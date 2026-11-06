# BeeverForge — convenience targets; `make help` lists them.
# The develop and onboard targets are the core's and run in any checkout. The four CLOUD targets
# (tfvars, secrets-help, deploy, panel-url) drive the reference deployment on ONE cloud, which
# ships in the `beeverforge-aws` add-on package together with the `infra/` tree they read. Where
# that tree is present a NEW deployment goes `make tfvars` → edit it → put the secrets in SSM
# (the package's docs/DEPLOYMENT.md §4) → `make deploy`; where it is absent each of the four
# refuses BY NAME and says what to install, rather than half-running against paths that are not
# there.
.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

TFVARS ?= $(CURDIR)/infra/terraform/deployment.tfvars

# ── the cloud add-on's paths, and the refusal that stands in for them ─────────
# `infra/` and `addons/` are rows of docs/STATUS.md's excluded-paths table: the public repository
# has neither. Until 2026-08-26 the four recipes below simply ran against them, and the failures
# were the quiet kind — `make tfvars` printed `cp: infra/terraform/deployment.tfvars.example: No
# such file or directory`, echoed "created …" over that failure and exited 0; `make panel-url`
# printed a `cd` error and exited 0; `make deploy` sent the reader back to `make tfvars`. A recipe
# that reports success after a failed command is worse than one that is missing, and no recipe in
# this file does it any more: every command whose result is announced is chained to the
# announcement with `&&`.
#
# THEY STAY LISTED HERE rather than moving into the package, and that is a decision. `make help`
# is the map a reader of the public tree gets, and a target that silently vanished would leave a
# stranger with no way to learn that the reference deployment exists or where it lives — while a
# refusal that names the package is a signpost. `infra/` also sits at the repository ROOT, not
# inside the package, so a package-local Makefile would have to reach `../../infra/` and couple
# the package to its position in somebody else's tree. So each of the four refuses BY NAME with
# the package to install — the same answer `channel: slack` and `BEEVERFORGE_SANDBOX=fargate`
# already give on a deployment that does not carry their add-on.
CLOUD_PACKAGE := beeverforge-aws
CLOUD_TFVARS_EXAMPLE := infra/terraform/deployment.tfvars.example
CLOUD_TERRAFORM := infra/terraform
CLOUD_DEPLOY := infra/deploy.sh
CLOUD_GUIDE := addons/beeverforge-aws/docs/DEPLOYMENT.md

# $(call cloud-or-refuse,<path>) — the FIRST line of every cloud recipe. Names the missing path
# and the package that carries it, and exits non-zero so nothing after it runs.
cloud-or-refuse = if [ ! -e "$(1)" ]; then \
	  echo "make $@: $(1) is not in this tree." >&2; \
	  echo "  The reference deployment on one cloud — its terraform, its deploy script and its" >&2; \
	  echo "  walkthrough — ships in the $(CLOUD_PACKAGE) add-on package." >&2; \
	  echo "  pip install $(CLOUD_PACKAGE)   (or use a checkout that carries $(1))" >&2; \
	  exit 1; fi

