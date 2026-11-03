"""#121: a `scope_jql` that would escape its `AND (...)` wrapper is refused, not read site-wide.

`within_scope` wraps the scope in parentheses, so a `)` it never opened ORs what follows onto the
project clause, and a string it never closes is closed by the quotes appended after it. Each cut
below breaks one part of `unbalanced_at` or the refusal in `JiraTracker.__init__`: quotes, the
escape inside a string, the escape outside one (Jira's lexer escapes in unquoted strings too, the
review's `labels = a\\") OR (...` bypass), the depth count, and the unterminated-string refusal.
"""

TEST = "tests/test_a_scope_with_an_unbalanced_parenthesis_is_not_a_wider_read.py"
SRC = "beeverforge/adapters/tracker/jira.py"

MUTATIONS = [
    ("no refusal: any scope constructs, a stray ')' included", SRC,
     "        flaw = unbalanced_at(self.scope_jql)\n",
     "        flaw = None\n"),

    ("quotes are ignored, so a ')' inside a string is refused", SRC,
     "        elif char in \"\\\"'\":\n            quote, opened = char, at\n",
     "        elif False:\n            quote, opened = char, at\n"),

    ("no escape handling inside quotes, so an escaped quote ends the string", SRC,
     "        elif char == \"\\\\\":\n            escaped = True\n",
     "        elif char == \"\\\\\" and not quote:\n            escaped = True\n"),

    ("a backslash outside quotes is not an escape, so `a\\\")` hides the stray ')'", SRC,
     "        elif char == \"\\\\\":\n            escaped = True\n",
     "        elif char == \"\\\\\" and quote:\n            escaped = True\n"),

    ("depth never drops, so a ')' after a balanced group passes", SRC,
     "                return \")\", at\n            depth -= 1\n",
     "                return \")\", at\n"),

    ("an unterminated string is accepted", SRC,
     "    return (quote, opened) if quote else None\n",
     "    return None\n"),
]
