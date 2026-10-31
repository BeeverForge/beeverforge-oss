"""A value of `.beeverforge/product.yaml` that YAML cannot build is answered as a sentence naming
the file, the line and the value, never raised (#90).

Both readers of the file promise `(docs, error)` for any text of it. A value the safe loader
composes but cannot build raised out of its constructor: `2026-02-30` a ValueError (day is out of
range for month), `!!int x` a ValueError, `!!bool x` a KeyError, `!!timestamp x` an
AttributeError. None of those is a `yaml.YAMLError`, so each escaped `except yaml.YAMLError` and
crashed the caller. The ones that were a `ConstructorError` came back in PyYAML's own words, across
lines, without the value.

THE FAMILY IS THE LOADER'S. `FAILING` writes, for every tag `yaml.SafeLoader` constructs, values
its constructor cannot build. The first test holds the table to the loader's own list, and holds
that each spelling does fail in plain `yaml.SafeLoader`, so no row tries nothing. Each spelling is
then read through both readers, as a field's value (line 1) and as an item under a field (line 2).
"""

from __future__ import annotations

import builtins
import re
from pathlib import Path

import pytest
import yaml

from beeverforge.preview.product import read_docs
from beeverforge.product.loader import DOCS_MANIFEST, _read_docs_manifest, parse_docs_manifest
from beeverforge.util import yaml_io

#: for every tag the safe loader builds, values written as a person might that it cannot build,
#: each with the value as the sentence names it
FAILING: dict[str, tuple[tuple[str, str], ...]] = {
    "tag:yaml.org,2002:timestamp": (("2026-02-30", "2026-02-30"), ("!!timestamp x", "x")),
    "tag:yaml.org,2002:int": (("!!int x", "x"),),
    "tag:yaml.org,2002:float": (("!!float x", "x"),),
    "tag:yaml.org,2002:bool": (("!!bool x", "x"),),
    "tag:yaml.org,2002:binary": (("!!binary é", "é"), ("!!binary a", "a")),
    "tag:yaml.org,2002:null": (("!!null {a: 1}", "{a: 1}"),),
    "tag:yaml.org,2002:str": (("!!str {a: 1}", "{a: 1}"),),
    "tag:yaml.org,2002:seq": (("!!seq x", "x"),),
    "tag:yaml.org,2002:map": (("!!map x", "x"),),
    "tag:yaml.org,2002:set": (("!!set x", "x"),),
    "tag:yaml.org,2002:omap": (("!!omap x", "x"),),
    "tag:yaml.org,2002:pairs": (("!!pairs x", "x"),),
}

CASES = [pytest.param(tag, spelling, value, id=f"{tag.rsplit(':', 1)[1]}:{spelling}")
         for tag, rows in FAILING.items() for spelling, value in rows]

#: where a value is written, and the line it is then on
WHERE = {
    "a field's value": ("product: {spelling}\n", 1),
    "an item under a field": ("product: books\nsources: [{spelling}]\n", 2),
}

#: both readers of the file: the product module's, and the preview's from its own checkout
READERS = {
    "the product module": lambda root: _read_docs_manifest(root),
    "the preview": lambda root: read_docs(str(root)),
}


def _read(reader: str, root: Path, text: str):
    path = root / DOCS_MANIFEST
    path.parent.mkdir(parents=True)
    path.write_bytes(text.encode("utf-8"))
    return READERS[reader](root)


def _shape(tag: str) -> str:
    return tag.replace("tag:yaml.org,2002:", "!!")


#: every exception class a constructor could raise and a sentence could echo: the interpreter's
#: own and PyYAML's
EXCEPTIONS = {name for space in (vars(builtins), vars(yaml), vars(yaml.constructor))
              for name, c in space.items() if isinstance(c, type) and issubclass(c, BaseException)}

#: the remedy every sentence ends on: what to write instead
REMEDY = re.compile(r" — (write|remove|quote) [^—]+$")


def _speaks_the_loaders_words(said: str) -> None:
    """The sentence is the loader's: no exception's class or its `Error:`, and a remedy at the end
    (CONTRIBUTING.md, "Failures speak by name")."""
    assert "Error:" not in said
    assert not {name for name in EXCEPTIONS if name in said}, said
    assert "invalid literal" not in said and "could not convert" not in said, said
    assert REMEDY.search(said), f"no remedy in {said!r}"


