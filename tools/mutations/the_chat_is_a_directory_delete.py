"""Mutation plan for the chat cut: the chat rows leave the core registries, the refusal names the
package, the deployment-wide fallback is declared, and the hint table is held to the packages.

Point-in-time proof (2026-08-26); anchors rot as code moves and fail loudly on rerun.
"""

TEST = "tests/test_the_chat_is_a_directory_delete.py"
CHAT_ROWS = "addons/beeverforge-slack/tests/test_the_rows_answer_for_themselves.py"
DOORS = "tests/test_the_doors_derive_from_the_registries.py"

#: ROW THIS TREE CANNOT PROVE, and what it needs. The worker's listener-start refusal is
#: reached only when a channel FAILS TO START, and the test that drives that opens with
#: `require("channel.slack")` — in the export there is one kind, `panel`, and it does not
#: fail. The direct `_readable` tests below it are about the helper, not this call site.
PROVED_ONLY_WHERE = {
    "the worker's listener start truncates the refusal before the package":
        'addons/beeverforge-slack',
}

MUTATIONS = [
    # ── the tables and the refusal ──────────────────────────────────────────────────────────────
    ("the channel table grows a built-in slack row importing its module lazily — the seam the "
     "cut exists to close",
     "beeverforge/adapters/channel/registry.py",
     'CHANNELS: dict[str, Callable[..., object]] = {\n    "panel": _panel,\n}',
     'CHANNELS: dict[str, Callable[..., object]] = {\n    "panel": _panel,\n'
     '    "slack": lambda **kw: __import__("beeverforge.adapters.channel.slack", '
     'fromlist=["build"]).build(),\n}'),
    ("the channel refusal drops the package to install",
     "beeverforge/adapters/channel/registry.py",
     'known: {_known}{plugins.install_hint(AXIS, kind)}. "',
     'known: {_known}. "'),
    ("the hint answers nothing for every kind",
     "beeverforge/plugins.py",
     '    package = SHIPS_IN.get(f"{axis}.{kind}")',
     '    package = None'),
    ("the hint sends a stranger's typo to install our package",
     "beeverforge/plugins.py",
     '    if package is None:\n        return ""',
     '    if package is None:\n        package = "beeverforge-slack"'),
    ("the hint table loses the telegram row",
     "beeverforge/plugins.py",
     '    "notifier.telegram": "beeverforge-slack",\n',
     ''),
    ("the hint table names the wrong package for the session store",
     "beeverforge/plugins.py",
     '    "session_store.s3": "beeverforge-aws",',
     '    "session_store.s3": "beeverforge-slack",'),
    # re-pinned 2026-09-07: the bound moved into `_readable`, which keeps whichever form says more
    ("the worker's listener start truncates the refusal before the package",
     "beeverforge/runtime/temporal/worker.py",
     'kind, _readable(exc))',
     'kind, _readable(exc, cap=20))'),
    # ── the notifier ────────────────────────────────────────────────────────────────────────────
    ("the notifier's unknown-kind warning drops the package",
     "beeverforge/adapters/notify/registry.py",
     'name or "?", kind, reason, plugins.install_hint(AXIS, kind),',
     'name or "?", kind, reason, "",'),
    ("the declared fallback is ignored",
     "beeverforge/adapters/notify/registry.py",
     '    kind = fallback_kind()\n    if not kind:\n        return None',
     '    kind = fallback_kind()\n    if kind:\n        return None'),
    ("the fallback's absent-package warning drops the package",
     "beeverforge/adapters/notify/registry.py",
     '                    plugins.install_hint(AXIS, kind))\n        return None',
     '                    "")\n        return None'),
    ("an inferred panel never consults the declared fallback",
     "beeverforge/adapters/notify/registry.py",
     '    return _declared_fallback(project) or built',
     '    return built'),
    ("an explicit panel is overruled by the declared fallback",
     "beeverforge/adapters/notify/registry.py",
     '    if declared or kind != DEFAULT_KIND:\n        return built',
     '    if kind != DEFAULT_KIND:\n        return built'),
    ("a row answering None is read as the panel, silently",
     "beeverforge/adapters/notify/registry.py",
     '    if built is None:\n        return CannotPost(missing=())',
     '    if built is None:\n        return _panel(project)',
     DOORS),
    ("the core reads a Telegram variable again",
     "beeverforge/adapters/notify/registry.py",
     'def fallback_kind() -> str:',
     'def fallback_kind() -> str:\n    os.environ.get("BEEVERFORGE_TELEGRAM_BOT_TOKEN")'),
    # ── the cloud doors ─────────────────────────────────────────────────────────────────────────
    ("the box runner's refusal drops the package",
     "beeverforge/adapters/sandbox/registry.py",
     '`{plugins.GROUP}` group{plugins.install_hint(RUNNER_AXIS, kind)}. Nothing was "',
     '`{plugins.GROUP}` group. Nothing was "'),
    ("the metrics refusal drops the package",
     "beeverforge/observability/registry.py",
     '                         f"{plugins.install_hint(axis, _key(kind))}")',
     '                         f"")'),
    ("the session store refusal drops the package",
     "beeverforge/adapters/agent/session_store.py",
     '                         f"{plugins.install_hint(AXIS, chosen)}")',
     '                         f"")'),
    ("the token pool refusal drops the package",
     "beeverforge/adapters/agent/token_pool.py",
     '                         f"{plugins.install_hint(AXIS, chosen)}")',
     '                         f"")'),
    # ── the packages ────────────────────────────────────────────────────────────────────────────
    ("the chat package's overlay drops the telegram module",
     "addons/beeverforge-slack/pyproject.toml",
     '    "beeverforge/adapters/notify/telegram.py",\n]',
     ']'),
    ("the slack row stops naming what it lacks",
     "beeverforge/adapters/notify/slack.py",
     '    if missing:\n        return CannotPost(missing)',
     '    if missing:\n        return CannotPost(())',
     CHAT_ROWS),
    ("the telegram row ignores a missing chat id",
     "beeverforge/adapters/notify/telegram.py",
     '((BOT_TOKEN_ENV, tok), (CHAT_ID_ENV, chat))',
     '((BOT_TOKEN_ENV, tok), (CHAT_ID_ENV, tok))',
     CHAT_ROWS),
]
