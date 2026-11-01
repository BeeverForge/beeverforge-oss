"""A value of `.beeverforge/product.yaml` that YAML cannot build is named, never raised (#90).

A constructor of `yaml.SafeLoader` raises what it raises: `2026-02-30` a ValueError, `!!bool x` a
KeyError, `!!timestamp x` an AttributeError, and none of those is a `yaml.YAMLError`, so each
escaped both readers of the file. `yaml_io.Loader.construct_object` now refuses every failure of a
constructor as `YamlRefused`, one sentence in the loader's words naming the value, its line, its
shape and what to write instead, and the second step a collection is built in
(`state_generators`) is refused the same way.

Each row below is one way that could come undone, and the guard must go red on each.
"""

TEST = "tests/test_a_value_yaml_cannot_build_is_named.py"

_DOOR = "beeverforge/util/yaml_io.py"

MUTATIONS = [
    ("THE DEFECT: the handler is removed, so the ValueError of `2026-02-30` and the KeyError of "
     "`!!bool x` escape both readers again",
     _DOOR, "        except Exception as exc:\n            raise _cannot_build(node, exc, quoted=",
     "        except ZeroDivisionError as exc:\n            raise _cannot_build(node, exc, quoted="),

    ("only what is no YAMLError is renamed, so a ConstructorError (`!!seq x`, `!!binary a`) comes "
     "back across lines without its value",
     _DOOR, "        except YamlRefused:\n            raise\n        except Exception as exc:\n"
     "            raise _cannot_build(node, exc, quoted=",
     "        except yaml.YAMLError:\n            raise\n        except Exception as exc:\n"
     "            raise _cannot_build(node, exc, quoted="),

    ("the second step of building a collection is not named, so `!!set x`, `!!omap x` and "
     "`!!pairs x` come back in PyYAML's words",
     _DOOR, "        self.state_generators[pending:] = [_naming(step, node)\n",
     "        self.state_generators[pending:] = [step\n"),

    ("the line is counted from zero, one above the value",
     _DOOR, "    where = _line(node.start_mark)\n", "    where = f\"line {node.start_mark.line}\"\n"),

    ("the value is not named, only its shape",
     _DOOR, "cannot build (`{_cut(_spelled(node), _VALUE_SHOWN)}`, {where})",
     "cannot build (`{node.tag}`, {where})"),

    ("THE REVIEW'S DEFECT: the exception's own words are the reason again (`KeyError: 'x'`, "
     "`invalid literal for int() with base 10`), and no remedy follows",
     _DOOR, "        reason = f\"not a {shape} — write {_WRITE.get(shape, 'one')}, or {keep}\"\n",
     "        reason = f\"{type(exc).__name__}: {exc}\"\n"),

    ("PyYAML's text is kept even where it carries the interpreter's (`!!binary a`: failed to "
     "decode base64 data: Invalid base64-encoded string…)",
     _DOOR, "    if problem is not None and _plain(problem):\n", "    if problem is not None:\n"),

    ("an explicit tag is told to quote its value, which keeps the tag and fails again",
     _DOOR, "    keep = \"remove the tag to keep it as text\" if _tagged(node) else ",
     "    keep = \"remove the tag to keep it as text\" if False else "),

    ("a tag the loader has no constructor for is named without its remedy",
     _DOOR, "f\"`{shape}` — remove the tag\", node.start_mark)", "f\"`{shape}`\", node.start_mark)"),

    ("what is written under a tag the loader has no constructor for is quoted, so the command "
     "under `!!python/object/apply:os.system` reaches the findings and the published map",
     _DOOR, "raise _cannot_build(node, exc, quoted=self._constructs(node.tag)) from exc\n",
     "raise _cannot_build(node, exc, quoted=True) from exc\n"),

    ("a value of any length is named whole",
     _DOOR, "    return text if len(text) <= at else text[:at - 1] + \"…\"\n",
     "    return text\n"),

    ("a family is dropped from the table, so its constructor is never tried",
     TEST, "    \"tag:yaml.org,2002:binary\": ((\"!!binary é\", \"é\"), "
     "(\"!!binary a\", \"a\")),\n", ""),
]
