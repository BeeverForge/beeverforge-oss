"""#335: no unit test reaches the network, and the sweep test that did now reaches no clone.

The first rows break the block in `tests/conftest.py` each way it could be wrong: letting every
address through, refusing the suite's own loopback and AF_UNIX servers, ignoring the marker,
leaving `connect_ex` open, letting a swallowed refusal pass, and a sentence that loses the test,
the address or the marker. The proof is an inner pytest run of probe tests, so each cut is seen
the way a real test would meet it.

The last two rows are the sweep test's own claim, which had to survive losing its clone: the
activity's call that drops `forge=`, and one that hands an Azure project's sweep a GitHub client.
"""

TEST = "tests/test_no_unit_test_reaches_the_network.py"
CONFTEST = "tests/conftest.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
SWEEP_TEST = ("tests/test_the_product_path_is_not_github_by_construction.py"
              "::test_the_HOURLY_sweep_is_handed_the_forge_it_used_to_run_without")

MUTATIONS = [
    ("every address is let through: the refusal is never reached", CONFTEST,
     "        if _a_local_host(address[0]):\n            return",
     "        if True:\n            return"),

    ("loopback is refused like the internet, so the suite's own servers fail", CONFTEST,
     "        if _a_local_host(address[0]):\n            return",
     "        if False:\n            return"),

    ("an IP literal on loopback is not recognised as local", CONFTEST,
     "    return ip.is_loopback or ip.is_unspecified",
     "    return ip.is_unspecified"),

    ("`localhost` by name is refused before it is resolved", CONFTEST,
     '    if host == "localhost":\n        return True\n',
     ""),

    ("AF_UNIX is checked like an internet address, so the Docker socket is refused", CONFTEST,
     "        if sock.family not in (socket.AF_INET, socket.AF_INET6):\n            return",
     "        if False:\n            return"),

    ("the marker is ignored, so a test that must reach the network cannot", CONFTEST,
     "    if request.node.get_closest_marker(NETWORK):",
     "    if False:"),

    ("`connect_ex` is left unguarded", CONFTEST,
     '    monkeypatch.setattr(socket.socket, "connect_ex", _connect_ex)',
     "    pass"),

    ("a refusal the code under test swallows leaves the test green", CONFTEST,
     "    if refused:\n        pytest.fail(refused[0], pytrace=False)",
     "    if refused:\n        pass"),

    ("the sentence no longer names the test", CONFTEST,
     'f"{nodeid} tried to connect',
     'f"a test tried to connect'),

    ("the sentence no longer names the address", CONFTEST,
     "tried to connect to {host}:{port}, which",
     "tried to connect to an address, which"),

    ("the sentence no longer names the marker that would allow it", CONFTEST,
     "@pytest.mark.{NETWORK}",
     "a marker"),

    ("the hourly sweep runs without a forge again and lands nothing", ACTIVITIES,
     "            forge=module._forge(),\n",
     "",
     SWEEP_TEST),

    ("an Azure project's sweep is handed a GitHub client, which reads nothing there", ACTIVITIES,
     "            forge=module._forge(),\n",
     '            forge=__import__("beeverforge.adapters.forge.github", '
     'fromlist=["GitHubForge"]).GitHubForge(cfg.docs_repo),\n',
     SWEEP_TEST),
]
