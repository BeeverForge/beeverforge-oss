# What works today

Read this before deciding anything. It is ordered by what would stop you, not by what is
impressive.

This page describes the `v0.1.0` tag of `beeverforge-oss`. Its claims were checked against the
code at main at `171de5f` of `beeverforge-oss`, where CI ran 24,161 tests green (228 skipped) on
2026-10-26.

BeeverForge 0.1.0 is OpenFactory 0.7.0 under a new name; its earlier history is at
<https://github.com/Open-Factory-Digital/openfactory-core>.

> **This is the one page that carries a count.** Other documents link here rather than type a
> number (`tests/test_the_docs_do_not_drift.py` holds that rule), so a stale count can only be
> stale here. No guard measures the count against the tree: it is copied from the CI run named
> above.

---

## Measured on the maintainers' deployments

Measured on **2026-10-27**, over the previous 30 days, from the factory's own records on the
deployments the maintainers run. The costs are **model usage only** (no infrastructure), and a
card is a card of the size those teams write. A card "in one pass" was merged after a single
implementation pass, with no repair pass.

| source | cards done | model cost per card | in one pass | factory time per card |
|---|---|---|---|---|
| a closed-source product repository (Python/TypeScript); local deployment: local tracker, GitHub forge, Claude Code | 102 | median $3.40, p90 $6.94 | 82 of 101 | median 26 min |
| this repository's predecessor (the same code under its former name); same deployment | 12 | median $8.64 | 3 of 11 | median 88 min |
| a client's Django application; production deployment on a 2 GB VM | 12 | median $4.48, p90 $11.04, total $52.75 | 6 of 10 | median 42 min |

On the client's application, the median time from pull request to merge was 1.7 h. 7 of the 12
pull requests merged by policy with no human step and 5 needed a person. The job was parked twice
on an out-of-memory kill (exit 137) instead of reporting success, and twice refused to open an
empty pull request.

These numbers are not repeated anywhere else in the documentation.

---

## What you can check yourself