.PHONY: help
help: ## show these targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── develop ──────────────────────────────────────────────────────────────────
.PHONY: install test lint check
install: ## install the package + dev tools (+ the add-on packages under addons/, where they exist)
	pip install -c constraints.txt -e '.[dev]'
	@for d in addons/*/; do if [ -f "$$d/pyproject.toml" ]; then pip install -c constraints.txt -e "$$d"; fi; done

test: ## run the test suite
	python -m pytest -q

# ── the suite as CI runs it: parallel jobs, and the proof that every test ran once ──────────────
# CI splits the suite into jobs that run side by side (.github/workflows/ci.yml): the tests that
# start their own durable engine or need Docker (`owns_its_engine`, `slow`), then the few that
# assert their own CPU time (`alone`) in a process of their own, and the rest in
# TEST_SHARDS slices. Every job writes the node ids it started to TEST_IDS, the lint job writes
# the whole collection, and `test-ran-once` fails on a test that is missing, doubled or unknown —
# so a test added tomorrow cannot fall between two jobs. The same targets run here, one at a time
# or a slice at a time: `make test-unit TEST_SHARD=2 TEST_SHARDS=3`.
INTEGRATION_TESTS := owns_its_engine or slow
ALONE_TESTS := alone
# OUTSIDE THE TREE: a test that scans the tree would read the ids while they are written.
TEST_IDS_DIR ?= $(or $(RUNNER_TEMP),$(TMPDIR),/tmp)/beeverforge-test-ids
.PHONY: test-collect test-unit test-integration test-alone test-ran-once
# The listing goes to a file, not the terminal: printed, 17,000 lines took five of the job's six
# minutes on GitHub's runner while the collection itself took forty seconds.
# THE BARE CONSOLE SCRIPT (#350). This is the one collection of the whole tree CI makes, so it is
# the one that asks the whole-tree question the unit guards in tests/test_ci_runs_what_we_run.py
# now ask of a subset (#336): does `pytest`, not `python -m pytest`, collect every module
# (2026-08-05: it died on `No module named 'tests'`)? A module that fails only under the console
# script, outside the plugin subset, fails this job. No toy-project setting is needed here:
# tests/conftest.py strips every `BEEVERFORGE_*` variable and re-homes HOME before collection, so
# every collection, this one included, is already one without the toy projects.
test-collect: ## write the node id of every test the suite collects to TEST_IDS
	@mkdir -p $(TEST_IDS_DIR)
	pytest -q --collect-only -p no:randomly $(if $(TEST_IDS),--record-ids=$(TEST_IDS)) > $(TEST_IDS_DIR)/collect.log 2>&1 || { tail -50 $(TEST_IDS_DIR)/collect.log; exit 1; }
	@tail -1 $(TEST_IDS_DIR)/collect.log

test-unit: ## the tests that start no engine and need no Docker, in parallel (TEST_SHARD/TEST_SHARDS: one slice; TEST_COVERAGE=1: measure)
	$(if $(TEST_COVERAGE),$(if $(TEST_SHARDS),,rm -rf $(COVERAGE_DIR) && )mkdir -p $(COVERAGE_DIR) && COVERAGE_FILE=$(COVERAGE_RUN_DATA) )python -m pytest -q -n auto -m "not ($(INTEGRATION_TESTS) or $(ALONE_TESTS))" --durations=15 $(if $(TEST_SHARDS),--shard=$(TEST_SHARD)/$(TEST_SHARDS)) $(if $(TEST_IDS),--record-ids=$(TEST_IDS)) $(if $(TEST_COVERAGE),$(COVERAGE_ARGS))

# `--dist loadgroup`: the tests on the real Docker daemon share compose projects, so they carry
# `xdist_group("docker")` and run on one worker, one after another; the rest spread as before.
test-integration: ## the tests that start their own durable engine, and the slow ones that need Docker
	python -m pytest -q -n auto --dist loadgroup -m "$(INTEGRATION_TESTS)" --durations=15 $(if $(TEST_IDS),--record-ids=$(TEST_IDS))

test-alone: ## the tests that assert their own CPU time, in one process with no xdist neighbours
	python -m pytest -q -p no:xdist -m "$(ALONE_TESTS) and not ($(INTEGRATION_TESTS))" $(if $(TEST_IDS),--record-ids=$(TEST_IDS))

test-ran-once: ## fail unless every collected test was started exactly once across CI's jobs
	python scripts/every_test_ran_once.py $(TEST_IDS_DIR)/collected.txt $(wildcard $(TEST_IDS_DIR)/ran-*.txt)

# ── the coverage floor (#334) ────────────────────────────────────────────────────────────────────
# WHAT IS MEASURED: `beeverforge/` (lines and branches, `[tool.coverage.*]` in pyproject.toml) under
# the UNIT selection — `test-unit` with TEST_COVERAGE=1, the same marker expression, so the figure
# and CI's four unit slices measure one thing. The integration and alone runs are not in it: they
# start engines and Docker, and a floor that a missing daemon could lower would be red for a
# reason no change made. Code a test reaches only in a SUBPROCESS (the CLI driven as a command, a
# probe pytest) is not counted either — pytest-cov 7 traces the test processes alone — so the
# figure under-reads the suite, and holds as a floor all the same: what it misses, it misses on
# every run alike.
#
# WHAT IT COSTS, ON THE RUNNERS THAT PAY IT (#344 review): the `make test-unit` step of each of
# CI's four unit slices (GitHub's ubuntu-latest, 4 cores), 2026-11-01, in seconds —
#
#                                                   slice 1  slice 2  slice 3  slice 4
#     unmeasured, main at b5f2742 (run 41302814099)   203      263      258      258
#     measured, run 41322787942                       331      281      487      490
#     measured, run 41323669639 attempt 1             410      459      501      347
#     measured, run 41323669639 attempt 2             417      467      507      474
#
# — 1.1x to 2.1x per slice, median 1.9x, and the slowest slice from 263 s to 487–507 s. Locally
# (12 cores, `-n auto`) `make test-unit` took 335–376 s and `make coverage` 528–639 s. coverage.py
# traces with its C tracer: on Python 3.12 the cheaper sys.monitoring core cannot measure branches.
# So the measurement is NOT on every run — plain `make test-unit` stays as it was — and CI pays it
# ON PUSHES TO MAIN ONLY, never on a pull request: a pull request keeps its speed, and the floor
# is held right after each merge, where a red names the merge that lowered it. `make coverage` is
# how to hold it BEFORE a merge. On main it is paid in the unit slices CI already runs, not in a
# job of its own: a fifth job would run the whole selection a second time, alone, at nearly twice
# its cost, to learn what the four slices already executed.
#
# OUTSIDE THE TREE, like TEST_IDS_DIR: a data file appearing in the checkout mid-run is a file a
# tree-scanning test can trip over, and it names the paths of whoever ran it.
#
# `--cov-fail-under=0` ON THE RUN, because pytest-cov reads `fail_under` from the config and would
# hold ONE SLICE to the whole suite's floor — every CI slice would be red. The floor is applied
# once, to the combined data, by `coverage-report`. `--cov-report=` keeps the per-run table out of
# the slices' logs; the combined report prints it once.
#
# ONE FILE PER RUN, NAMED BY ITS SLICE: pytest-cov's xdist controller combines its workers into the
# exact file COVERAGE_FILE names, so four slices writing `coverage` would overwrite one another
# when CI downloads them into one directory. `coverage-report` combines every `coverage.*` there.
# A WHOLE run empties the directory first — it supersedes every slice, and a slice left over from
# last week combined into today's figure would make a stale number look like a measured one.
COVERAGE_DIR ?= $(or $(RUNNER_TEMP),$(TMPDIR),/tmp)/beeverforge-coverage
COVERAGE_RUN_DATA = $(COVERAGE_DIR)/coverage.unit$(if $(TEST_SHARDS),-$(TEST_SHARD)-of-$(TEST_SHARDS))
# THE COMBINED FILE SITS IN A DIRECTORY OF ITS OWN. coverage.py 7.17's `report` also combines — and
# DELETES — every `coverage.*` beside the file it reads, and earlier 7.x releases do not; read from
# here, it finds no slice to fold in, so the report says the same on every version and a second
# `make coverage-report` re-reads the slices instead of finding them gone.
COVERAGE_COMBINED = $(COVERAGE_DIR)/combined/coverage
COVERAGE_ARGS := --cov --cov-report= --cov-fail-under=0
.PHONY: coverage coverage-report
coverage: ## measure the unit tests' coverage of beeverforge/ and hold it to the floor in pyproject.toml
	$(MAKE) --no-print-directory test-unit TEST_COVERAGE=1
	$(MAKE) --no-print-directory coverage-report

# coverage.py names both numbers itself ("Coverage failure: total of X is less than
# fail-under=Y") and exits 2; the sentence after it says what to do, since that line alone reads
# like a tool error to somebody who has never seen the floor. Any other exit is coverage's own
# error and passes through as it is. An EMPTY directory is refused by name rather than reported as
# 0% under the floor: no data is a run that did not happen, not a run that covered nothing.
coverage-report: ## combine the coverage data in COVERAGE_DIR and fail below the floor
	@mkdir -p $(dir $(COVERAGE_COMBINED)) && COVERAGE_FILE=$(COVERAGE_COMBINED) python -m coverage combine --keep $(COVERAGE_DIR) \
	  || { echo "make $@: there is no coverage data to combine in $(COVERAGE_DIR) — run \`make coverage\`, or \`make test-unit TEST_COVERAGE=1\` once per slice, first." >&2; exit 1; }
	@COVERAGE_FILE=$(COVERAGE_COMBINED) python -m coverage report --skip-covered --sort=cover; rc=$$?; \
	  if [ $$rc -eq 2 ]; then \
	    echo "make $@: coverage of beeverforge/ fell below the floor in pyproject.toml ([tool.coverage.report] fail_under) — cover what this change left unexecuted (\`python -m coverage report -m\` names the lines), or lower fail_under and its figure in docs/STATUS.md together and say why in the pull request." >&2; \
	  fi; exit $$rc

# ── shellcheck, and why it is not a CI-only step ─────────────────────────────
# `install.sh` is the first thing a stranger runs and the one artefact in this repository that no
# Python test can execute. It belongs in `make lint` rather than in a job of its own, because
# `tests/test_ci_runs_what_we_run.py` exists precisely to stop CI and the gate drifting apart —
# it derives the roots the suite covers and holds CI to them, after the two differed by one word
# (`ruff check beeverforge/ tests/` here, `… addons/` there) and the add-on packages went unlinted
# where it counted. A CI-only shellcheck step would re-create that gap in a new place: green on
# every laptop, and the only machine that ever checked the script would be the one nobody runs
# locally.
#
# LOCAL FIRST, THEN THE CONTAINER, THEN A REFUSAL BY NAME. shellcheck is a Haskell binary, not a
# Python dependency, so `make install` cannot provide it and most machines do not have it —
# measured on this one, 2026-08-30: absent, with no sudo available to install it. Silently
# skipping would be the worst of the three outcomes: `make lint` would pass while checking
# nothing, which is the "absence read as compliance" shape this codebase has been bitten by more
# than once. So it runs whichever it can find and refuses BY NAME when it can find neither,
# naming both ways to fix it — the same shape the four cloud targets above use for `infra/`.
SHELLCHECK_IMAGE := koalaman/shellcheck:stable
SHELL_SCRIPTS := install.sh docker/install-addons.sh $(wildcard scripts/*.sh)

shellcheck-or-refuse = \
	if command -v shellcheck >/dev/null 2>&1; then \
	  shellcheck -s sh $(1); \
	elif docker info >/dev/null 2>&1; then \
	  docker run --rm -v "$(CURDIR):/mnt" $(SHELLCHECK_IMAGE) -s sh $(addprefix /mnt/,$(1)); \
	else \
	  echo "make $@: shellcheck is not installed, and no Docker daemon is available to run it." >&2; \
	  echo "  These are POSIX sh and CI checks them either way — to check them here, do one of:" >&2; \
	  echo "    install shellcheck   (apt/brew/dnf install shellcheck, or https://www.shellcheck.net)" >&2; \
	  echo "    start Docker         (this then runs $(SHELLCHECK_IMAGE))" >&2; \
	  exit 1; \
	fi

lint: ## ruff over the package and the suite; shellcheck over the shell scripts that ship
	ruff check beeverforge/ tests/ $(wildcard addons)
	@$(call shellcheck-or-refuse,$(SHELL_SCRIPTS))

check: test lint ## test + lint (what deploy runs first)

# ── the product role's evaluation battery (#266 slice 0) ─────────────────────
# A LIVE MODEL ANSWERS IT, which is why it is a target of its own and never a prerequisite of
# `test` or `check`: every run spends tokens, and a suite that paid a model on each commit would
# be skipped within a week. The suite drives the same runner with the model scripted, and holds
# both halves of this rule — the recipe below is not reached from `test`, and the runner refuses a
# live run inside pytest (tests/test_the_evaluation_battery.py). The questions are the product
# owner's to write (ADR-0051 decision 9); with none, this refuses and says so.
.PHONY: eval-product
eval-product: ## ask the product role the evaluation battery — LIVE model, spends tokens
	python -m beeverforge.product.evaluation

# ── run the code in THIS checkout instead of the published images ────────────
# `docker compose up -d` PULLS `ghcr.io/beeverforge/beeverforge-*` — that is the
# installer's path and it is what almost every user wants (ADR-0043). A contributor wants the
# opposite, and the difference is one profile plus one flag, which is exactly the kind of
# incantation that ends up half-remembered in three documents.
#
# THE PROFILE IS NOT OPTIONAL AND THAT IS THE WHOLE REASON THIS TARGET EXISTS. `base-image` and
# `sandbox-image` sit behind `profiles: ["build"]` so the installer's `up` does not build a
# multi-GB box it could have pulled; without `--profile build` this command would quietly build
# the worker and the panel ALONE and leave the box image absent, which surfaces at the first
# ticket rather than here. `beeverforge preflight` names that state, but a build command that
# creates it by omission is a trap this file can simply not set.
.PHONY: build
build: ## build the images from THIS checkout and run them (contributors; users just `up -d`)
	@if [ ! -f .env.compose ]; then \
	  echo "make $@: no .env.compose in this directory." >&2; \
	  echo "  The stack reads its environment from that file and compose refuses a missing" >&2; \
	  echo "  --env-file rather than starting with none." >&2; \
	  echo "  beeverforge init            (or: cp .env.compose.example .env.compose)" >&2; \
	  exit 1; fi
	docker compose --env-file .env.compose --profile build up -d --build

# ── bootstrap a new deployment (the cloud add-on) ────────────────────────────
.PHONY: tfvars secrets-help
tfvars: ## create deployment.tfvars from the template (needs the beeverforge-aws tree)
	@$(call cloud-or-refuse,$(CLOUD_TFVARS_EXAMPLE))
	@if [ -f "$(TFVARS)" ]; then echo "$(TFVARS) already exists — edit it, don't clobber."; \
	else cp "$(CLOUD_TFVARS_EXAMPLE)" "$(TFVARS)" \
	     && echo "created $(TFVARS) — fill it in (app id, installation, temporal, brand)."; fi

secrets-help: ## the SSM put-parameter commands for this deployment (needs the beeverforge-aws tree)
	@$(call cloud-or-refuse,$(CLOUD_GUIDE))
	@echo "Put these in THIS account's SSM (see $(CLOUD_GUIDE) §4):"
	@echo "  /<prefix>/bot-app-private-key   (the GitHub App .pem)"
	@echo "  /<prefix>/temporal-api-key      (Temporal Cloud API key)"
	@echo "  /<prefix>/claude-oauth-token    (Claude Code token)  and/or  /<prefix>/agent-tokens"
	@echo "  /<prefix>/panel-token           (invent a long random string)"
	@echo "  /beeverforge/slack-token-<project>     (Slack bot xoxb- token, ONE per project's workspace;"
	@echo "                                   OPTIONAL. Map it in slack_bot_tokens in deployment.tfvars,"
	@echo "                                   e.g. { SLACK_BOT_TOKEN = \"/beeverforge/slack-token-<project>\" })"

# ── deploy (the OTA) ─────────────────────────────────────────────────────────
.PHONY: deploy panel-url
deploy: ## build + roll THIS deployment (AWS creds + a deployment.tfvars + the beeverforge-aws tree)
	@$(call cloud-or-refuse,$(CLOUD_DEPLOY))
	@if [ ! -f "$(TFVARS)" ]; then echo "no $(TFVARS) — run 'make tfvars' and fill it in first." >&2; exit 1; fi
	BEEVERFORGE_TFVARS="$(TFVARS)" $(CLOUD_DEPLOY)

# `terraform` is checked BY NAME too. `cd $(CLOUD_TERRAFORM) && terraform output …` failed
# identically whether the directory was missing, the binary was absent or nothing was deployed
# yet, and answered all three with "(deploy first)" — a remedy that sends two of those three
# readers to fix the wrong thing.
#
# That message names the PACKAGE and not its guide's path, deliberately: it prints on the way
# past the refusal above, and a path under `addons/` is one more thing a reader who got here
# without the add-on cannot open.
panel-url: ## print the panel URL, after a deploy (needs the beeverforge-aws tree)
	@$(call cloud-or-refuse,$(CLOUD_TERRAFORM))
	@command -v terraform >/dev/null 2>&1 \
	  || { echo "make $@: terraform is not installed — the $(CLOUD_PACKAGE) walkthrough §1 lists what a deploy needs." >&2; exit 1; }
	@url=$$(cd "$(CLOUD_TERRAFORM)" && terraform output -raw panel_apprunner_url 2>/dev/null) \
	  && [ -n "$$url" ] && echo "$$url" \
	  || echo "no panel_apprunner_url in the terraform state — deploy first."

# ── onboard a project ────────────────────────────────────────────────────────
# usage: make onboard NAME=myapp DIR=~/Projects/myapp REPO=yourorg/myapp
.PHONY: onboard
onboard: ## register + scaffold a project (NAME=, DIR=, REPO=)
	@if [ -z "$(NAME)" ] || [ -z "$(DIR)" ] || [ -z "$(REPO)" ]; then \
	  echo "usage: make onboard NAME=myapp DIR=~/Projects/myapp REPO=yourorg/myapp"; exit 1; fi
	beeverforge project add "$(NAME)" "$(DIR)" --repo "$(REPO)"
	beeverforge project init "$(NAME)"
	beeverforge conformance "$(NAME)"
