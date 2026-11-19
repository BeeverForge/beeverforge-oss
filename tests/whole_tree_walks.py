"""Which tests walk this repository's own tree — the one definition the `whole_tree` marker and its
guard (`tests/test_a_whole_tree_test_carries_its_marker.py`) share (#545).

WHAT COUNTS. A test walks the tree when it, or anything it reaches in the test modules — a helper,
a fixture, a module-level constant it names or a decorator argument — makes one of these calls on a
path that starts in the checkout:

  - `<path>.rglob(...)`, and `<path>.glob("**/...")`;
  - `os.walk(<path>)`;
  - a call carrying the argument `"ls-files"` (`git ls-files`), whose `cwd=` is the checkout, or
    which names no `cwd`, since a child process starts where the suite does.

WHERE A PATH STARTS. Read from its leftmost piece, through `/`, `.joinpath`, `.parent`, `Path(...)`
and the names it was assigned to. It starts in the checkout when that piece is `__file__`, the
current directory, or one of the checkout's own directories written as a string (`Path("beeverforge")`).
A path that starts in `tmp_path`, in a fixture's directory or in a function's parameter nothing
passes the checkout to is somebody else's directory: walking it is cheap and is not marked. A
parameter is followed to its callers in the test modules, one call at a time.

WHAT IT IS NOT. It does not run anything, so it cannot see a walk behind `getattr`, `eval` or a
path built by a function that is not in the test modules. A test it misses is a test the guard
cannot hold; the repair is to make the walk visible, not to widen this file.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# The checkout's own directories, when a path is written from one of them as a string.
CHECKOUT_PIECES = frozenset({
    ".", "beeverforge", "tests", "docs", "addons", "tools", "scripts", "changes", "src",
})

MARKER = "whole_tree"


@dataclass(frozen=True)
class Site:
    """One walking call: where it is, and the call as written."""

    path: str
    line: int
    call: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line} `{self.call}`"


@dataclass
class _Origin:
    """Where an expression's path starts: in the checkout, or in these parameters."""

    repo: bool = False
    params: set[str] = field(default_factory=set)

    def add(self, other: _Origin) -> None:
        self.repo = self.repo or other.repo
        self.params |= other.params


@dataclass
class _Function:
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.expr
    module: Module
    params: list[str]
    defaults: dict[str, ast.expr]
    cls: str | None = None
    locals: dict[str, list[ast.expr]] = field(default_factory=dict)


class Module:
    """One parsed test module and what it defines."""

    def __init__(self, name: str, path: str, tree: ast.Module, index: Index) -> None:
        self.name = name
        self.path = path
        self.tree = tree
        self.index = index
        self.functions: dict[str, _Function] = {}
        self.assigns: dict[str, ast.expr] = {}
        self.from_imports: dict[str, tuple[str, str]] = {}
        self.module_imports: dict[str, str] = {}
        self._collect()

    def _collect(self) -> None:
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = self._function(node, None)
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.functions[f"{node.name}.{item.name}"] = self._function(item, node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.assigns[target.id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
                self.assigns[node.target.id] = node.value
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                module = node.module.rsplit(".", 1)[-1]
                for alias in node.names:
                    self.from_imports[alias.asname or alias.name] = (module, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.module_imports[alias.asname or alias.name.split(".")[0]] = (
                        alias.name.rsplit(".", 1)[-1])

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, cls: str | None) -> _Function:
        args = node.args
        positional = [a.arg for a in args.posonlyargs + args.args]
        defaults = dict(zip(reversed(positional), reversed(args.defaults), strict=False))
        kwonly = [a.arg for a in args.kwonlyargs]
        defaults.update({a.arg: d for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True) if d})
        function = _Function(node, self, positional + kwonly, defaults, cls)
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                for target in sub.targets:
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store):
                            function.locals.setdefault(name.id, []).append(sub.value)
            elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and sub.value:
                function.locals.setdefault(sub.target.id, []).append(sub.value)
            elif isinstance(sub, ast.NamedExpr) and isinstance(sub.target, ast.Name):
                function.locals.setdefault(sub.target.id, []).append(sub.value)
            elif isinstance(sub, (ast.For, ast.AsyncFor, ast.comprehension)):
                for name in ast.walk(sub.target):
                    if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store):
                        function.locals.setdefault(name.id, []).append(sub.iter)
            elif isinstance(sub, ast.withitem) and sub.optional_vars is not None:
                for name in ast.walk(sub.optional_vars):
                    if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store):
                        function.locals.setdefault(name.id, []).append(sub.context_expr)
        return function


