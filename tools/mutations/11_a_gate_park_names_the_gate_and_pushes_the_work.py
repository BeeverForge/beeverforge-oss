"""Proven by breaking it — a park on failed gates names the gate, and pushes the work it leaves (#11).

The gate park handed the card one sentence, `validations failed after N repair attempt(s)`, and
pushed nothing: the tech-lead role read one such park three times and reasoned about the code each
time, wrongly, because the failing test names were never written down, and the agent's commits
lived only in a worktree `cleanup` removes.

FOUR CLAIMS:

  1. **The note names each failing blocking gate** — its role, its command and the last lines it
     printed — at most three, then how many more, and never an advisory gate.
  2. **What a gate printed is scrubbed before it is cut, on every surface**: the note (and so the
     ticket comment), the journal's full tail, and git's words when the push fails.
  3. **The park keeps its identity**: the first line is still the sentence `classify` reads as the
     change, the park declares that cause itself, and `memory.signature` signs only that line.
  4. **The work is pushed through `_preserve_for_hold`**, and when nothing was written the note
     says nothing was pushed.

AND SIX MORE, FROM THE REVIEW OF THE FIRST CUT:

  5. **A credential no name gives away is withheld too** — `AZURE_DEVOPS_PAT`, a project's
     `token_env` — from the note, the comment, the journal and the push warning.
  6. **A failed push says where the work is, on each box**: the local branch and its repository on
     the worktree box, with "push it by hand before resuming" and a handle that makes that Resume
     start from the forge's copy; "discarded" where nothing survives.
  7. **Each step that fails is named as itself**: a commit that fails is not a push that failed.
  8. **A push replaces only the tip the workspace saw** (`--force-with-lease`, both boxes), and a
     refused push holds the job, naming the branch; a run's own second push still lands.
  9. **What a gate printed notifies nobody**: indented, and with `#12` written `card 12`.
 10. **Resume continues from the forge's branch**, a person's fix on it included.

The guards are `tests/test_a_gate_park_names_the_gate_and_pushes_the_work.py` and, for the
boxes' push, `tests/test_a_push_replaces_only_what_the_workspace_saw.py`.
"""

TEST = "tests/test_a_gate_park_names_the_gate_and_pushes_the_work.py"

PUSH = "tests/test_a_push_replaces_only_what_the_workspace_saw.py"

MACHINE = "beeverforge/orchestrator/machine.py"
MEMORY = "beeverforge/techlead/memory.py"
WORKTREE = "beeverforge/adapters/sandbox/worktree.py"
CONTAINER = "beeverforge/adapters/sandbox/container.py"

