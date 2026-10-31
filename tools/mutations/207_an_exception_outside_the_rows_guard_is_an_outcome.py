"""An exception raised in `perform` outside a row's own guard is an outcome, not a raise (#207).

Run:  .venv/bin/python tools/mutate.py tools/mutations/207_an_exception_outside_the_rows_guard_is_an_outcome.py

`perform` caught a row's exception and answered `failed`/`raised` with a reference; whatever broke
before the row ran (the catalog failing to import, a parameter check that breaks) reached the
caller, and the panel answered an unhandled 500. The outer guard answers it the same way.

Row 1 is the defect as it shipped: no outer handler. Row 2 narrows it to one exception type. Row
3 logs and re-raises, the behaviour #43's branch records. Row 4 answers the wrong reason. Row 5
drops the reference. Row 6 drops the log line, so the answer names a traceback nobody wrote. Row 7
catches `BaseException` without the explicit re-raise, so a cancellation becomes an answer.
"""

TEST = "tests/test_an_exception_outside_the_rows_guard_is_an_outcome.py"

ACTIONS = "beeverforge/actions/__init__.py"

_HANDLER = (
    "    except Exception as exc:\n"
    "        reference = failure_reference()\n"
    '        log.exception("action %s raised outside its guard for %s reference=%s", key, by,\n'
    "                      reference)\n"
    '        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=RAISED,\n'
    "                       reference=reference)\n"
)

MUTATIONS = [
    ("THE DEFECT: nothing outside the row's guard is caught, so the panel answers a 500", ACTIONS,
     _HANDLER, ""),

    ("the outer guard catches only one kind of failure", ACTIONS,
     "    except Exception as exc:\n        reference = failure_reference()\n"
     '        log.exception("action %s raised outside its guard',
     "    except LookupError as exc:\n        reference = failure_reference()\n"
     '        log.exception("action %s raised outside its guard'),

    ("the outer guard logs and re-raises, #43's behaviour", ACTIONS,
     "                      reference)\n"
     '        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=RAISED,\n'
     "                       reference=reference)\n",
     "                      reference)\n"
     "        raise\n"),

    ("the outer guard answers a reason that is not `raised`", ACTIONS,
     "                      reference)\n"
     '        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=RAISED,\n',
     "                      reference)\n"
     '        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=REPORTED_NOTHING,\n'),

    ("the outer guard's answer carries no reference", ACTIONS,
     "                      reference)\n"
     '        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=RAISED,\n'
     "                       reference=reference)\n",
     "                      reference)\n"
     '        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=RAISED)\n'),

    ("the outer guard writes no record of what it caught", ACTIONS,
     '        log.exception("action %s raised outside its guard for %s reference=%s", key, by,\n'
     "                      reference)\n",
     ""),

    ("a cancellation is swallowed into an answer", ACTIONS,
     "    except asyncio.CancelledError:\n"
     "        raise  # a cancellation is the caller's, never an outcome\n"
     "    except Exception as exc:\n"
     "        reference = failure_reference()\n",
     "    except BaseException as exc:\n"
     "        reference = failure_reference()\n"),
]