def test_every_constructor_family_has_a_failing_spelling():
    built = {tag for tag in yaml.SafeLoader.yaml_constructors if tag is not None}
    assert set(FAILING) == built
    for tag, rows in FAILING.items():
        assert rows, f"no spelling for {tag}"
        for spelling, _ in rows:
            assert yaml.compose(f"x: {spelling}\n", Loader=yaml.SafeLoader).value[0][1].tag == tag
            assert _fails(f"x: {spelling}\n"), f"{spelling!r} builds: the row tries nothing"


def _fails(text: str) -> bool:
    """Whether plain `yaml.SafeLoader` fails to build `text`, by any exception at all."""
    try:
        yaml.load(text, Loader=yaml.SafeLoader)
    except Exception:
        return True
    return False


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("where", WHERE)
@pytest.mark.parametrize(("tag", "spelling", "value"), CASES)
def test_a_value_a_constructor_cannot_build_is_answered_never_raised(tmp_path, reader, where,
                                                                     tag, spelling, value):
    text, line = WHERE[where]
    docs, error = _read(reader, tmp_path, text.format(spelling=spelling))
    assert docs is None
    assert error.startswith(f"{DOCS_MANIFEST} is not valid YAML: ")
    assert f"line {line}" in error
    assert f"`{value}`" in error
    assert _shape(tag) in error
    assert "\n" not in error
    _speaks_the_loaders_words(error)


@pytest.mark.parametrize("loader", [yaml_io.Loader, yaml_io.CountingLoader])
def test_the_door_refuses_what_a_constructor_cannot_build(loader):
    with pytest.raises(yaml.YAMLError) as caught:
        yaml_io.load("a: 2026-02-30\n", loader=loader)
    assert isinstance(caught.value, yaml_io.YamlRefused)
    assert not isinstance(caught.value, ValueError)
    assert str(caught.value) == ("a value YAML cannot build (`2026-02-30`, line 1): not a "
                                 "!!timestamp — write a real date, or quote it to keep it as text")


def test_a_long_value_is_named_by_its_beginning_and_keeps_its_line():
    long = "9" * 1000 + "x" * 1000
    with pytest.raises(yaml_io.YamlRefused) as caught:
        yaml_io.load(f"product: !!int {long}\n")
    said = str(caught.value)
    assert "line 1" in said and "…" in said and "`9999" in said
    assert len(said) <= 200
    _, error = parse_docs_manifest(f"product: !!int {long}\n")
    assert "line 1" in error and "…" in error


@pytest.mark.parametrize("reader", READERS)
def test_a_valid_file_still_loads(tmp_path, reader):
    docs, error = _read(reader, tmp_path, "product: books\nsources: [a/b]\n")
    assert error == ""
    assert docs is not None and docs.product == "books"


def test_a_real_date_is_built_not_refused():
    assert yaml_io.load("x-when: 2026-02-28\n")["x-when"].day == 28
    _, error = parse_docs_manifest("product: books\nx-when: 2026-02-28\n")
    assert "is not valid YAML" not in error


@pytest.mark.parametrize("loader", [yaml_io.Loader, yaml_io.CountingLoader])
@pytest.mark.parametrize("text", [
    "a: !!python/object/apply:os.system [\"touch /tmp/planted\"]\n",
    "a: !!python/name:os.system touch\n",
    "a: !no-such-tag touch\n",
])
def test_a_value_under_a_tag_the_loader_has_no_constructor_for_is_not_quoted(loader, text):
    """A tag the safe loader has no constructor for is refused by its tag and line alone: what
    is written under it is somebody else's payload (a command for `os.system`), and the sentence
    travels into findings and the published map, so it is not echoed."""
    with pytest.raises(yaml_io.YamlRefused) as caught:
        yaml_io.load(text, loader=loader)
    said = str(caught.value)
    assert "touch" not in said
    tag = text.split()[1].split("[")[0]
    assert said == f"a value YAML cannot build (line 1): YAML has no constructor for `{tag}` — remove the tag"


@pytest.mark.parametrize(("text", "said"), [
    ("a: !!int x\n", "(`x`, line 1): not a !!int — write a whole number, or remove the tag to "
                     "keep it as text"),
    ("a: !!bool x\n", "(`x`, line 1): not a !!bool — write true or false, or remove the tag to "
                      "keep it as text"),
    ("a: !!binary a\n", "(`a`, line 1): not a !!binary — write base64 text, or remove the tag "
                        "to keep it as text"),
    ("a: !!seq x\n", "(`x`, line 1): expected a sequence node, but found scalar — write what "
                     "!!seq holds, or remove the tag"),
])
def test_the_reason_and_the_remedy_are_the_loaders_own(text, said):
    with pytest.raises(yaml_io.YamlRefused) as caught:
        yaml_io.load(text)
    assert str(caught.value) == f"a value YAML cannot build {said}"
