# Changelog

What changed in each release of BeeverForge, for the people who install it, newest first.

Every pull request carries the line its release's notes will read for it, as a fragment in
`changes/` ([CONTRIBUTING.md](CONTRIBUTING.md)). At the final release the fragments are assembled
into the version's section here, and its GitHub release page carries the same notes
([docs/RELEASING.md](docs/RELEASING.md), "The release notes").

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
