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

The guard is `tests/test_a_gate_park_names_the_gate_and_pushes_the_work.py`.
"""

TEST = "tests/test_a_gate_park_names_the_gate_and_pushes_the_work.py"

MACHINE = "beeverforge/orchestrator/machine.py"
MEMORY = "beeverforge/techlead/memory.py"

MUTATIONS = [
    # ── claim 1: what the note names ──────────────────────────────────────────────────────────
    ("the gate line drops the role, so the card says a gate failed and not which",
     MACHINE,
     '        blocks.append(f"`{v.name}` exited {v.exit_code}:\\n\\n{body}")',
     '        blocks.append(f"a gate exited {v.exit_code}:\\n\\n{body}")'),

    ("the gate line drops the command",
     MACHINE,
     '        body = "\\n".join(f"    {ln}" for ln in [*command, *printed])',
     '        body = "\\n".join(f"    {ln}" for ln in [*printed])'),

    ("the gate line drops what the gate printed — the failing test names the issue measured",
     MACHINE,
     '        body = "\\n".join(f"    {ln}" for ln in [*command, *printed])',
     '        body = "\\n".join(f"    {ln}" for ln in [*command])'),

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
     "_without_credentials(v.output_tail).splitlines()",
     "v.output_tail.splitlines()"),

    ("the gate line's command is unscrubbed",
     MACHINE,
     "                   (_without_credentials(v.command).splitlines() or [\"\"])]",
     "                   (v.command.splitlines() or [\"\"])]"),

    ("the journal's full tail is the raw output",
     MACHINE,
     '                         "output_tail": _without_credentials(v.output_tail)}',
     '                         "output_tail": v.output_tail}'),

    ("the journal no longer receives the full tails: the card's short form is all there is",
     MACHINE,
     '                    self._emit(ticket, "note", f"{reason} — the failing gates", gates=[',
     '                    (ticket, "note", f"{reason} — the failing gates", ['),

    ("git's words on a failed push reach the journal with the push URL's credential in them",
     MACHINE,
     "f\"couldn't preserve partial work ({_without_credentials(str(exc))[:120]})\")",
     "f\"couldn't preserve partial work ({str(exc)[:120]})\")"),

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

    ("a failed push is not said to have pushed nothing",
     MACHINE,
     '    return (f"Nothing was pushed: the push of `{branch}` to the forge failed',
     '    return (f"The push of `{branch}` to the forge failed'),
]
