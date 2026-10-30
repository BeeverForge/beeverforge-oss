"""A value of `.beeverforge/product.yaml` that YAML cannot build is named, never raised (#90).

A constructor of `yaml.SafeLoader` raises what it raises: `2026-02-30` a ValueError, `!!bool x` a
KeyError, `!!timestamp x` an AttributeError, and none of those is a `yaml.YAMLError`, so each
escaped both readers of the file. `yaml_io.Loader.construct_object` now refuses every failure of a
constructor as `YamlRefused`, one sentence naming the value, its line and its shape, and the
second step a collection is built in (`state_generators`) is refused the same way.

Each row below is one way that could come undone, and the guard must go red on each.
"""

TEST = "tests/test_a_value_yaml_cannot_build_is_named.py"

_DOOR = "beeverforge/util/yaml_io.py"

MUTATIONS = [
    ("THE DEFECT: the handler is removed, so the ValueError of `2026-02-30` and the KeyError of "
     "`!!bool x` escape both readers again",
     _DOOR, "        except Exception as exc:\n            raise _cannot_build(node, exc) from exc\n"
     "        self.state_generators",
     "        except ZeroDivisionError as exc:\n            raise _cannot_build(node, exc) from exc\n"
     "        self.state_generators"),

    ("only what is no YAMLError is renamed, so a ConstructorError (`!!seq x`, `!!binary a`) comes "
     "back across lines without its value",
     _DOOR, "        except YamlRefused:\n            raise\n        except Exception as exc:\n"
     "            raise _cannot_build(node, exc) from exc\n        self.state_generators",
     "        except yaml.YAMLError:\n            raise\n        except Exception as exc:\n"
     "            raise _cannot_build(node, exc) from exc\n        self.state_generators"),

    ("the second step of building a collection is not named, so `!!set x`, `!!omap x` and "
     "`!!pairs x` come back in PyYAML's words",
     _DOOR, "        self.state_generators[pending:] = [_naming(step, node)\n",
     "        self.state_generators[pending:] = [step\n"),

    ("the line is counted from zero, one above the value",
     _DOOR, "f\"{_line(node.start_mark)}, as ", "f\"line {node.start_mark.line}, as "),

    ("the value is not named, only its shape",
     _DOOR, "a value YAML cannot build (`{_cut(_spelled(node), _VALUE_SHOWN)}`, ",
     "a value YAML cannot build (`{node.tag}`, "),

    ("a value of any length is named whole",
     _DOOR, "    return text if len(text) <= at else text[:at - 1] + \"…\"\n",
     "    return text\n"),

    ("a family is dropped from the table, so its constructor is never tried",
     TEST, "    \"tag:yaml.org,2002:binary\": ((\"!!binary é\", \"é\"), "
     "(\"!!binary a\", \"a\")),\n", ""),
]
