"""A parameter whose value is not of the type the row declares is refused before the row runs (#211).

`POST /api/act/product_status` with a list for `project` reached the registry and was answered
with an ERROR and a traceback. `_check_params` now reads each parameter's annotation from the
row's runner (`_declared_types`) and refuses a value that is not of that type, as `invalid` with
reason `bad_parameters`, in one sentence naming the parameter, the type it must be and the kind of
value it was given in the caller's terms. Each row below is one way that could come undone, and
the guard must go red on each.
"""

TEST = "tests/test_a_parameter_of_the_wrong_type_is_refused.py"

_ACTIONS = "beeverforge/actions/__init__.py"

MUTATIONS = [
    ("THE DEFECT: the type check is removed from `_check_params`, so a list for `project` reaches "
     "the registry again",
     _ACTIONS, "        if accepted and not isinstance(params[p], accepted):\n",
     "        if False:\n"),

    ("`_declared_types` returns nothing, so no parameter has a type to be checked against",
     _ACTIONS,
     "    return {name: prm.annotation for name, prm in sig.parameters.items()\n"
     "            if isinstance(prm.annotation, (str, type))}\n",
     "    return {}\n"),

    ("a `str` parameter refuses nothing: a list or an object passes as a string",
     _ACTIONS, "_STR = (\"a string\", (str, int, float, bool, type(None)))\n",
     "_STR = (\"a string\", ())\n"),

    ("a `bool` parameter accepts a string, so \"no\" reaches `bool()` and means yes",
     _ACTIONS, "_BOOL = (\"true or false\", (bool, type(None)))\n",
     "_BOOL = (\"true or false\", (bool, str, type(None)))\n"),

    ("the refusal is coded as something other than `invalid` / `bad_parameters`",
     _ACTIONS, "        return refused(INVALID, problem, reason=BAD_PARAMETERS)\n",
     "        return refused(FAILED, problem, reason=BAD_REF)\n"),

    ("the sentence does not name the parameter",
     _ACTIONS, "takes {p} as {word}, not ", "takes it as {word}, not "),

    ("the row is run before the check, so a refused call has already done its work",
     _ACTIONS, "    problem = _check_params(found, params)\n",
     "    try:\n"
     "        await found.run(by=by, **params)\n"
     "    except Exception:\n"
     "        pass\n"
     "    problem = _check_params(found, params)\n"),

    # the wording: the caller sends JSON, not Python, and the article is in the word
    ("a dict is named \"a dict\", in Python's terms rather than the caller's",
     _ACTIONS, "dict: \"an object\"", "dict: \"a dict\""),

    ("an int is named \"a int\", with the wrong article",
     _ACTIONS, "int: \"a number\"", "int: \"a int\""),

    ("a list is named \"a array\", with the wrong article",
     _ACTIONS, "list: \"a list\"", "list: \"a array\""),

    ("a value of a kind the table does not know is named by its Python class name",
     _ACTIONS, "_KIND.get(type(params[p]), 'a value of another kind')",
     "_KIND.get(type(params[p]), type(params[p]).__name__)"),
]
