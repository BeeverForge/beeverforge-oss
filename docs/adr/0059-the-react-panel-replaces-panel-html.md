# ADR 0059 — The panel is rebuilt in React in a repository of its own, and replaces `panel.html`

- **Status:** Accepted (decided on #547, 2026-11-16 and 2026-11-17; built by the milestone "The new panel" in BeeverForge/beeverforge-panel, none of it merged yet)
- **Date:** 2026-11-17
- **Implements:** #547, for BeeverForge/beeverforge-panel#2.
- **Relates to:** [ADR-0038](./0038-the-platform-is-complete-channels-are-add-ons.md) D1 (the panel
  is the reference surface; it stands, D9), [ADR-0043](./0043-the-distribution-is-a-published-image.md)
  (the distribution is a published image; D4 amends it, with dated notes there), #22 (the default
  front end is a module on the API contract; D4 answers how it ships), #272 (an open request for a
  record that amends ADR-0038 D1; this record does not answer it), and the references to
  `panel.html` in [ADR-0039](./0039-the-action-layer.md),
  [ADR-0051](./0051-one-door-parallel-conversations-one-semaphore-on-work.md) and
  [ADR-0052](./0052-the-owners-view.md), which D9 leaves as they are.

## Context

The default front end is one file in the core, `beeverforge/api/panel.html`: 6,218 lines and 411,723
bytes (about 133 KB gzip) at 8d9ae51, the commit this record is written against. Measured on one
simulated floor over a minute at rest, on 14 and 15 November 2026, it made 51 API requests on the
floor page and 23 on a line's page, because it re-reads on timers while two event streams and two
sockets are open. On the same days axe found serious problems on both pages, mostly colour contrast.
8d9ae51 (#583, 17 November) has since made the page's text meet AA contrast in both themes; what axe
finds on it now has not been re-measured.

A React panel was built on the public API only (the `/api/v1/` reads, the catalogued actions, the
two SSE streams and the two sockets). Measured the same days, it makes 2 requests a minute on both
pages, has no axe serious or critical finding on the floor, a line, the board or the product room,
and loads about 140 KB gzip of JavaScript on first load. It has only met a simulator.

The core is headless in what it owns: the action catalogue, the read models and their contract; a
front end is a client of that contract (#22). That is the reasoning of this record, not a decision
already on record: ADR-0038 D1 stands (D9), and #272, which asks for a record that amends it, is
open. A page served from the core's tree, and its source kept there, is what is left of the time the
panel was the product.

## Decision

**The React panel replaces `panel.html`, and it lives outside the core, in
[BeeverForge/beeverforge-panel](https://github.com/BeeverForge/beeverforge-panel).** The core keeps
`panel.html` until the switch, then for one release as the way back, then it goes.

### D1 — A repository of its own

The panel is `BeeverForge/beeverforge-panel`: public, Apache-2.0 like the core, starting from the
proof of concept's commits. From BeeverForge/beeverforge-panel#21 on, the core's tree holds no
front-end source, no Node toolchain and no npm dependency; until then `panel.html` is in the tree,
the wheel and the worker image. The panel uses the core's public contract only; nothing in the core
is written for it alone.

### D2 — Node 24 LTS and npm, pinned, in the panel's repository

`package.json` declares `engines`, `.nvmrc` names the version, and `package-lock.json` is committed.
The panel's own CI typechecks, lints, runs its unit tests and builds it.

### D3 — The dependency tree is held strictly

- Installs are `npm ci` from the lockfile, in CI and in the image.
- Install scripts are blocked, except an allowlist (esbuild today).
- CI fails on a high or critical `npm audit` finding.
- Every dependency's licence is compatible with Apache-2.0, and the panel's CI checks it: the core no
  longer sees that tree.
- A new runtime dependency states its reason in the pull request that adds it.

### D4 — It reaches a deployment as an image of its own

The panel's repository publishes an image that serves the built files and passes every other request
(`/api`, the streams, the sockets, the sign-in, the previews) to the core on the same origin, so the
`__Host-` credential cookie and the sockets work as they do today. The image has no Node at runtime.

**It carries what the core's pages carry by Host and by header.** The core never serves the panel on
a host under `BEEVERFORGE_PREVIEW_DOMAIN`, and it sends `frame-ancestors 'none'` on every page,
because a preview is a page on a sibling host running code nobody reviewed yet and the panel's
buttons merge pull requests and release to production. Neither is a split by path, so the image
holds both:

- The image routes by Host before path: a request whose Host is under `BEEVERFORGE_PREVIEW_DOMAIN`
  goes to the core whole, and the image serves its own files only on the deployment's host.
- Every response it serves carries `Content-Security-Policy: frame-ancestors 'none'` and
  `X-Frame-Options: DENY`, and it forwards `Host` and `X-Forwarded-Proto` as it received them (the
  core reads the second to tell whether a request is secure).
- The core's `test_a_host_under_the_preview_domain_never_reaches_the_panel` and
  `test_the_panel_refuses_to_be_framed` are carried to tests that run against the image, not the
  page. BeeverForge/beeverforge-panel#8 and #13 carry both properties.

**It is pinned by digest.** The core's compose file names the image by digest
(`ghcr.io/beeverforge/beeverforge-panel:<tag>@sha256:<digest>`), so the release's `SHA256SUMS` covers
what runs, and a core release is tested with the digest it names. The panel's release publishes an
SBOM and a build-provenance attestation, as ADR-0043 requires of every image. It is a fifth image and
the only one `release.yml` does not publish: ADR-0043 §1 and §2 carry a dated note, and the image-set
guard names it as that one exception.

**It has an owner and a rule.** Only the panel's release workflow publishes the image, run by the
maintainers of that repository; the core's maintainers own which digest the compose file names. When
a core release is cut and no panel release has passed the core's tests, the core release keeps the
digest the previous release named and its notes say so. It does not go out with a tag it did not
test.

**It can fail to come up.** An image that cannot be pulled or does not start stops
`docker compose up` with the pull or start error, naming the image. The remedy is the way back (D7),
which needs no panel image.

The core's wheel and images carry no panel from BeeverForge/beeverforge-panel#21 on, and `install.sh`
needs nothing new.

### D5 — The contract is pinned to one commit of the core

The panel copies the core's `docs/reference/openapi.json` and `events.schema.json` into its
`contract/` at one commit, named in `contract/core-ref`. Its types are generated from them, and its
test bed installs the core at the same commit. A word or a read the panel needs and the core does
not publish is added in the core first, as a contract any front end may read
(BeeverForge/beeverforge-panel#7), then pulled.

### D6 — The promises the old page's guards hold leave with it

78 test files in the core read or name `panel.html`, and 75 mutation plans in `tools/mutations` cut
it. They keep holding it while it exists. Before BeeverForge/beeverforge-panel#21 deletes it, each
promise is one of three:

- **carried by the panel's own suite**: a Playwright test for what the page shows or does, a check
  over the panel's source for a rule about text (no vendor name, no former product name, no copy of
  a list the core owns);
- **carried by a test that runs against the image**: the routing and the response headers of D4,
  which a test that drives the page and a check over source text do not see;
- **retired**, with the reason in the pull request, where the new design cannot break it.

Each of the 75 plans goes with the guards it proves: its rows are retired with
`# RETIRED <date>: <why>`, or the plan is declared `SUPERSEDED_BY` the panel's own. Deleting
`panel.html` without that makes `test_every_mutation_plan_can_run` refuse 393 anchors in those plans
(measured in a scratch copy at db313e6).

### D7 — One release of fallback, chosen in the compose file

At the switch (BeeverForge/beeverforge-panel#20) the compose file starts the panel's image on the
published port, with the core behind it, and sets `BEEVERFORGE_DEFAULT_FRONT_END=off` for the core,
so the core serves no page of its own and one panel answers.

For one release, a compose profile starts the core on the published port instead, with the setting
`on` and no panel image: that is the way back, and it is chosen in the compose file because a core
setting cannot change what the image answers first. `BEEVERFORGE_DEFAULT_FRONT_END` keeps its
meaning (`on` or `off`) and gains no value. The core's own default stays `on` until
BeeverForge/beeverforge-panel#21, so a core run without the compose file still serves its page; what
changes at the switch is the compose file.

One release later `panel.html`, the code that serves it and the setting are deleted
(BeeverForge/beeverforge-panel#21).

### D8 — The rig and the simulator are tooling, then they go

The rig (the core's API at `core-ref`, with a registry, board and home of its own, and no engine) and
the factory simulator (the routes only an engine and a worker can answer) live in the panel's
repository. Until the switch they are its development and CI tooling, held to the contract
(BeeverForge/beeverforge-panel#5). They are removed once its browser tests run against the real API
and a real engine in CI (BeeverForge/beeverforge-panel#22).

### D9 — ADR-0038 D1 stands; the three records that cite `panel.html` cite it as it was

ADR-0038 D1 stands: the panel is the reference surface. From the switch, the panel it names is this
one. ADR-0039, ADR-0051 and ADR-0052 cite `panel.html` at a function, a line or a timer. Those are
citations of the page as it was when each was written, not decisions: nothing in them moves, so the
dated note `docs/adr/README.md` asks for when a decision moves does not apply, and none of the four
is edited. ADR-0043 is different, because D4 moves a decision in it, and it carries the dated notes.

### D10 — The work is tracked where it lands

The milestone "The new panel" is in the panel's repository. A change the core needs (a word it
publishes, the compose file, the fallback, deleting `panel.html`) is a pull request in the core that
names the panel's issue.

## What this does NOT mean

- **Not two panels for good.** Both exist only until BeeverForge/beeverforge-panel#21, and at the
  switch one answers: the compose file turns the core's page off (D7).
- **Not Node in the core.** It is needed only to work on the panel and to build its image.
- **Not #272.** That issue asks for a record that amends ADR-0038 D1; this record does not, and D9
  leaves D1 standing. "The core is headless" is this record's reasoning, not a decision on record.
- **Not a private interface.** The panel reads nothing another front end could not.

## Considered and rejected

- **`panel/` in this tree** (the 16 November decision). Dropped on 17 November: the core would carry
  a Node toolchain and an npm supply chain it does not otherwise have, and a change to the panel
  would wait for a core release.

## Consequences

**Good.** The core keeps one toolchain and no npm supply chain. The panel is released on its own
schedule, under the owner and the rule of D4. A complete front end built outside the core, on the
public contract alone, is the evidence `docs/reference/the-front-end-api.md` and #22 promise.

**Costs and open risks.**

- **The replacement is not at parity today.** The switch (BeeverForge/beeverforge-panel#20) waits on
  the parity audit (#12), the security review (#13) and the scenario run against a real deployment
  (#19). Four gaps are known, each with the issue that closes it: the product room cannot switch
  product (#10), a product-only credential gets the product room instead of a read-only board (#11),
  the image does not yet serve the panel at every page address (#8), and some server-owned words are
  still copied (#7).
- **Two repositories move together.** A change to the contract lands in the core, then the panel
  pulls it; until then the panel reads the older contract. `core-ref` makes that lag visible.
- **One more image** to publish, pin by digest in the compose file at each core release, and test
  with it.
- **First load is heavier** than the page it replaces (about 140 KB gzip of JavaScript against about
  133 KB), and cached after the first visit.
- **Only proven against a simulator.** Real failure modes are not reproduced there; the panel is
  run against a real deployment, scenario by scenario, before the switch.
- **78 guard files and 75 mutation plans to answer for** before the old page can go (D6).
- **A core run without the compose file serves no page**, from BeeverForge/beeverforge-panel#21 on:
  `beeverforge serve` from a checkout or a pip install has the API, the streams, the sign-in and the
  previews, and no page. That is intended: the core is headless, and the panel's dev server is how a
  contributor gets a page.