class Index:
    """Every test module under some roots, analysed together so a helper in one is seen from another."""

    def __init__(self, sources: dict[str, str]) -> None:
        """`sources` maps a repository-relative path to its text."""
        self.modules: dict[str, Module] = {}
        for path, text in sources.items():
            name = Path(path).stem
            self.modules[name] = Module(name, path, ast.parse(text, filename=path), self)
        self._memo: dict[tuple[str, str], tuple[Site | None, dict[str, Site]]] = {}
        self._active: set[tuple[str, str]] = set()
        self._holders: dict[tuple[str, str], _Function] = {}
        self._cuts = 0

    # ── where a path starts ────────────────────────────────────────────────────────────────
    def origin(self, expr: ast.expr, fn: _Function | None, module: Module,
               seen: frozenset[str] = frozenset()) -> _Origin:
        out = _Origin()
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, str) and expr.value in CHECKOUT_PIECES:
                out.repo = True
        elif isinstance(expr, ast.Name):
            self._name_origin(expr.id, fn, module, seen, out)
        elif isinstance(expr, ast.BinOp):
            if not _names_a_fixture(expr.right):
                out.add(self.origin(expr.left, fn, module, seen))
        elif isinstance(expr, ast.Attribute):
            if expr.attr == "__file__":  # `module.__file__`: where that module lives
                out.repo = True
            out.add(self.origin(expr.value, fn, module, seen))
        elif isinstance(expr, ast.Subscript):
            out.add(self.origin(expr.value, fn, module, seen))
        elif isinstance(expr, ast.Starred):
            out.add(self.origin(expr.value, fn, module, seen))
        elif isinstance(expr, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            out.add(self.origin(expr.elt, fn, module, seen))
        elif isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
            for element in expr.elts:
                out.add(self.origin(element, fn, module, seen))
        elif isinstance(expr, ast.BoolOp):
            for value in expr.values:
                out.add(self.origin(value, fn, module, seen))
        elif isinstance(expr, ast.IfExp):
            out.add(self.origin(expr.body, fn, module, seen))
            out.add(self.origin(expr.orelse, fn, module, seen))
        elif isinstance(expr, ast.Call):
            self._call_origin(expr, fn, module, seen, out)
        return out

    def _call_origin(self, call: ast.Call, fn: _Function | None, module: Module,
                     seen: frozenset[str], out: _Origin) -> None:
        func = call.func
        if isinstance(func, ast.Attribute):
            if func.attr == "cwd" and isinstance(func.value, ast.Name) and func.value.id in (
                    "Path", "pathlib"):
                out.repo = True
                return
            if func.attr in ("getfile", "getsourcefile"):  # `inspect.getfile(module)`
                out.repo = True
                return
            if func.attr == "getcwd":
                out.repo = True
                return
            # `.joinpath`, `.resolve`, `.relative_to`, `Path.home`: the receiver is where it starts.
            if func.attr in ("joinpath", "resolve", "absolute", "expanduser", "with_name",
                             "with_suffix", "relative_to"):
                if any(_names_a_fixture(a) for a in call.args):
                    return
                out.add(self.origin(func.value, fn, module, seen))
                return
        if isinstance(func, ast.Name) and func.id in ("Path", "PurePath", "str", "fspath", "sorted",
                                                      "list", "set", "tuple"):
            if call.args:
                out.add(self.origin(call.args[0], fn, module, seen))
            return
        if isinstance(func, ast.Attribute) and func.attr in ("Path", "fspath"):
            if call.args:
                out.add(self.origin(call.args[0], fn, module, seen))
            return
        target = self.callee(call, fn, module)
        if target is None and isinstance(func, ast.Attribute):
            # `.glob`, `.iterdir`, `.read_text`: whatever it yields comes from the receiver.
            out.add(self.origin(func.value, fn, module, seen))
            return
        # A helper of this module that returns a path: where its returns start.
        if target is not None and target.module is not None:
            key = f"{target.module.name}:{id(target)}"
            if key in seen:
                return
            for sub in ast.walk(target.node):
                if isinstance(sub, ast.Return) and sub.value is not None:
                    inner = self.origin(sub.value, target, target.module, seen | {key})
                    out.repo = out.repo or inner.repo

    def _name_origin(self, name: str, fn: _Function | None, module: Module,
                     seen: frozenset[str], out: _Origin) -> None:
        if name == "__file__":
            out.repo = True
            return
        key = f"{module.name}.{name}.{id(fn)}"
        if key in seen:
            return
        seen = seen | {key}
        if fn is not None and name in fn.locals:
            for value in fn.locals[name]:
                out.add(self.origin(value, fn, module, seen))
        if fn is not None and name in fn.params:
            out.params.add(name)
            default = fn.defaults.get(name)
            if default is not None:
                inner = self.origin(default, None, module, seen)
                out.repo = out.repo or inner.repo
            return
        if fn is not None and name in fn.locals:
            return
        if name in module.assigns:
            out.add(self.origin(module.assigns[name], None, module, seen))
            return
        if name in module.from_imports:
            other, attr = module.from_imports[name]
            target = self.modules.get(other)
            if target is not None and attr in target.assigns:
                out.add(self.origin(target.assigns[attr], None, target, seen))

    # ── what a call reaches ────────────────────────────────────────────────────────────────
    def callee(self, call: ast.Call, fn: _Function | None, module: Module) -> _Function | None:
        return self.resolve(call.func, fn, module)

    def resolve(self, expr: ast.expr, fn: _Function | None, module: Module) -> _Function | None:
        if isinstance(expr, ast.Name):
            if expr.id in module.functions:
                return module.functions[expr.id]
            if f"{expr.id}.__init__" in module.functions:
                return module.functions[f"{expr.id}.__init__"]
            if expr.id in module.from_imports:
                other, attr = module.from_imports[expr.id]
                target = self.modules.get(other)
                if target is not None:
                    return target.functions.get(attr)
        elif isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            holder = expr.value.id
            if holder in ("self", "cls") and fn is not None and fn.cls:
                return module.functions.get(f"{fn.cls}.{expr.attr}")
            if holder in module.module_imports:
                target = self.modules.get(module.module_imports[holder])
                if target is not None:
                    return target.functions.get(expr.attr)
            if holder in module.from_imports:
                other, attr = module.from_imports[holder]
                if attr in self.modules:
                    return self.modules[attr].functions.get(expr.attr)
        return None

    def _walk_sites(self, fn: _Function) -> list[tuple[ast.Call, str, ast.expr | None]]:
        """The walking calls in a function's body, decorators and defaults: (call, text, subject).
        A subject of None is the working directory."""
        found = []
        nodes = [fn.node] if isinstance(fn.node, ast.expr) else [
            *fn.node.decorator_list, *fn.node.args.defaults, *fn.node.body]
        for top in nodes:
            for call in ast.walk(top):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                if isinstance(func, ast.Attribute) and func.attr == "rglob":
                    found.append((call, f"{ast.unparse(func.value)}.rglob", func.value))
                elif (isinstance(func, ast.Attribute) and func.attr == "glob" and call.args
                        and isinstance(call.args[0], ast.Constant)
                        and isinstance(call.args[0].value, str) and "**" in call.args[0].value):
                    found.append((call, f"{ast.unparse(func.value)}.glob", func.value))
                elif ((isinstance(func, ast.Attribute) and func.attr == "walk"
                       and isinstance(func.value, ast.Name) and func.value.id == "os")
                      or (isinstance(func, ast.Name) and func.id == "walk"
                          and fn.module.from_imports.get("walk", ("", ""))[0] == "os")):
                    if call.args:
                        found.append((call, "os.walk", call.args[0]))
                elif any(isinstance(a, ast.Constant) and a.value == "ls-files"
                         or (isinstance(a, (ast.List, ast.Tuple)) and any(
                             isinstance(e, ast.Constant) and e.value == "ls-files" for e in a.elts))
                         for a in call.args):
                    cwd = next((k.value for k in call.keywords if k.arg == "cwd"), None)
                    found.append((call, "git ls-files", cwd))
        return found

    def _holder(self, module: Module, name: str) -> _Function:
        """A module-level constant, as the function whose body is its value."""
        key = (module.name, name)
        if key not in self._holders:
            self._holders[key] = _Function(module.assigns[name], module, [], {})
        return self._holders[key]

    def reaches(self, fn: _Function) -> tuple[Site | None, dict[str, Site]]:
        """(a walk of the checkout this function makes, the walks it makes on each parameter)."""
        key = (fn.module.name, f"{id(fn)}")  # every _Function lives as long as the index
        if key in self._memo:
            return self._memo[key]
        if key in self._active:
            self._cuts += 1  # a cycle: what this returns is not final, so nothing above keeps it
            return None, {}
        self._active.add(key)
        cuts = self._cuts
        module = fn.module
        direct: Site | None = None
        parametric: dict[str, Site] = {}

        def note(origin: _Origin, site: Site) -> None:
            nonlocal direct
            if origin.repo and direct is None:
                direct = site
            for p in origin.params:
                parametric.setdefault(p, site)

        for call, text, subject in self._walk_sites(fn):
            site = Site(module.path, call.lineno, text)
            if subject is None:
                note(_Origin(repo=True), site)
            else:
                note(self.origin(subject, fn, module), site)

        nodes = [fn.node] if isinstance(fn.node, ast.expr) else [
            *fn.node.decorator_list, *fn.node.body]
        # a fixture or helper named as a parameter is reached by name
        names = list(fn.params) if not isinstance(fn.node, ast.expr) else []
        for top in nodes:
            for sub in ast.walk(top):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                    names.append(sub.id)
                elif isinstance(sub, ast.Attribute) and isinstance(sub.ctx, ast.Load):
                    pass
        for name in names:
            if name in module.assigns and not (name in fn.locals or name in fn.params):
                inner, _ = self.reaches(self._holder(module, name))
                if inner is not None and direct is None:
                    direct = inner
            elif name in module.from_imports and name not in fn.locals:
                other, attr = module.from_imports[name]
                target = self.modules.get(other)
                if target is not None and attr in target.assigns:
                    inner, _ = self.reaches(self._holder(target, attr))
                    if inner is not None and direct is None:
                        direct = inner
            if name in fn.params and name in module.functions:
                inner, _ = self.reaches(module.functions[name])
                if inner is not None and direct is None:
                    direct = inner
        for top in nodes:
            for call in ast.walk(top):
                if not isinstance(call, ast.Call):
                    continue
                target = self.callee(call, fn, module)
                if target is None or target is fn:
                    continue
                inner_direct, inner_params = self.reaches(target)
                if inner_direct is not None and direct is None:
                    direct = inner_direct
                for param, site in inner_params.items():
                    argument = _argument(call, target, param)
                    if argument is None:
                        continue
                    note(self.origin(argument, fn, module), site)
        self._active.discard(key)
        if self._cuts == cuts or not self._active:
            self._memo[key] = (direct, parametric)
        return direct, parametric

    # ── the tests ──────────────────────────────────────────────────────────────────────────
    def tests(self, module: Module) -> dict[str, Facts]:
        out: dict[str, Facts] = {}
        module_marked = _marked(module.tree.body, module.tree)
        classes = {n.name: n for n in module.tree.body if isinstance(n, ast.ClassDef)}
        for qual, fn in module.functions.items():
            leaf = qual.rsplit(".", 1)[-1]
            if not leaf.startswith("test"):
                continue
            if fn.cls is not None and not fn.cls.startswith("Test"):
                continue
            if not isinstance(fn.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            marked = module_marked or any(_is_marker(d) for d in fn.node.decorator_list)
            if fn.cls is not None:
                marked = marked or any(_is_marker(d) for d in classes[fn.cls].decorator_list) \
                    or _marked(classes[fn.cls].body, None)
            site, _ = self.reaches(fn)
            out[qual] = Facts(module.path, fn.node.lineno, marked, site)
        return out


@dataclass(frozen=True)
class Facts:
    path: str
    line: int
    marked: bool
    walk: Site | None


def _names_a_fixture(expr: ast.expr) -> bool:
    """A piece of a path that says it is a fixture directory: what a test reads there is the
    test's own data, small and not the checkout."""
    if isinstance(expr, ast.Constant):
        return isinstance(expr.value, str) and expr.value == "fixtures"
    return isinstance(expr, ast.Name) and "FIXTURES" in expr.id.upper()


def _argument(call: ast.Call, target: _Function, param: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == param:
            return keyword.value
    params = target.params
    if params and params[0] in ("self", "cls"):
        params = params[1:]
    if param in params:
        index = params.index(param)
        if index < len(call.args) and not any(isinstance(a, ast.Starred) for a in call.args[:index + 1]):
            return call.args[index]
    return target.defaults.get(param)


def _is_marker(node: ast.expr) -> bool:
    """`pytest.mark.whole_tree`, called or not."""
    if isinstance(node, ast.Call):
        node = node.func
    return (isinstance(node, ast.Attribute) and node.attr == MARKER
            and isinstance(node.value, ast.Attribute) and node.value.attr == "mark")


def _marked(body: list[ast.stmt], _tree: ast.Module | None) -> bool:
    """A `pytestmark = ...` among these statements that names the marker."""
    for node in body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            if any(_is_marker(sub) for sub in ast.walk(node.value)):
                return True
    return False


def analyse(sources: dict[str, str]) -> dict[str, dict[str, Facts]]:
    """For every module in `sources`, each test's marker and the walk it makes, if any."""
    index = Index(sources)
    return {module.path: index.tests(module) for module in index.modules.values()}
