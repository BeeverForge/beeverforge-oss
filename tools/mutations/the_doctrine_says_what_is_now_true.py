"""The doctrine says what is now true — every claim added on 2026-08-26 has a guard that goes red.

The cuts are on DOCUMENTS, because the guards protect documents: a path list that drifts from the
tree, a `leaves` beside a file the export keeps, a package name the README invents, an ADR index
row that stops copying the record it indexes. Each cut is one thing a later editor would do.
"""

TEST = "tests/test_the_public_cut_is_written_down.py"
DRIFT = "tests/test_the_docs_do_not_drift.py"
VENDOR = "tests/test_the_docs_name_no_vendor_as_the_core.py"

MUTATIONS = [
    ("STATUS excludes a path that is not tracked (a stale line)",
     "docs/STATUS.md",
     "| `beeverforge/runtime/fargate/` | `beeverforge-aws`",
     "| `beeverforge/runtime/fargatex/` | `beeverforge-aws`"),
    ("STATUS drops the DynamoDB row: the ledger's `leaves` is then wrong, and a file nothing "
     "that stays imports is a reference provider reached by nothing",
     "docs/STATUS.md",
     "| `beeverforge/observability/dynamo.py` | `beeverforge-aws` — the managed metrics table",
     ""),
    ("the ledger marks a leaving file as staying",
     "docs/core/07-extensibility.md",
     "  - beeverforge/observability/dynamo.py             # leaves —",
     "  - beeverforge/observability/dynamo.py             # stays —"),
    ("the ledger marks a staying file as leaving",
     "docs/core/07-extensibility.md",
     "  - beeverforge/adapters/tracker/jira.py            # stays",
     "  - beeverforge/adapters/tracker/jira.py            # leaves"),
    ("the ledger loses the chat channel entry while STATUS still excludes it",
     "docs/core/07-extensibility.md",
     "  - beeverforge/adapters/channel/slack.py           # leaves — the chat channel\n",
     ""),
    ("§10 stops naming the registry that still holds a chat row",
     "docs/core/07-extensibility.md",
     "core registries — `adapters/channel/registry.py` (`slack`)",
     "core registries — `adapters/channel/table.py` (`slack`)"),
    ("§10 says the chat side is not a directory delete while no row reaches it (the sentence "
     "flipped with the chat cut of 2026-08-26; the guard flipped with it)",
     "docs/core/07-extensibility.md",
     "- *The chat connectors are a directory delete too.*",
     "- *The chat connectors are not a directory delete yet.*"),
    ("the README's channel line names a package STATUS does not know",
     "README.md",
     "a chat channel is an add-on package (beeverforge-slack)",
     "a chat channel is an add-on package (beeverforge-chat)"),
    ("the README's sandbox line stops naming the cloud add-on",
     "README.md",
     "a cloud box is an add-on package (beeverforge-aws)",
     "a cloud box is an add-on package"),
    ("STATUS renames the cloud add-on and the README keeps the old name",
     "docs/STATUS.md",
     "| `beeverforge/runtime/fargate/` | `beeverforge-aws` — the cloud box",
     "| `beeverforge/runtime/fargate/` | `beeverforge-cloud` — the cloud box"),
    # re-pinned 2026-09-24 (#269 slice 2): `embed` now follows `credential` in the list
    # re-pinned 2026-10-18 (#742): `credential_store` now follows `credential` in the list
    ("CONTRIBUTING's axis list loses the credential axis",
     "CONTRIBUTING.md",
     "board_setup, box, box_runner, channel, ci, credential, credential_store, embed, event,",
     "board_setup, box, box_runner, channel, ci, credential_store, embed, event,"),
    ("the reader's page names a group the loader never reads",
     "docs/README.md",
     "in the `beeverforge.adapters` entry-point group",
     "in the `beeverforge.plugins` entry-point group"),
    ("the ADR index's row for 0034 stops copying the record it indexes",
     "docs/adr/README.md",
     "| Accepted; the in-process step is decided (addendum 2026-08-26:",
     "| Accepted; the in-process step is deferred (addendum 2026-08-26:",
     DRIFT),
    ("ADR-0034's Status word changes and the index does not follow",
     "docs/adr/0034-extension-model.md",
     "- **Status:** **Accepted; the in-process step is decided**",
     "- **Status:** **Proposed; the in-process step is decided**",
     DRIFT),
    ("ADR-0034's Status line names an addendum the file no longer has",
     "docs/adr/0034-extension-model.md",
     "## Addendum (2026-08-26): the in-process step is decided",
     "## Postscript (2026-08-26): the in-process step is decided",
     DRIFT),
    ("the README names the vendor beside the package, and the exemption is that narrow",
     "README.md",
     "a cloud box is an add-on package (beeverforge-aws)",
     "a cloud box on AWS is an add-on package (beeverforge-aws)",
     VENDOR),
]
