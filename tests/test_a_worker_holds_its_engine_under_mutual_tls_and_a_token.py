"""A worker holds its engine under mutual TLS and a JWT at once, against a real server (#657).

THE SERVER. A real `temporalio/auto-setup` — the version the compose stack runs — on a Postgres of
its own, both started here once for the module on a Docker network of their own and stopped with
it. Mutual TLS is on for the frontend and between the server's own services
(`TEMPORAL_TLS_REQUIRE_CLIENT_AUTH`), with one CA made here for the server, the client and the
connection's `TEMPORAL_TLS_SERVER_CA_CERT`. The default JWT authorizer and claim mapper are on, and
read their signing key from a JWKS document this module serves on the network's gateway. The
internal frontend is on (`USE_INTERNAL_FRONTEND`), so the server's own system workers need no
token, and the image's own setup steps are off: the namespace is registered here, with a token
that carries the system's admin role.

WHAT IS HELD, through `connection.connect()` and the settings a deployment sets — the certificate,
its key, the server CA, and the API key as a file in the `file` credential store:

  1. a certificate and a token (`<namespace>:write`, which polling needs) poll the namespace — a
     worker on the connection's client runs a workflow to its end;
  2. the certificate without a token is refused by the authorizer;
  3. the token without the certificate is refused at the handshake, before any authorizer;
  4. a token rotated in place reaches the held client without a reconnect, and the worker on it
     keeps polling: an already-expired token is refused by the server once it is presented, and the
     fresh one after it runs the next workflow on the same worker.

BOUNDED: the only real waits are the readiness poll (at most `READY_WITHIN_S`) and each workflow's
bound. The engine's address is the port Docker published for this module's container, handed to
`connection.address` — never a deployment's setting.

Needs a Docker daemon and is skipped without one, as the other real-daemon tests are; where
`TEST_REQUIRE_DOCKER` is set it runs regardless, and fails rather than skipping.
"""

from __future__ import annotations

import asyncio
import datetime
import http.server
import ipaddress
import json
import os
import shutil
import socketserver
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from temporalio import workflow
from temporalio.api.workflowservice.v1 import (
    DescribeNamespaceRequest,
    RegisterNamespaceRequest,
)
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode, TLSConfig
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from beeverforge.adapters.credential_store.file import DIR_VAR
from beeverforge.adapters.credential_store.registry import STORE_VAR
from beeverforge.runtime.temporal import connection

#: The engine the compose stack runs (`docker-compose.yml`), and its database.
IMAGE = "temporalio/auto-setup:1.25.2"
DATABASE = "postgres:16"
NAMESPACE = "bf657"
#: The key id the JWKS document and every token carry: the default claim mapper needs one.
KID = "bf-657"
#: The readiness poll's bound: the image creates its schema before it serves.
READY_WITHIN_S = 180.0
#: Each workflow's bound, once the server is ready.
JOB_WITHIN_S = 60.0
#: How long one image may take to pull, where this machine does not hold it yet.
PULL_WITHIN_S = 600.0


def _docker() -> bool:
    """A Docker daemon answers — asked at import, so it stays cheap. Where `TEST_REQUIRE_DOCKER`
    is set it answers yes regardless, so a CI that lost its daemon fails here instead of
    skipping in silence (`tests/one_live_preview._docker_and_compose`)."""
    if os.environ.get("TEST_REQUIRE_DOCKER"):
        return True
    if not shutil.which("docker"):
        return False
    try:
        daemon = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return daemon.returncode == 0


pytestmark = [
    pytest.mark.owns_its_engine,
    pytest.mark.slow,
    pytest.mark.skipif(not _docker(), reason="needs a Docker daemon"),
    pytest.mark.xdist_group("docker"),
]

@workflow.defn(name="Polled657")
class Polled:
    @workflow.run
    async def run(self) -> str:
        return "polled"


# ── the material: one CA, a server certificate, a client certificate, a signing key ────────────

