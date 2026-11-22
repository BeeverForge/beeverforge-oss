"""ADR-0052 D15, proven by breaking it — a knowledge source beside the product's own, off by default.

FIVE CLAIMS:

  1. **Off is the core as it was.** Unset or `none`, the facts pack is the one written with the step
     taken out, byte for byte, and the role's prompt names no file of it.
  2. **On, one file of cited answers.** Each sentence with its labels; an abstention as one.
  3. **Asked as the role, and as nothing else.** The bearer token, the message, the product when
     one is named, no person; once a turn; a redirect is not followed.
  4. **A service that does not answer is one line, and the turn goes on.** A short `Retry-After`
     is waited for once and never in a loop; an answer larger than an answer is is none.
  5. **The token is never written, and a workload in a worktree box cannot read it.**

The guard under test is `tests/test_the_product_role_reads_beeverforge_knowledge_when_switched_on.py`,
whose service is real HTTP on this machine; the fifth claim's second half is
`tests/test_the_environment_carries_the_products_name.py`, which measures what reaches a workload.
"""

TEST = "tests/test_the_product_role_reads_beeverforge_knowledge_when_switched_on.py"

REGISTRY = "beeverforge/adapters/knowledge_source/registry.py"
SERVICE = "beeverforge/adapters/knowledge_source/service.py"
ANSWERS = "beeverforge/product/knowledge_answers.py"
MODULE = "beeverforge/product/module.py"
ROLE = "beeverforge/product/role.py"
WORKTREE = "beeverforge/adapters/sandbox/worktree.py"
SCRUB = "tests/test_the_environment_carries_the_products_name.py"

MUTATIONS = [
    # ── 1. off is the core as it was ────────────────────────────────────────────────────────────
    ("the add-on is ON by default: a deployment that said nothing asks the service", REGISTRY,
     'DEFAULT_KIND = OFF\n', 'DEFAULT_KIND = "beeverforge-knowledge"\n'),

    ("`none` is read as switched on: the pack gains a gap line nobody asked for", REGISTRY,
     "    return kind() != OFF\n", "    return True\n"),

    ("the pack asks whatever the axis says, off included", ANSWERS,
     "    if not registry.switched_on() or not question.strip():\n",
     "    if not question.strip():\n"),

    ("the prompt names the file of answers with the axis off", ROLE,
     "    if not registry.switched_on():\n        return []\n",
     "    if False:\n        return []\n"),

    # ── 2. on, one file of cited answers ───────────────────────────────────────────────────────
    ("the sentences lose their labels", ANSWERS,
     "        labels = f\" [{', '.join(said.citations)}]\" if said.citations else \"\"\n",
     "        labels = \"\"\n"),

    ("an abstention is written as if it were an answer", ANSWERS,
     "    if answered.abstained:\n", "    if False:\n"),

    ("the file is never handed to the pack", MODULE,
     "        found = {**found, **attached, **known}\n",
     "        found = {**found, **attached}\n"),

    # ── 3. asked as the role, and as nothing else ──────────────────────────────────────────────
    ("the token is not sent", SERVICE,
     '                        headers={"Authorization": f"Bearer {_the_token()}",\n',
     '                        headers={"Authorization": "Bearer",\n'),

    ("a person is named in a call that has none in the turn", SERVICE,
     '                                 "Accept": "application/json"}) as response:\n',
     '                                 "Accept": "application/json",\n'
     '                                 "Knowledge-Person": "someone"}) as response:\n'),

    ("an empty product is sent as one", SERVICE,
     "        if self.product:\n", "        if True:\n"),

    ("the service is asked again for every pack the turn writes", MODULE,
     '    if "_known_before" not in vars(module):\n', "    if True:\n"),

    ("a redirect is followed, and the token goes where it points", SERVICE,
     "follow_redirects=False,", "follow_redirects=True,"),

    # ── 4. a service that does not answer is one line ──────────────────────────────────────────
    ("a short Retry-After is never waited for", SERVICE,
     "            if wait is None or wait > SHORT_WAIT_SECONDS:\n", "            if True:\n"),

    ("a rate-limited service is asked a third time", SERVICE,
     "            if response.status_code == 429:\n"
     '                raise NotAsked("it asked to be asked again later (HTTP 429), twice")\n',
     "            if response.status_code == 429:\n"
     "                response = self._post(body)\n"),

    ("an answer larger than its bound is read whole", SERVICE,
     "        if len(read) > MAX_ANSWER_BYTES:\n            return None\n",
     "        if False:\n            return None\n"),

    ("a token is sent in clear to another machine", SERVICE,
     '    if parts.scheme == "http" and not _loopback(host):\n', "    if False:\n"),

    ("a timeout that is not a number of seconds is taken as the default", SERVICE,
     "        seconds = math.nan\n", "        seconds = DEFAULT_TIMEOUT_SECONDS\n"),

    # ── 5. the token is never written ──────────────────────────────────────────────────────────
    ("a refusal carries the token", SERVICE,
     '        raise NotAsked(f"it {said}")\n',
     '        raise NotAsked(f"it {said} ({_the_token()})")\n'),

    ("a workload in a worktree box can read the token", WORKTREE,
     '"BEEVERFORGE_CREDENTIAL_DIR", "BEEVERFORGE_KNOWLEDGE_TOKEN")',
     '"BEEVERFORGE_CREDENTIAL_DIR")', SCRUB),
]
