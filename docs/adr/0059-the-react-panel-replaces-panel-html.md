# ADR 0059 — The panel is rebuilt in React in a repository of its own, and replaces `panel.html`

- **Status:** Accepted (decided on #547, 2026-11-16 and 2026-11-17; built by the milestone "The new panel" in BeeverForge/beeverforge-panel, none of it merged yet)
- **Date:** 2026-11-17
- **Implements:** #547, for #546.
- **Relates to:** [ADR-0038](./0038-the-platform-is-complete-channels-are-add-ons.md) D1 (the panel
  is the reference surface), [ADR-0043](./0043-the-distribution-is-a-published-image.md) (the
  distribution is a published image), #272 and #22 (the core is headless; the default front end is
  a module on the API contract), and the references to `panel.html` in
  [ADR-0039](./0039-the-action-layer.md), [ADR-0051](./0051-one-door-parallel-conversations-one-semaphore-on-work.md)
  and [ADR-0052](./0052-the-owners-view.md), which D9 supersedes.

## Context

The default front end is one file in the core, `beeverforge/api/panel.html`: about 6,000 lines,
408 KB (131 KB gzip). Measured on one simulated floor over a minute at rest, it makes 51 API
requests on the floor page and 23 on a line's page, because it re-reads on timers while two event
streams and two sockets are open. axe finds serious problems on both pages.

A React panel was built on the public API only (the `/api/v1/` reads, the catalogued actions, the
two SSE streams and the two sockets): 2 requests a minute on both pages, no axe serious or critical
finding on the floor, a line, the board or the product room, about 140 KB gzip of JavaScript on
first load. It has only met a simulator.

The core is headless: what it owns is the action catalogue, the read models and their contract, and
a front end is a client of that contract (#272, #22). A page served from the core's tree, and its
source kept there, is what is left of the time the panel was the product.

## Decision

**The React panel replaces `panel.html`, and it lives outside the core, in
[BeeverForge/beeverforge-panel](https://github.com/BeeverForge/beeverforge-panel).** The core keeps
`panel.html` until the switch, then for one release as the way back, then it goes.

### D1 — A repository of its own

The panel is `BeeverForge/beeverforge-panel`: public, Apache-2.0 like the core, starting from the
proof of concept's commits. The core's tree holds no front-end source, no Node toolchain and no npm
dependency. The panel uses the core's public contract only; nothing in the core is written for it
alone.

### D2 — Node 24 LTS and npm, pinned, in the panel's repository

`package.json` declares `engines`, `.nvmrc` names the version, and `package-lock.json` is committed.
The panel's own CI typechecks, lints, runs its unit tests and builds it.

### D3 — The dependency tree is held strictly

- Installs are `npm ci` from the lockfile, in CI and in the image.
- Install scripts are blocked, except an allowlist (esbuild today).
- CI fails on a high or critical `npm audit` finding.
- A new runtime dependency states its reason in the pull request that adds it.

### D4 — It reaches a deployment as an image of its own

The panel's repository publishes an image that serves the built files and passes every other path
(`/api`, the streams, the sockets, the sign-in, the previews) to the core on the same origin, so the
`__Host-` credential cookie and the sockets work as they do today. The image has no Node at runtime.
The core's compose file starts it, pinned to a tag, and a core release is tested with the tag it
names. The core's wheel and images carry no panel, and `install.sh` needs nothing new.

### D5 — The contract is pinned to one commit of the core

The panel copies the core's `docs/reference/openapi.json` and `events.schema.json` into its
`contract/` at one commit, named in `contract/core-ref`. Its types are generated from them, and its
test bed installs the core at the same commit. A word or a read the panel needs and the core does
not publish is added in the core first, as a contract any front end may read (#552), then pulled.

### D6 — The promises the old page's guards hold leave with it

78 test files in the core read or name `panel.html`. They keep holding it while it exists. Before
#566 deletes it, each promise is either:

- **carried by the panel's own suite**: a Playwright test for what the page shows or does, a check
  over the panel's source for a rule about text (no vendor name, no former product name, no copy of
  a list the core owns);
- **retired**, with the reason in the pull request, where the new design cannot break it.

### D7 — One release of fallback

At the switch the compose file starts the panel in front of the core. For one release, a documented
setting of the core (`BEEVERFORGE_DEFAULT_FRONT_END`) serves `panel.html` again, as the way back.
One release later `panel.html` and the code that serves it are deleted (#566).

### D8 — The rig and the simulator are tooling, then they go

The rig (the core's API at `core-ref`, with a registry, board and home of its own, and no engine) and
the factory simulator (the routes only an engine and a worker can answer) live in the panel's
repository. Until the switch they are its development and CI tooling, held to the contract (#550).
They are removed once its browser tests run against the real API and a real engine in CI (#572).

### D9 — This record supersedes the references to `panel.html`; ADR-0038 is not edited

ADR-0038 D1 stands: the panel is the reference surface. From the switch, the panel it names is this
one. Where ADR-0039, ADR-0051 and ADR-0052 cite `panel.html` (a function, a line, a timer), they
describe the page as it was when they were written, and this record supersedes those references.
None of the four is rewritten.

### D10 — The work is tracked where it lands

The milestone "The new panel" is in the panel's repository. A change the core needs (a word it
publishes, the compose file, the fallback, deleting `panel.html`) is a pull request in the core that
names the panel's issue.

## What this does NOT mean

- **Not two panels for good.** Both exist only until #566.
- **Not Node in the core.** It is needed only to work on the panel and to build its image.
- **Not #272.** That issue records the core as headless; this record applies it to the panel.
- **Not a private interface.** The panel reads nothing another front end could not.

## Consequences

**Good.** The core keeps one toolchain and no npm supply chain. The panel is released on its own
schedule. A complete front end built outside the core, on the public contract alone, is the
evidence `docs/reference/the-front-end-api.md` and #22 promise.

**Costs and open risks.**

- **Two repositories move together.** A change to the contract lands in the core, then the panel
  pulls it; until then the panel reads the older contract. `core-ref` makes that lag visible.
- **One more image** to publish, pin in the compose file and test with each core release.
- **First load is heavier** than the page it replaces (about 140 KB gzip of JavaScript against
  131 KB), and cached after the first visit.
- **Only proven against a simulator.** Real failure modes are not reproduced there; the panel is
  run against a real deployment, scenario by scenario, before the switch.
- **78 guard files to answer for** before the old page can go.