MUTATIONS = [
    # ── claim 1: what the note names ──────────────────────────────────────────────────────────
    ("the gate line drops the role, so the card says a gate failed and not which",
     MACHINE,
     '        blocks.append(f"`{v.name}` exited {v.exit_code}:\\n\\n{body}")',
     '        blocks.append(f"a gate exited {v.exit_code}:\\n\\n{body}")'),

    ("the gate line drops the command",
     MACHINE,
     "        lines = [without_mentions(ln) for ln in [*command, *printed]]",
     "        lines = [without_mentions(ln) for ln in [*printed]]"),

    ("the gate line drops what the gate printed — the failing test names the issue measured",
     MACHINE,
     "        lines = [without_mentions(ln) for ln in [*command, *printed]]",
     "        lines = [without_mentions(ln) for ln in [*command]]"),

    ("the advisory filter goes, so a gate that reports and never decides is named as the cause",
     MACHINE,
     "    return [v for v in validations if v.passed is False and not v.advisory and not "
     "v.unrunnable]",
     "    return [v for v in validations if v.passed is False and not v.unrunnable]"),

    ("past three failing gates the rest are dropped without a count",
     MACHINE,
     "    if len(failing) > _GATES_NAMED:",
     "    if False:"),

    # ── claim 2: the scrub, on every surface ──────────────────────────────────────────────────
    ("the note's tail is the raw output, so a token the gate printed reaches the ticket",
     MACHINE,
     "_withheld(v.output_tail, secrets).splitlines()",
     "v.output_tail.splitlines()"),

    ("the gate line's command is unscrubbed",
     MACHINE,
     "                   (_withheld(v.command, secrets).splitlines() or [\"\"])]",
     "                   (v.command.splitlines() or [\"\"])]"),

    ("the journal's full tail is the raw output",
     MACHINE,
     '                         "output_tail": _withheld(v.output_tail, secrets)}',
     '                         "output_tail": v.output_tail}'),

    ("the journal no longer receives the full tails: the card's short form is all there is",
     MACHINE,
     '                    self._emit(ticket, "note", f"{reason} — the failing gates", gates=[',
     '                    (ticket, "note", f"{reason} — the failing gates", ['),

    ("git's words on a failed push reach the journal with the push URL's credential in them",
     MACHINE,
     "            # git's words can carry the push URL's userinfo: withheld before the cut (#11)\n"
     "            self._emit(ticket, \"warning\", f\"couldn't preserve partial work \"\n"
     "                       f\"({_withheld(str(exc), self._in_the_gates_reach())[:120]})\")",
     "            self._emit(ticket, \"warning\", f\"couldn't preserve partial work \"\n"
     "                       f\"({str(exc)[:120]})\")"),

    # ── claim 3: the park's identity ──────────────────────────────────────────────────────────
    ("the park stops declaring its cause, so what the project printed steers `classify`",
     MACHINE,
     "                    result.hold_cause = CODE\n",
     ""),

    ("the memory signs the whole note, so a tail that differs on every run is a new failure",
     MEMORY,
     '    text = (note or "").strip().split("\\n", 1)[0].lower()',
     '    text = (note or "").strip().lower()'),

    # ── claim 4: the push ─────────────────────────────────────────────────────────────────────
    ("THE DEFECT ITSELF: the gate park skips `_preserve_for_hold` and claims the work was pushed",
     MACHINE,
     "                result.resume_handle = self._preserve_for_hold(\n"
     "                    ticket, ws, rep.resume_handle if attempts else "
     "agent_result.resume_handle)",
     "                result.resume_handle = None\n"
     "                self._preserve_outcome = \"pushed\""),

    ("with nothing written the note is silent about the push",
     MACHINE,
     '        return ("Nothing was pushed: the agent left no change on the branch, so a Resume '
     'starts "\n                "fresh.")',
     '        return ""'),

    ("a failed push on the worktree box is not said to have pushed nothing",
     MACHINE,
     '        return (f"Nothing was pushed: the push of `{branch}` to the forge failed',
     '        return (f"The push of `{branch}` to the forge failed'),

    ("a failed push on a box that keeps nothing is not said to have pushed nothing",
     MACHINE,
     '    return (f"Nothing was pushed: the push of `{branch}` to the forge failed (the journal has "\n'
     '            f"git\'s words), and the box\'s copy',
     '    return (f"The push of `{branch}` to the forge failed (the journal has "\n'
     '            f"git\'s words), and the box\'s copy'),

    # ── claim 5: a credential under a name nothing reads as one ───────────────────────────────
    ("THE FINDING: the values in the gate's reach are not withheld, only the shapes",
     MACHINE,
     "    for secret in secrets:\n        text = text.replace(secret, WITHHELD_CREDENTIAL)\n",
     ""),

    ("the worktree box names only what is credential-shaped, so a `token_env` of any other name "
     "is printed",
     WORKTREE,
     "        asked = {*named, *self.extra_env, *_AUTH_ENV_VARS}",
     "        asked = {*self.extra_env, *_AUTH_ENV_VARS}"),

    ("the worktree box names only what it is told, so `AZURE_DEVOPS_PAT` is printed",
     WORKTREE,
     "                if value and (name in asked or holds_a_credential(name))}",
     "                if value and name in asked}"),

    ("the machine does not ask with the project's `token_env` names",
     MACHINE,
     "            found = (ask(named=named) if callable(ask)",
     "            found = (ask(named=()) if callable(ask)"),

    # ── claim 6: where the work is, by box ────────────────────────────────────────────────────
    ("the worktree box says nothing survives it, so the note calls kept work lost",
     WORKTREE,
     "        without it is one where nothing survives.\"\"\"\n        return self._repo_root\n",
     "        without it is one where nothing survives.\"\"\"\n        return None\n"),

    ("a failed push on the worktree box carries no handle, so the Resume after the push by hand "
     "starts from the base",
     MACHINE,
     "            if self._preserve_outcome == \"push-failed\" and self._kept_after_cleanup(ws):",
     "            if False:"),

    ("a failed push carries a handle on a box that kept nothing",
     MACHINE,
     "            if self._preserve_outcome == \"push-failed\" and self._kept_after_cleanup(ws):",
     "            if self._preserve_outcome == \"push-failed\":"),

    ("the first cut's sentence comes back: check the credential, and Resume deletes the work",
     MACHINE,
     "    if kept is not None:\n",
     "    if False:\n"),

    # ── claim 7: each step is named as itself ─────────────────────────────────────────────────
    ("THE FINDING: any failure is recorded as a failed push",
     MACHINE,
     '        self._preserve_outcome = "not-committed"\n',
     '        self._preserve_outcome = "push-failed"\n'),

    # ── claim 8: the lease ────────────────────────────────────────────────────────────────────
    ("THE FINDING: the push is a plain `--force` again, on both boxes",
     WORKTREE,
     '    return [f"--force-with-lease=refs/heads/{workspace.branch}:{workspace.lease}"]',
     '    return ["--force"]'),

    ("the worktree box starts a fresh workspace with no lease, so it pushes over anything",
     WORKTREE,
     '        lease: str | None = None if _is_this_repo(remote_url, repo_path) else ""',
     "        lease: str | None = None"),

    ("the worktree box leases a resume on nothing, so its push is refused over its own start",
     WORKTREE,
     '                lease = _tip(repo_path, f"refs/remotes/origin/{branch}")\n',
     "",
     PUSH),

    ("the worktree box does not move its lease after a push, so a repair's second push is refused",
     WORKTREE,
     '            workspace.lease = _tip(workspace.path, f"refs/heads/{workspace.branch}")',
     "            pass",
     PUSH),

    ("the container box does not move its lease after a push",
     CONTAINER,
     '            workspace.lease = _tip(self._host_clone, f"refs/heads/{workspace.branch}")',
     "            pass",
     PUSH),

    ("the container box starts a fresh workspace with no lease",
     CONTAINER,
     '    if not checkout_existing:\n        return ""\n',
     "    if not checkout_existing:\n        return None\n",
     PUSH),

    ("the container box leases a resume on nothing",
     CONTAINER,
     '    return _tip(host_clone, f"refs/remotes/origin/{branch}")',
     '    return ""',
     PUSH),

    ("a refused push is not told from any other failed push, on either box",
     WORKTREE,
     "            if LEASE_REFUSED in out:\n"
     "                raise PushRefused(f\"push refused: {_redact(out)}\", "
     "branch=workspace.branch)\n"
     "            raise RuntimeError(f\"push failed: {_redact(out)}\")\n"
     "        if workspace.lease is not None:\n"
     "            workspace.lease = _tip(workspace.path",
     "            raise RuntimeError(f\"push failed: {_redact(out)}\")\n"
     "        if workspace.lease is not None:\n"
     "            workspace.lease = _tip(workspace.path"),

    ("THE FINDING: the refused pull-request push is not held, and the run goes on to open it",
     MACHINE,
     "                return self._hold(ticket, owner, _lease_refused_said(branch), "
     "JobState.ON_HOLD,\n"
     "                                  branch=branch, resume_handle=_FROM_THE_FORGE)",
     "                pass"),

    ("the refused pull-request push holds with no handle, so its Resume starts from the base again",
     MACHINE,
     "                                  branch=branch, resume_handle=_FROM_THE_FORGE)",
     "                                  branch=branch)"),

    ("a gate park whose push was refused says the push failed",
     MACHINE,
     '            self._preserve_outcome = "lease-refused"\n',
     ""),

    # ── claim 9: nobody is notified ───────────────────────────────────────────────────────────
    ("THE FINDING: the indent goes, so an `@someone` the gate printed notifies them",
     MACHINE,
     '        body = "\\n".join(f"    {ln}" for ln in lines)',
     '        body = "\\n".join(f"{ln}" for ln in lines)'),

    ("a `#12` the gate printed reaches a tracker that links it",
     MACHINE,
     "        lines = [without_mentions(ln) for ln in [*command, *printed]]",
     "        lines = [ln for ln in [*command, *printed]]"),

    # ── claim 10: Resume ──────────────────────────────────────────────────────────────────────
    ("a Resume prepares from the base, so it continues nothing",
     MACHINE,
     "                checkout_existing=resuming,\n",
     "                checkout_existing=False,\n"),
]
