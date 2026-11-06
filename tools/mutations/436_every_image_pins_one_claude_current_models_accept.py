"""Every image pins one `claude`, and it is a version current Claude models accept (#436).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/436_every_image_pins_one_claude_current_models_accept.py

Rows 1-3 put one install site back on 2.1.219, the refused version, alone. Row 4 declares the
fixtures on 2.1.219, the version the parser was measured on before this change. Row 5 unpins one
install. Row 6 points the fixtures at a version no image installs.
"""

TEST = "tests/test_every_image_pins_one_claude_current_models_accept.py"

BASE = "docker/base-python.Dockerfile"
WORKER = "docker/worker.Dockerfile"
CLI = "tests/claude_cli_output.py"

MUTATIONS = [
    ("the box's copy stays on the refused 2.1.219", BASE,
     "RUN npm install -g @anthropic-ai/claude-code@2.1.309",
     "RUN npm install -g @anthropic-ai/claude-code@2.1.219"),

    ("the toolbox's copy stays on the refused 2.1.219", WORKER,
     "ARG HARNESS_CLAUDE=@anthropic-ai/claude-code@2.1.309",
     "ARG HARNESS_CLAUDE=@anthropic-ai/claude-code@2.1.219"),

    ("the worker's own copy stays on the refused 2.1.219", WORKER,
     "RUN npm install -g @anthropic-ai/claude-code@2.1.309",
     "RUN npm install -g @anthropic-ai/claude-code@2.1.219"),

    ("the fixtures are declared on the refused 2.1.219", CLI,
     'PINNED = "2.1.309"',
     'PINNED = "2.1.219"'),

    ("the worker installs whatever version is latest", WORKER,
     "RUN npm install -g @anthropic-ai/claude-code@2.1.309",
     "RUN npm install -g @anthropic-ai/claude-code"),

    ("the fixtures are read from a version no image installs", CLI,
     'FIXTURES = Path(__file__).parent / "fixtures" / "claude_cli" / PINNED',
     'FIXTURES = Path(__file__).parent / "fixtures" / "claude_cli" / "2.1.219"'),
]