def _key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _certificate(name: str, key, *, issuer=None, issuer_key=None, ca=False, usages=(),
                 names=()) -> x509.Certificate:
    now = datetime.datetime.now(datetime.UTC)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    built = (x509.CertificateBuilder()
             .subject_name(subject)
             .issuer_name(issuer.subject if issuer is not None else subject)
             .public_key(key.public_key())
             .serial_number(x509.random_serial_number())
             .not_valid_before(now - datetime.timedelta(hours=1))
             .not_valid_after(now + datetime.timedelta(days=1))
             .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if ca:
        built = built.add_extension(x509.KeyUsage(
            digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            encipher_only=False, decipher_only=False), critical=True)
    if usages:
        built = built.add_extension(x509.ExtendedKeyUsage(list(usages)), critical=False)
    if names:
        built = built.add_extension(x509.SubjectAlternativeName(list(names)), critical=False)
    return built.sign(issuer_key if issuer_key is not None else key, hashes.SHA256())


def _write(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    # READABLE BY THE CONTAINER'S OWN USER through the bind mount; these keys exist for this
    # module only and sign nothing outside it.
    path.chmod(0o644)
    return str(path)


@dataclass
class Engine:
    address: str
    ca: str
    client_cert: str
    client_key: str
    signing_key: ec.EllipticCurvePrivateKey

    def token(self, *permissions: str, lives: float = 600.0) -> str:
        """A JWT the server's default claim mapper reads; `lives` below zero is already expired."""
        now = int(time.time())
        expires = int(now + lives)
        # ISSUED BEFORE IT EXPIRES AND NEVER IN THE FUTURE, which the server refuses as well.
        return jwt.encode({"sub": "worker-657", "permissions": list(permissions),
                           "iat": min(now, expires) - 60, "exp": expires},
                          self.signing_key, algorithm="ES256", headers={"kid": KID})

    def tls(self, *, certificate: bool = True) -> TLSConfig:
        mine = ({"client_cert": Path(self.client_cert).read_bytes(),
                 "client_private_key": Path(self.client_key).read_bytes()} if certificate else {})
        return TLSConfig(server_root_ca_cert=Path(self.ca).read_bytes(), **mine)


class _JwksServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        # NOT `HTTPServer.server_bind`, which asks DNS for the bound address's name.
        socketserver.TCPServer.server_bind(self)


def _serve_jwks(host: str, document: bytes) -> _JwksServer:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — the handler's own spelling
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)

        def log_message(self, *_args) -> None:
            pass

    server = _JwksServer((host, 0), Handler)
    threading.Thread(target=server.serve_forever, name="jwks-657", daemon=True).start()
    return server


def _cannot(reason: str) -> None:
    """Skip with `reason` — or fail with it where `TEST_REQUIRE_DOCKER` says this must run."""
    if os.environ.get("TEST_REQUIRE_DOCKER"):
        pytest.fail(reason)
    pytest.skip(reason)


def _pulled(image: str) -> None:
    """`image` on this machine, pulled in a step of its own and bounded by `PULL_WITHIN_S`, so a
    slow registry is said as itself and never as an engine that did not start."""
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True,
                      timeout=60).returncode == 0:
        return
    try:
        done = subprocess.run(["docker", "pull", image], capture_output=True, text=True,
                              timeout=PULL_WITHIN_S)
    except subprocess.TimeoutExpired:
        _cannot(f"pulling {image} took longer than {PULL_WITHIN_S:g}s")
    if done.returncode != 0:
        _cannot(f"{image} could not be pulled: {done.stderr.strip()[-300:]}")


