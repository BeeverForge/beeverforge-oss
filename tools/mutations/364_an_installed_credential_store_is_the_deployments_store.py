"""A credential store an installed add-on registers is a deployment's store like a shipped one
(#364), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/364_an_installed_credential_store_is_the_deployments_store.py

`BEEVERFORGE_CREDENTIAL_STORE=<kind>` with `credential_store.<kind>` installed through the
`beeverforge.adapters` entry-point group was documented and never held by a test. The claims, each
a row:

  1. an installed kind is built: the registry asks the entry-point group, not only `STORES`;
  2. its refusal is final: a refused name is never answered by the variable;
  3. it is asked before the environment;
  4. a kind nobody installed refuses by name, listing the installed kinds, add-on ones included;
  5. the configuration reference says an add-on kind is a supported value and names the
     credentials the worker's start path asks for.
"""

TEST = "tests/test_an_installed_credential_store_is_the_deployments_store.py"
REGISTRY = "beeverforge/adapters/credential_store/registry.py"
DOCS = "docs/reference/configuration.md"

MUTATIONS = [
    # 1. the add-on lookup
    ("an installed store kind is never looked up in the entry-point group", REGISTRY,
     "    builder = STORES.get(key) or plugins.builder(AXIS, key, builtin=STORES)\n",
     "    builder = STORES.get(key)\n"),

    # 2. the final-refusal rule
    ("a refusal from the declared store falls back to the variable", REGISTRY,
     "    return found if (found.value or found.refused) else None\n",
     "    return found if found.value else None\n"),

    # 3. the order
    ("the environment is asked before the declared store", REGISTRY,
     "    declared = _declared(name, quiet=quiet)\n",
     "    if os.environ.get(name):\n"
     "        return Answer(reference=f\"{ENV}:{name}\", value=os.environ.get(name))\n"
     "    declared = _declared(name, quiet=quiet)\n"),

    # 4. the unknown kind's refusal
    ("the unknown-kind refusal lists the shipped kinds only", REGISTRY,
     "known: {', '.join(known())}\"",
     "known: {', '.join(STORES)}\""),
    ("the unknown-kind refusal stops naming the kind it was asked", REGISTRY,
     'f"unknown credential store {key!r} — known:',
     'f"unknown credential store — known:'),

    # 5. the reference
    ("the reference drops the TLS key from what a worker asks for at start", DOCS,
     ", and `TEMPORAL_TLS_KEY` when no API key answers;",
     ";"),
    ("the reference drops that an add-on kind is a supported value", DOCS,
     "An installed add-on's kind is a supported value: its package registers "
     "`credential_store.<kind>` in the `beeverforge.adapters` entry-point group, the store is "
     "asked before the environment, and its refusal is final — nothing falls back to the "
     "variable. ",
     ""),
]
