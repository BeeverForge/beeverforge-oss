# Changelog

What changed in each release of BeeverForge, for the people who install it, newest first.

Every pull request carries the line its release's notes will read for it, as a fragment in
`changes/` ([CONTRIBUTING.md](CONTRIBUTING.md)). At the final release the fragments are assembled
into the version's section here, and its GitHub release page carries the same notes
([docs/RELEASING.md](docs/RELEASING.md), "The release notes").

## 0.1.3 (2026-11-20)

### Fixes

- **The board view reads a GitHub project board once, not twice.** Opening a board asked GitHub for the project's columns in one set of reads and for where each card sits in another, so every page of the board was paid for twice over. The column names now come in the same read that places the cards, so one view makes one read per hundred cards (#591).
- **A Docker daemon slow to remove a box no longer crashes the job or loses its outcome.** When `docker rm -f` on a job's box did not finish within its bound, the job errored out with a traceback before any work if the box was a leftover from an interrupted attempt, and at the end of a run the same timeout replaced the run's outcome, so a hold or an open pull request surfaced as a failed job. The removal is now tried again once after a short wait; a leftover that still will not go parks the job with one sentence naming the box and the remedy, `docker rm -f <name>`, then resume, and any other step of starting the box that times out parks it the same way. A box left behind after a run is reported once, on the card and in the log, with the same command, and the run keeps the result it reached (#608).
- **A merged job leaves its merge in the metrics.** When a job ends, its driver — the workflow and `beeverforge run`/`poll` alike — now writes one `job` row with the final state, the pull request and the platform stamp, marked `extra.ending: true` and written once, so a pull request merged by hand shows as a job that ended merged. And when the forge closed the issue before the workflow saw the merge, the card's door still records `merged` for that pull request, once, without rewriting the card. The metrics docs (`docs/reference/metrics.md`) say what an ending row is and that `card_transition` rows without `event` are effect outcomes (#609).

## 0.1.2 (2026-11-18)

### Fixes

- **A GitHub forge and tracker token held in a rotating credential store is read again during a job.** A token answered by the `file` store or an installed store was read once, when the job's runner was composed, so a job that outlived a one-hour installation token failed its final push with "Invalid username or token"; the GitHub forge and tracker now read it again every five minutes (every half lifetime under ten minutes), so a push carries the token the platform rotated in, and when the store refuses it or answers nothing once `BEEVERFORGE_STORED_TOKEN_TTL` (an hour unset) has passed since the last good read, the push refuses by name instead of using the expired token or the machine's own login; a store that fails is asked again at most once a minute, not at every call. A token from the environment, a GitHub PAT, the GitHub App trio and other vendors' tokens behave as before (#236).

## 0.1.1 (2026-11-09)

### Fixes

- **A fresh install runs a `claude` current Claude models accept.** Every image pinned `claude` 2.1.219, which current models refuse ("version 2.1.280 or newer is required"), so every harness call failed until the CLI was upgraded by hand in the worker and in the toolbox, while the installer, `doctor` and `box prove` stayed green. The box, the toolbox and the worker now pin 2.1.309. An existing deployment's toolbox keeps its old copy after the rebuild until #246 is fixed (#436).

## 0.1.0 (2026-10-28)

### Highlights

- **BeeverForge, an autonomous software factory.** It takes tickets from your board and returns reviewed pull requests: planned, implemented, validated by your own test suite, independently reviewed, and merged under the policy you chose, with production always behind a human gate (#1).
  - **It orchestrates the coding agents you already use.** Claude Code, Codex, Kimi and OpenCode run behind one adapter contract, and the reviewer can run on a different engine from the executor.
  - **Policies authorise, humans evaluate.** The manifest declares the merge policy, the quality floor and the promotion chain, and a project with no declared test command is held, not passed.
  - **The box is proven before money is spent.** `beeverforge box prove` runs your own `setup:` and `validate:` inside the real sandbox before any ticket is picked up.
  - **Every stall speaks.** A blocked job parks with executable options for a human, never a silent wait.
  - **Independent adapters, not lock-in.** Tracker, board, forge, CI observer, notifier, coding agent and sandbox are chosen per project: GitHub Issues and Projects, Jira, Azure DevOps.
  - **It runs on your machines.** One machine with no Docker and no account, or a team deployment with Docker, against your board and with your credentials, and with no telemetry.

### Upgrade notes

- **BeeverForge 0.1.0 is OpenFactory 0.7.0 under a new name.** OpenFactory was released up to 0.7.0 (`openfactory` on PyPI); this release continues that codebase as `beeverforge`, and its earlier history is at https://github.com/BeeverForge/openfactory-core (#1).

### Known limitations

- **An OpenFactory 0.7 deployment does not upgrade to BeeverForge 0.1.0 in place.** BeeverForge 0.1.0 reads none of OpenFactory's names yet: no `OPENFACTORY_*` variable, no `~/.openfactory` or `.openfactory/` directory and no `openfactory.adapters` entry point, and there is no `openfactory` command. Install BeeverForge fresh, beside the 0.7 deployment or in its place; OpenFactory 0.7 receives security fixes until BeeverForge 1.0. The upgrade in place, which reads the old names, is planned for 0.2.0 (#266).
- **On Kimi Code, the planner and read-only questions are read-only by instruction only.** `kimi-code` 0.31.1 refuses plan mode beside a prompt and has no sandbox-policy flag, so nothing but the instruction keeps those roles from writing. The planner runs on the job's own workspace, and a planner pass that writes there holds the job. The read-only questions (the sizer, the tech-lead, the product role, card drafting and judging, documents) run on the host whatever the sandbox setting, in a directory nothing commits from, except `env context --ask`, which asks in the checkout it is pointed at, where a write is left in that working tree, and the independent review, which runs in the job's box on the job's workspace before the push, where its write can reach the pull request; nothing confines a write to any of them. A per-run agent file with a `tools:` list would enforce it and is not used yet. Give the executor (which also plans), the reviewer and the judging roles another harness where that matters (#362).
- **Under a Jira `scope_jql`, the tickets the factory creates must match the scope by other means.** Its create writes only the project, summary, description and issue type, so a split's children, the product role's cards and its impediments carry no label of the scope: outside it, the poller does not pick them up, the panel and the product role do not show them, and the search for an earlier filing does not find them, so a retry files another, and a scoped project refuses to edit, close, remove, queue or rank them until they are. Scope by something every new issue of the project receives, such as a label or component a Jira automation rule sets on each issue the project's own account creates; `docs/reference/configuration.md` says how (#752).