def _docker_run(*args: str) -> str:
    try:
        done = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise AssertionError(f"docker {' '.join(args[:2])} did not answer in 120s") from None
    if done.returncode != 0:
        raise AssertionError(f"docker {' '.join(args[:2])} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def _logs(container: str) -> str:
    done = subprocess.run(["docker", "logs", "--tail", "40", container], capture_output=True,
                          text=True, timeout=30)
    return (done.stdout + done.stderr)[-4000:]


async def _registered(engine: Engine) -> None:
    """Bounded readiness: register the namespace with a system-admin token, then wait until a
    workflow can be started in it (the namespace reaches the server's cache in its own time)."""
    admin = engine.token("temporal-system:admin")
    deadline = time.monotonic() + READY_WITHIN_S
    said: object = None
    registered = False
    while time.monotonic() < deadline:
        try:
            client = await Client.connect(engine.address, namespace=NAMESPACE, api_key=admin,
                                          tls=engine.tls())
            if not registered:
                try:
                    await client.workflow_service.register_namespace(RegisterNamespaceRequest(
                        namespace=NAMESPACE,
                        workflow_execution_retention_period={"seconds": 86400}))
                except RPCError as exc:
                    if exc.status != RPCStatusCode.ALREADY_EXISTS:
                        raise
                registered = True
            handle = await client.start_workflow(Polled.run, id=f"ready-{uuid.uuid4().hex[:8]}",
                                                 task_queue="ready-657")
            await handle.terminate()
            return
        except (RPCError, RuntimeError) as exc:
            said = exc
        await asyncio.sleep(1.0)
    raise AssertionError(f"the engine was not ready in {READY_WITHIN_S:g}s: {said}")


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """The server, once for the module: its network, its database, its JWKS and itself."""
    here = tmp_path_factory.mktemp("engine-657")
    here.chmod(0o755)
    ca_key, server_key, client_key, signing = _key(), _key(), _key(), _key()
    ca = _certificate("engine-657-ca", ca_key, ca=True)
    server = _certificate("localhost", server_key, issuer=ca, issuer_key=ca_key,
                          usages=(ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH),
                          names=(x509.DNSName("localhost"),
                                 x509.IPAddress(ipaddress.ip_address("127.0.0.1"))))
    client = _certificate("worker-657", client_key, issuer=ca, issuer_key=ca_key,
                          usages=(ExtendedKeyUsageOID.CLIENT_AUTH,))
    pem = serialization.Encoding.PEM
    ca_path = _write(here / "ca.pem", ca.public_bytes(pem))
    _write(here / "server.pem", server.public_bytes(pem))
    _write(here / "server.key", _pem(server_key))
    client_cert = _write(here / "client.pem", client.public_bytes(pem))
    client_key_path = _write(here / "client.key", _pem(client_key))
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(signing.public_key()))
    jwks = json.dumps({"keys": [{**jwk, "kid": KID, "alg": "ES256", "use": "sig"}]}).encode()

    for image in (DATABASE, IMAGE):
        _pulled(image)
    tag = uuid.uuid4().hex[:8]
    network, database, temporal = f"bf657-{tag}", f"bf657-db-{tag}", f"bf657-engine-{tag}"
    started: list[str] = []
    jwks_server = None
    _docker_run("network", "create", network)
    try:
        gateway = _docker_run("network", "inspect", network, "-f",
                              "{{(index .IPAM.Config 0).Gateway}}")
        try:
            jwks_server = _serve_jwks(gateway, jwks)
        except OSError as exc:
            # DOCKER DESKTOP AND A ROOTLESS DAEMON keep the network's gateway inside their own
            # VM or namespace: this process cannot listen there, and the engine could not reach a
            # key served anywhere else it can see.
            _cannot(f"the JWKS server cannot listen on the Docker network's gateway {gateway} "
                    f"({exc.strerror or exc}) — a daemon whose networks this host does not hold")
        jwks_url = f"http://{gateway}:{jwks_server.server_address[1]}/jwks.json"
        _docker_run("run", "-d", "--rm", "--name", database, "--network", network,
                    "-e", "POSTGRES_USER=temporal", "-e", "POSTGRES_PASSWORD=temporal", DATABASE)
        started.append(database)
        certs = {"TEMPORAL_TLS_SERVER_CERT": "/certs/server.pem",
                 "TEMPORAL_TLS_SERVER_KEY": "/certs/server.key",
                 "TEMPORAL_TLS_SERVER_CA_CERT": "/certs/ca.pem",
                 "TEMPORAL_TLS_FRONTEND_CERT": "/certs/server.pem",
                 "TEMPORAL_TLS_FRONTEND_KEY": "/certs/server.key",
                 "TEMPORAL_TLS_CLIENT1_CA_CERT": "/certs/ca.pem",
                 "TEMPORAL_TLS_CLIENT2_CA_CERT": "/certs/ca.pem",
                 "TEMPORAL_TLS_INTERNODE_SERVER_NAME": "localhost",
                 "TEMPORAL_TLS_FRONTEND_SERVER_NAME": "localhost",
                 "TEMPORAL_TLS_REQUIRE_CLIENT_AUTH": "true"}
        settings = {"DB": "postgres12", "DB_PORT": "5432", "POSTGRES_USER": "temporal",
                    "POSTGRES_PWD": "temporal", "POSTGRES_SEEDS": database,
                    "USE_INTERNAL_FRONTEND": "true",
                    "TEMPORAL_AUTH_AUTHORIZER": "default",
                    "TEMPORAL_AUTH_CLAIM_MAPPER": "default",
                    "TEMPORAL_JWT_KEY_SOURCE1": jwks_url,
                    "SKIP_DEFAULT_NAMESPACE_CREATION": "true",
                    "SKIP_ADD_CUSTOM_SEARCH_ATTRIBUTES": "true",
                    **certs}
        env = [arg for name, value in settings.items() for arg in ("-e", f"{name}={value}")]
        _docker_run("run", "-d", "--rm", "--name", temporal, "--network", network,
                    "-p", "127.0.0.1::7233", "-v", f"{here}:/certs:ro", *env, IMAGE)
        started.append(temporal)
        port = _docker_run("port", temporal, "7233/tcp").splitlines()[0].rsplit(":", 1)[1]
        held = Engine(address=f"127.0.0.1:{port}", ca=ca_path, client_cert=client_cert,
                      client_key=client_key_path, signing_key=signing)
        try:
            asyncio.run(_registered(held))
        except AssertionError as exc:
            raise AssertionError(f"{exc}\n--- the engine's log ---\n{_logs(temporal)}") from None
        yield held
    finally:
        for container in reversed(started):
            subprocess.run(["docker", "stop", "-t", "2", container], capture_output=True,
                           timeout=60)
        subprocess.run(["docker", "network", "rm", network], capture_output=True, timeout=60)
        if jwks_server is not None:
            jwks_server.shutdown()
            jwks_server.server_close()


