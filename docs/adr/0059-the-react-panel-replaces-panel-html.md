# ADR 0059 — The panel is rebuilt in React on the public API, and it replaces `panel.html`

- **Status:** Accepted (decided 2026-11-16 on #547; built by the issues of #546, none merged yet)
- **Date:** 2026-11-17
- **Implements:** #547, for #546.
- **Relates to:** [ADR-0038](./0038-the-platform-is-complete-channels-are-add-ons.md) D1 (the panel
  is the reference surface), [ADR-0043](./0043-the-distribution-is-a-published-image.md) (the
  distribution is a published image), and the references to `panel.html` in
  [ADR-0039](./0039-the-action-layer.md), [ADR-0051](./0051-one-door-parallel-conversations-one-semaphore-on-work.md)
  and [ADR-0052](./0052-the-owners-view.md), which D8 supersedes.

## Context

The default front end is one file, `beeverforge/api/panel.html`: about 6,000 lines, 408 KB (131 KB
gzip), every surface in it. Measured on one simulated floor over a minute at rest, it makes 51 API
requests on the floor page and 23 on a line's page, because it re-reads on timers while two event
streams and two sockets are open. axe finds serious problems on both pages.

A React panel was built beside it on the public API only (the `/api/v1/` reads, the catalogued
actions, the two SSE streams and the two sockets): 2 requests a minute on both pages, no axe
serious or critical finding on the floor, a line, the board or the product room, about 140 KB gzip
of JavaScript on first load. It lives on a local branch and has only met a simulator. #546 proposes
that it replace the page. The work cannot start until the choices below are fixed.

## Decision

**The React panel replaces `panel.html`. The two run side by side only until the switch, then for
one release behind a setting, then the old page goes.**

### D1 — It lives at `panel/`, its final name

The app sits at the repository root as `panel/`, from its first commit on `main` (#548). Nothing is
renamed at the switch. It is a standalone app (Vite, React 19, TypeScript, TanStack Query and Router,
Radix) and talks to the server through the public API only. Until #553 serves it, it is
development-only code: not served, not in the wheel, not in an image.

### D2 — Node 24 LTS and npm, pinned

`panel/package.json` declares `engines`, `panel/.nvmrc` names the version, and
`panel/package-lock.json` is committed. A contributor runs `npm ci` in `panel/`, then `npm start`
(the rig and the simulator) or `npm run dev:live` (against a deployment). `make` wraps the checks
(#549), and a machine without Node is refused by name, as shellcheck is, never skipped.

### D3 — The dependency tree is held strictly

- Installs are `npm ci` from the lockfile, in CI and in the images.
- Install scripts are blocked, except an allowlist (esbuild today).
- CI fails on a high or critical `npm audit` finding.
- A new runtime dependency states its reason in the pull request that adds it.

### D4 — Built in CI, never committed; no Node to install or run

The release builds the panel before the wheel, and the wheel carries the built files as package
data. The images build it in a Node stage and keep no Node at runtime. `install.sh` needs nothing
new. A checkout needs one build command, and refuses by name, naming that command, when it has not
been run (#554).

### D5 — The promises the old page's guards hold move by kind

78 test files read or name `panel.html` (#559–#562). Each promise moves to the check that fits it:

- **What the page shows or does** becomes a Playwright test (#551).
- **A rule about text** (no vendor name, no former product name, no copy of a list the server owns)
  stays Python, reading `panel/src` and the built files, never `node_modules`.
- **A promise the new design cannot break** is retired, with the reason in the pull request.

Logic with no page (the stream merge, the station model) is a unit test in `panel/`.

### D6 — One release of fallback, through the existing setting

At the switch (#565) every page address serves the new panel. For one release, a documented value
of `BEEVERFORGE_DEFAULT_FRONT_END` serves `panel.html` instead; `off` still serves no page. One
release later `panel.html` and that value are deleted together (#566).

### D7 — The rig and the simulator are tooling, then they go

The rig (this checkout's API with a registry, board and home of its own, and no engine) and the
factory simulator (the routes only an engine and a worker can answer) stay as development and CI
tooling until the switch, held to `docs/reference/openapi.json` and `events.schema.json` (#550).
They are removed in #566. Before that, the browser tests move to the real API and a real engine in
CI (#572), so they never lose what they run against.

### D8 — This record supersedes the references to `panel.html`; ADR-0038 is not edited

ADR-0038 D1 stands: the panel is the reference surface. From the switch, the panel it names is this
one. Where ADR-0039, ADR-0051 and ADR-0052 cite `panel.html` (a function, a line, a timer), they
describe the page as it was when they were written, and this record supersedes those references.
None of the three, and not ADR-0038, is rewritten.

### D9 — The proof of concept's container files are not merged

The files that packaged the proof of concept as a `poc-panel` service on port 5180 are dropped with
#548. The panel reaches a deployment the way `panel.html` does, through the API's own process (#553).

## What this does NOT mean

- **Not two panels for good.** Both exist only between #548 and #566.
- **Not a change to the API for the panel's sake.** A word the server owns that the panel needs is
  published by the server (#552), as a contract any front end may read.
- **Not Node on a deployment.** D4 keeps it at build time.
- **Not #272.** Whether the reference surface becomes the action catalogue and the typed read
  models is that issue's decision. A panel built on the public API alone is evidence for it.

## Consequences

**Good.** The front-end API is shown to be enough to build a whole front end, which
`docs/reference/the-front-end-api.md` promises. The floor follows the streams instead of timers. The
surfaces are separate modules with their own tests.

**Costs and open risks.**

- **A Node toolchain and an npm dependency tree in a Python repository**: a build step, release
  packaging, and a supply-chain surface the project did not have. D3 is the price of admitting it.
- **First load is heavier** than the page it replaces (about 140 KB gzip of JavaScript against
  131 KB), and cached after the first visit.
- **Only proven against a simulator.** Real failure modes are not reproduced there. #564 runs it
  against a real deployment, scenario by scenario, before the switch.
- **78 guard files to carry over** before the old page can go, each one a promise to keep or a
  retirement to explain.
