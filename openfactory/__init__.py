"""`openfactory`: OpenFactory 0.7's import name for `beeverforge`, kept until 1.1 (#264).

A 0.7 add-on writes `from openfactory.<module> import <name>`. The rename removed the package in
0.1.0, so every such add-on failed to load on an upgrade in place. Importing `openfactory` now
gives back the `beeverforge` package itself, and `openfactory.<module>` gives back
`beeverforge.<module>` — THE SAME MODULE OBJECTS, never second copies: a module imported twice
under two names holds two caches, two registries and two of every class, so an `isinstance` across
them fails and a registry written through one name is empty through the other.

HOW. Importing this package replaces its own `sys.modules` entry with `beeverforge` (the import
statement returns what `sys.modules` holds once the module has run) and puts one finder at the head
of `sys.meta_path`. For `openfactory.<x>` the finder imports `beeverforge.<x>` and hands the import
system a loader whose `create_module` returns that module, so the name `openfactory.<x>` is bound to
it. The import system stamps the spec it was handed onto the module it got
(`importlib._bootstrap._init_module_attrs` sets `__spec__` unconditionally), so `exec_module` puts
the module's own spec back: `beeverforge.<x>.__spec__` still names `beeverforge.<x>`. A name
`beeverforge` does not have is not found, under the name that was asked for.

NOTHING HAPPENS UNTIL SOMEBODY ASKS. `import beeverforge` never imports this package; the finder
exists only in a process that imported the old name.

A FutureWarning, NOT A DeprecationWarning. Python's default filters show a DeprecationWarning only
when the importing line is in `__main__`, and a 0.7 add-on's import is in the add-on's own module:
the operator of the deployment — the person 1.1 breaks — would never read it. A FutureWarning is
shown by default wherever it is raised, once per importing line; it is raised once per process,
from the first import of the old name, pointing at that line.

Removed in BeeverForge 1.1.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
import warnings

import beeverforge
from beeverforge.deprecations import removed_in

#: The release that removes the `openfactory` import name — the register's, not restated here.
#: `beeverforge.deprecations` imports only `re` and `dataclasses`, so the shim stays cheap and
#: reaches nothing that could import the shim back.
REMOVED_IN = removed_in("openfactory-import")

_OLD, _NEW = "openfactory", "beeverforge"


class _TheNewName(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """`openfactory.<x>` is found as `beeverforge.<x>`, the same module object."""

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(_OLD + "."):
            return None
        real = _NEW + fullname[len(_OLD):]
        try:
            module = importlib.import_module(real)
        except ModuleNotFoundError as exc:
            if exc.name != real:
                raise  # the module exists and failed on an import of its own: that is the error
            return None  # neither name exists; the import system says so, under the name asked
        spec = importlib.util.spec_from_loader(fullname, self,
                                               is_package=hasattr(module, "__path__"))
        spec.loader_state = module.__spec__
        return spec

    def create_module(self, spec):
        return sys.modules[_NEW + spec.name[len(_OLD):]]

    def exec_module(self, module):
        # the module already ran under its own name; only its spec, overwritten on the way in by
        # the alias's, is put back
        module.__spec__ = module.__spec__.loader_state


if not any(isinstance(finder, _TheNewName) for finder in sys.meta_path):
    sys.meta_path.insert(0, _TheNewName())

warnings.warn(
    f"`{_OLD}` is now `{_NEW}`: import `{_NEW}` (and `{_NEW}.<module>` for `{_OLD}.<module>`) — "
    f"the `{_OLD}` import name is removed in BeeverForge {REMOVED_IN}.",
    FutureWarning, stacklevel=2)

sys.modules[__name__] = beeverforge