@pytest.fixture
def deployed(engine, monkeypatch, tmp_path):
    """This engine's settings as a deployment sets them: the certificate and its key, the server
    CA, and the API key as a file in the `file` credential store. Answers the key's file."""
    for name in ("TEMPORAL_ENDPOINT", "TEMPORAL_API_KEY", "BEEVERFORGE_LOG_FORMAT",
                 "TEMPORAL_AUTH_REFRESH_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(connection, "address", lambda: engine.address)
    monkeypatch.setenv("TEMPORAL_NAMESPACE", NAMESPACE)
    monkeypatch.setenv("TEMPORAL_TLS_CERT", engine.client_cert)
    monkeypatch.setenv("TEMPORAL_TLS_KEY", engine.client_key)
    monkeypatch.setenv("TEMPORAL_TLS_SERVER_CA_CERT", engine.ca)
    secrets = tmp_path / "secrets"
    secrets.mkdir(mode=0o700)
    held = secrets / "TEMPORAL_API_KEY"
    held.write_text(engine.token(f"{NAMESPACE}:write"))
    held.chmod(0o600)
    monkeypatch.setenv(STORE_VAR, "file")
    monkeypatch.setenv(DIR_VAR, str(secrets))
    connection.forget()
    yield held
    connection.forget()


async def _a_job(client: Client, queue: str) -> str:
    async with asyncio.timeout(JOB_WITHIN_S):
        return await client.execute_workflow(Polled.run, id=f"job-{uuid.uuid4().hex[:8]}",
                                             task_queue=queue)


def _worker(client: Client, queue: str) -> Worker:
    return Worker(client, task_queue=queue, workflows=[Polled],
                  workflow_runner=UnsandboxedWorkflowRunner())


async def test_a_certificate_and_a_token_POLL_the_namespace(deployed):
    client = await connection.connect(within=20)
    queue = f"q-{uuid.uuid4().hex[:8]}"

    async with _worker(client, queue):
        assert await _a_job(client, queue) == "polled"


async def test_a_certificate_WITHOUT_a_token_is_refused_by_the_authorizer(deployed):
    deployed.unlink()   # the store answers nothing, and the environment holds no key

    with pytest.raises(RPCError) as refused:
        client = await connection.connect(within=20)
        await client.workflow_service.describe_namespace(
            DescribeNamespaceRequest(namespace=NAMESPACE))

    assert refused.value.status == RPCStatusCode.PERMISSION_DENIED, (
        f"a certificate without a token was answered {refused.value.status!r}: "
        f"{refused.value.message}")


async def test_a_token_WITHOUT_a_certificate_is_refused_at_the_handshake(deployed, monkeypatch):
    monkeypatch.delenv("TEMPORAL_TLS_CERT")
    monkeypatch.delenv("TEMPORAL_TLS_KEY")

    with pytest.raises(RuntimeError) as refused:
        await connection.connect(within=20)

    assert not isinstance(refused.value, RPCError), (
        f"a token without a certificate reached the server's API ({refused.value!r}) — the "
        f"handshake should have refused it before any authorizer")
    # THE SERVER'S OWN ALERT, measured on 1.25.2: "received fatal alert: CertificateRequired" —
    # the TLS layer refused the connection, not a trust failure on the client's side.
    assert "CertificateRequired" in str(refused.value), refused.value


async def test_a_token_ROTATED_IN_PLACE_keeps_the_worker_polling(deployed, engine):
    client = await connection.connect(within=20)
    queue = f"q-{uuid.uuid4().hex[:8]}"

    async with _worker(client, queue):
        assert await _a_job(client, queue) == "polled"

        deployed.write_text(engine.token(f"{NAMESPACE}:write", lives=-60.0))
        assert connection.refresh_api_key(client) is True
        with pytest.raises(RPCError) as expired:
            await client.workflow_service.describe_namespace(
                DescribeNamespaceRequest(namespace=NAMESPACE))
        assert expired.value.status in (RPCStatusCode.PERMISSION_DENIED,
                                        RPCStatusCode.UNAUTHENTICATED), expired.value

        deployed.write_text(engine.token(f"{NAMESPACE}:write", lives=900.0))
        assert connection.refresh_api_key(client) is True
        assert await _a_job(client, queue) == "polled", "the worker stopped polling"

    assert await connection.connect(within=20) is client, "the rotation made a new client"
