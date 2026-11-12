"""`beeverforge box answer` asks with the model the tickets run, on every harness.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/the_question_is_asked_with_the_model_the_project_runs.py

Row 1 is the defect as it shipped on claude: the smallest call read `planner_model`, which an
executor build leaves empty, so the question went out with no `--model`. Row 2 is the cut the
first version of the guard could not tell: the executor's slot first and the planner's behind it,
which only differs when `BEEVERFORGE_PLANNER_MODEL` is set and the project chose no model. Row 3
invents a model for a project that chose none. Rows 4-6 are the defect as it stands on the other
three harnesses: the question reads the planner slot, `BEEVERFORGE_PLANNER_MODEL or self.model`,
while `execute` reads `self.model`. Row 7 invents a model on one of them.
"""

TEST = "tests/test_something_finally_asks_the_agent.py"

CLAUDE = "beeverforge/adapters/agent/claude_code.py"
CODEX = "beeverforge/adapters/agent/codex.py"
KIMI = "beeverforge/adapters/agent/kimi.py"
OPENCODE = "beeverforge/adapters/agent/opencode.py"

MUTATIONS = [
    ("TODAY'S DEFECT on claude: the smallest call reads the planner slot, which an executor "
     "build leaves empty", CLAUDE,
     '                         model=self.executor_model, phase="chat")',
     '                         model=self.planner_model, phase="chat")'),

    ("claude falls through to the planner slot when the project chose no model", CLAUDE,
     '                         model=self.executor_model, phase="chat")',
     '                         model=self.executor_model or self.planner_model, phase="chat")'),

    ("claude asks a project that chose no model with one this code made up", CLAUDE,
     '                         model=self.executor_model, phase="chat")',
     '                         model=self.executor_model or "made-up-1", phase="chat")'),

    ("codex asks with the planner slot, which BEEVERFORGE_PLANNER_MODEL moves", CODEX,
     "        return self._cli(prompt, harness=harness, model=self.model,\n"
     '                         sandbox_mode="read-only")',
     "        return self._cli(prompt, harness=harness, model=self.planner_model,\n"
     '                         sandbox_mode="read-only")'),

    ("kimi asks with the planner slot, which BEEVERFORGE_PLANNER_MODEL moves", KIMI,
     "        return self._cli(prompt, harness=harness, model=self.model)",
     "        return self._cli(prompt, harness=harness, model=self.planner_model)"),

    ("opencode asks with the planner slot, which BEEVERFORGE_PLANNER_MODEL moves", OPENCODE,
     "        return self._cli(prompt, harness=harness, model=self.model,\n"
     "                         read_only=True)",
     "        return self._cli(prompt, harness=harness, model=self.planner_model,\n"
     "                         read_only=True)"),

    ("codex asks a project that chose no model with one this code made up", CODEX,
     "        return self._cli(prompt, harness=harness, model=self.model,\n"
     '                         sandbox_mode="read-only")',
     '        return self._cli(prompt, harness=harness, model=self.model or "made-up-1",\n'
     '                         sandbox_mode="read-only")'),
]