**`beeverforge doctor`.** One line per check, each with its own remedy: Docker, the harness, the
manifest, forge access, the deployment's installation scope, the board's columns, the merge gates,
and, where they apply, the agent credential, the declared CI checks, the box proof and the API
budget ([the CLI reference](reference/cli.md#beeverforge-doctor-project) lists them). Run it
first; it is the fastest way to find out which of the gaps below applies to you.

**One machine.** With `local` on tracker, forge and board and `none` on CI, a git repository and a
signed-in coding agent run the whole cycle (card, branch, gates, independent review, pull request,
merge) with no account anywhere and no Docker. The pull requests and the board live in one SQLite
file beside the registry, so nothing is shared between machines. [setup/one-machine.md](setup/one-machine.md)
walks it.

**The compose stack.** `docker compose up` brings up the durable engine, a worker, the panel and
the box image on one machine, with no cloud account. Telemetry goes to a SQLite file
(`BEEVERFORGE_METRICS_SINK=sqlite` in the compose file), and the cost dashboard reads the same
file.

---

## The provider axes

[ADR-0022](adr/0022-provider-seams.md)'s rule is that *an axis is agnostic when it is born with
two*. Where an axis has one implementation, the table says so.

| axis | implementations | notes |
|---|---|---|
| tracker | GitHub, **Jira**, **Azure DevOps**, **local** | refs are opaque strings, because Jira's are not integers |
| forge | GitHub, **Azure Repos**, **local** | branches, pull requests, merges, tags. GitLab is not implemented; `gitlab` is refused by name |
| board | GitHub Projects v2, **Azure Boards**, **local** | plus Jira, where the workflow status is the board |
| CI / environment | GitHub Actions, **Azure Pipelines**, **none** | observation on both. One action on GitHub Actions only: a CI repair re-runs the failed jobs of a red required check whose log names no changed file ([ADR-0004](adr/0004-ci-aware-autonomous-repair.md)). That re-run is proven by fakes and by one measurement against the real `gh` (2.102.0, 2026-10-20), not end to end. Azure Pipelines re-runs nothing |
| agent | Claude Code, Codex, Kimi, **OpenCode** | four, selectable per role and per model (`model:`) |
| sandbox | worktree, container, `fargate` (add-on) | worktree and container are built in. `fargate` is described by the core (its traits are a row) and run by the `beeverforge-aws` add-on through the `box_runner.fargate` entry point; without the add-on the kind is refused by name |
| channel | panel, Slack (add-on) | the panel is the reference surface ([ADR-0038](adr/0038-the-platform-is-complete-channels-are-add-ons.md)); Slack is the `beeverforge-slack` add-on |
| telemetry | SQLite, null, in-memory | SQLite when `BEEVERFORGE_METRICS_SINK=sqlite` (the compose file sets it), null otherwise; DynamoDB is an add-on row |
| events | file journal, stdout, tee, in-memory, null | the file journal is the local default |

The Jira and Azure DevOps adapters have each run against a live instance, under the former
name. Jira, on 2026-08-05: a ticket
crossed from the board to a merged pull request. Azure DevOps, on 2026-08-06: work items read and
moved, pull requests opened in Azure Repos, pipelines observed. The Azure DevOps setup path is
[docs/setup/azure-devops.md](setup/azure-devops.md).

---

## Known gaps

**Principles the documents state and the code does not yet meet.** These are aims, written here so
nobody reads them as facts.

- **"Born with two"** ([ADR-0022](adr/0022-provider-seams.md)). `channel`, `notifier`,
  `session_store` and `token_pool` have one built-in row each, `box_runner` has none, and no test
  enforces the rule.
- **Least privilege.** The manifest's `permissions` field is accepted and has no effect: no call
  site reads it, and the loader lists it among the inert keys (`beeverforge/loader.py::_INERT`).
  The box's isolation and `box.env` are what bound a run.
- **The quality floor.** `policy/floor.py` checks that a `test` and a `security` validation exist.
  It does not check what they run: a project can declare either one with any command, and the
  `security` gate a project inherits from `org_defaults/floor.yaml` is `advisory: true`. A project
  with no `test` command is held before any agent runs, and there is no switch that turns the
  floor off.
- **`JobState`** (`contracts/state.py`) has no transition table. `ci_waiting` and
  `staging_deploying` are never assigned, `ready` is only a board mapping, and `blocked` is used
  for decision parks rather than dependencies.
- **"The core names no vendor."** The AST guard (`tests/test_kernel_names_no_vendor.py`) covers
  `contracts/` and `policy/` only, and the metrics sink is inferred as `dynamodb` when
  `BEEVERFORGE_METRICS_TABLE` is set (`observability/registry.py::metrics_sink_kind`).
- **Contributor rules CI does not run.** `mypy` and `bandit` are configured in `pyproject.toml`
  and run by neither `make ci` nor `.github/workflows/ci.yml`.

**The box proof gates pickup on the `container` box, and on `worktree` only where the worker is
declared to be somebody's own machine** (`BEEVERFORGE_OWN_WORK`). `beeverforge box prove` resolves
the image digest, checks the image contract and that the toolbox runs in that image, runs the
project's own `setup:` and `validate:` on untouched main, and probes the harness's auth route;
on a box with no image that probe asks the harness one read-only question, which costs tokens.
`box_prove.gate_reason` returns no reason for any other box (a `worktree`
elsewhere, or the add-on's `fargate`), so there the proof is something an operator runs by hand.

**`box.image` is honoured by the container box only.** The `worktree` box has no image.

**The box has full outbound internet by default** (`network: bridge`, `contracts/project.py`). A
deployment that wants less names a restricted network or a proxy in `box.network`; anything that
network can reach is reachable by code the agent wrote.

**One deployment serves one GitHub organisation.** A GitHub App installation belongs to one
organisation, and the forge credential is process-wide. `beeverforge project add` refuses a
project in a second organisation, a hand-edited registry that spans two logs
`BEEVERFORGE_REGISTRY_SPANS_INSTALLATIONS` on every load, and `beeverforge doctor` fails its
`installation_scope` line for either. The load warns rather than refusing, so one stale line does
not stop every project. The rule and how to run one deployment per organisation are in
[configuration.md](configuration.md#one-deployment-one-github-organisation).

**A project registered by local path needs the repository on the worker's own disk.** A project
registered by clone URL is fetched into the worker's repository cache, private repositories with
the forge credential; a local path is read where it is, which in compose means a mounted checkout.

**The `setup:` and `validate:` commands are shell strings and only the exit code is read.** That
is what makes any stack work, and it is the whole extent of the integration: there is no
stack-specific intelligence beyond the presets' command tables.

**The reviewer is handed no decision records.** A job's prompt is bounded by one budget
(`BEEVERFORGE_PROMPT_BUDGET`, 160,000 bytes unless the operator sets another, or `off`) shared by
the card, the plan, a repair's failure log and the documents; the project's guidelines are kept
first, decision records newest first, and every document left out is named in the prompt by its
path ([ADR-0056](adr/0056-a-prompt-has-one-budget-and-names-what-it-leaves-out.md)). Nothing fills
the reviewer's `constraints` today.

**The knowledge layer is on by default, and the measurement behind that is not published.**
`knowledge_map` defaults to `true` ([ADR-0035](adr/0035-knowledge-layer-on-by-default.md)); the map
is handed to the agent only when its checksums match the job's own checkout, and otherwise nothing
is handed. Publishing the map needs `product.docs_repo`. Nothing on this page compares cost with
the map on and off, and ADR-0035 itself asks the first enterprise deployment to retake the
measurement.

---

## Deliberately not built

Decisions, each with an ADR.

- **Production deploys are never triggered from chat.** Production needs an approver in the panel
  ([ADR-0016](adr/0016-slack-actions-authorization.md)).
- **The bot never gets the `workflows` permission.** CI/CD stays human-only: an agent's change
  under `.github/workflows/` is dropped before the commit, and the drop is recorded on the job
  rather than lost in silence (`orchestrator/machine.py`).
- **Review is advisory by default** (`review_mode: advisory`). It comments and does not block
  ([ADR-0014](adr/0014-single-agent-execution-and-advisory-review.md)). A rejection with concrete
  findings triggers a repair pass; a vague one goes to a human.
- **One job at a time, deployment-wide, by default.** The floor frees at merge, not when the agent
  finishes, so the next ticket builds on a base that contains the last one
  ([ADR-0007](adr/0007-floor-frees-at-merge.md)). The slot count is
  `BEEVERFORGE_MAX_CONCURRENT_JOBS` (default 1), counted across all projects; raising it adds
  parallelism with no per-project cap.
- **Cross-repository ordering does not exist.** Two repositories are two floors; nothing stops a
  front-end ticket merging before the API it depends on. Designed in
  [ADR-0036](adr/0036-cross-repo-ordering.md), not built.

---

## What the public repository contains

This repository is the core. A few paths of the maintainers' own source tree are not in it: the
cloud realisation, the chat connectors and some internal documents. The table is the one place
those paths are written down, and `tests/test_the_public_cut_is_written_down.py` holds it to the
tree and to the ledger in [docs/core/07-extensibility.md](core/07-extensibility.md) §10. Azure DevOps
and Jira stay in the core beside GitHub. A vendor that is not here is installed from outside
through the `beeverforge.adapters` entry-point group (§2 of the same page).

| not in this repository | where the capability comes from instead |
|---|---|
| `addons/` | the add-on packages, each installed beside the core as its own wheel; the documents of the deployment a package carries are in that package |
| `infra/` | `beeverforge-aws` — the reference deployment on one cloud (its walkthrough and runtime document are that package's `docs/DEPLOYMENT.md` and `docs/runtime-architecture.md`) |
| `beeverforge/runtime/fargate/` | `beeverforge-aws` — the cloud box (`box_runner.fargate`) and the token pool (`token_pool.ssm`) |
| `beeverforge/observability/dynamo.py` | `beeverforge-aws` — the managed metrics table (`metrics.dynamodb`) |
| `beeverforge/adapters/agent/s3_session_store.py` | `beeverforge-aws` — the remote session store (`session_store.s3`) |
| `beeverforge/runtime/slack/` | `beeverforge-slack` — the chat channel's runtime |
| `beeverforge/adapters/channel/slack.py` | `beeverforge-slack` — the channel adapter |
| `beeverforge/adapters/notify/slack.py` | `beeverforge-slack` — the channel's push half |
| `beeverforge/adapters/notify/telegram.py` | `beeverforge-slack` — the deployment-wide fallback notifier (`notifier.telegram`), reached when `BEEVERFORGE_NOTIFIER_FALLBACK=telegram` declares it |
| `docs/core/01-reality-check.md` | a dated audit of this tree; `docs/STATUS.md` answers the same question and a guard keeps it current |
| `docs/core/03-extraction-strategy.md` | the plan for making this cut; the four anti-patterns it wrote down are in `CONTRIBUTING.md` |
| `docs/core/04-business-and-licensing.md` | `NOTICE` carries the licence-and-mark rule a user needs, and `docs/core/07-extensibility.md` §2 the rule that the open build is never hobbled |
| `docs/core/05-open-questions.md` | the answers are in `LICENSE`, `NOTICE`, `CONTRIBUTING.md` and `docs/STATUS.md` |
| `docs/core/06-onboarding-and-project-shape.md` | `docs/ONBOARDING.md` §10 carries the project shape in the present tense, and `docs/architecture.md` §5 the egress a security review asks for |
| `docs/site-guide.md` | website copy source; `README.md` and this page are the public claims |

**Removing them is a directory delete.** Every row of the two add-on packages registers through
the entry-point group, and the core's own `pyproject.toml` declares none.
`tests/test_the_cloud_is_a_directory_delete.py` and `tests/test_the_chat_is_a_directory_delete.py`
prove the core imports and every registry answers without them, and that a project declaring
`channel: slack` on a deployment without `beeverforge-slack` is refused by name, naming the package
and the `channel.slack` entry point any package must declare to answer for it
(`beeverforge/plugins.py::install_hint`). `adapters/channel/registry.py` and
`adapters/notify/registry.py` hold the panel and nothing else.

**The deployment-wide fallback notifier is declared, never inferred.** Setting
`BEEVERFORGE_TELEGRAM_BOT_TOKEN` and `BEEVERFORGE_TELEGRAM_CHAT_ID` alone switches nothing on: the
two are read by the `notifier.telegram` row only, and that row is reached only when
`BEEVERFORGE_NOTIFIER_FALLBACK=telegram` declares it (with `beeverforge-slack` installed). Without
the declaration, notifications with no project go nowhere. `beeverforge doctor` prints the
fallback state as one line and, when a notifier is installed and not declared, names the line to
add.
