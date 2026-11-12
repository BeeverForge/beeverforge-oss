"""`beeverforge box answer` asks with the model the project runs, on every harness.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/the_question_is_asked_with_the_model_the_project_runs.py

Row 1 is the defect as it shipped: the claude adapter's smallest call read `planner_model` alone,
which an executor build leaves empty, so the question went out with no `--model`. Row 2 loses the
fallback a judging build needs (it has no executor model). Row 3 invents a model for a project
that chose none. Rows 4-6 empty the model in the other three harnesses' smallest call, so the
parity the test holds across the four is shown to be held.
"""

TEST = "tests/test_something_finally_asks_the_agent.py"

CLAUDE = "beeverforge/adapters/agent/claude_code.py"
CODEX = "beeverforge/adapters/agent/codex.py"
KIMI = "beeverforge/adapters/agent/kimi.py"
OPENCODE = "beeverforge/adapters/agent/opencode.py"

MUTATIONS = [
    ("TODAY'S DEFECT: the smallest call reads the planner slot alone, which an executor build "
     "leaves empty", CLAUDE,
     '                         model=self.executor_model or self.planner_model, phase="chat")',
     '                         model=self.planner_model, phase="chat")'),

    ("the executor's slot is read alone: a judging build is asked with no model", CLAUDE,
     '                         model=self.executor_model or self.planner_model, phase="chat")',
     '                         model=self.executor_model, phase="chat")'),

    ("a project that chose no model is asked with one this code made up", CLAUDE,
     '                         model=self.executor_model or self.planner_model, phase="chat")',
     '                         model=self.executor_model or self.planner_model or "made-up-1",\n'
     '                         phase="chat")'),

    ("codex asks with no model", CODEX,
     "        return self._cli(prompt, harness=harness, model=self.planner_model,\n"
     '                         sandbox_mode="read-only")',
     "        return self._cli(prompt, harness=harness, model=None,\n"
     '                         sandbox_mode="read-only")'),

    ("kimi asks with no model", KIMI,
     "        return self._cli(prompt, harness=harness, model=self.planner_model)",
     "        return self._cli(prompt, harness=harness, model=None)"),

    ("opencode asks with no model", OPENCODE,
     "        return self._cli(prompt, harness=harness, model=self.planner_model,\n"
     "                         read_only=True)",
     "        return self._cli(prompt, harness=harness, model=None,\n"
     "                         read_only=True)"),
]
