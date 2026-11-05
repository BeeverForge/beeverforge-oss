"""A credential the implementing agent echoes never reaches the pull request: it is shown as
`[credential withheld]`, and the body says so (#885).

Claims:
  - the executor's quote withholds a credential — a token by its prefix, the value of an
    `Authorization` header, a URL's userinfo, a secret of this process — on the RAW text, whole:
    before `_neutralised` (which escapes `_`, so `ghp\\_…` matches nothing and renders whole) and
    before `splitlines` (a key that spans lines is never found line by line);
  - each later pass's line withholds it too, before the whitespace fold (the multi-line key) and
    before the 200-character cut (a token the cut splits leaves a head no shape matches);
  - a URL's userinfo is REPLACED by the marker in the body, never silently dropped;
  - `scrub_credentials` withholds an `Authorization` value after a NAMED scheme (any word there is
    prose: "Authorization: handled centrally …"), in any case, after `:` or `=`, a JSON key's
    quote included; a header value only from 8 characters, and only with a credential's mark (a
    digit, trailing `=` padding, a sentence's full stop after it included, or a single lowercase
    letter before a single uppercase one; never a `+`, a `/` or an `=` inside the value), so
    "Authorization: Basic authentication is kept …" and "… username/password pairs …" are prose;
    a bare `Bearer` value only when it is 16 token68
    characters with a digit; `$` is never part of a value, so `Bearer $GH_TOKEN_2` stays prose;
  - a `Digest` or SigV4 header withholds its `response=` / `Signature=` only, and keeps the rest
    of its parameter list as written (never the marker on the first parameter's name), and a
    SHA-256 response (64 hex) whole, not its first 32;
  - an `Authorization` value with NO scheme is withheld only when it is 16 token68 characters
    with a digit, and never `AWS4-HMAC-SHA256`, the SigV4 scheme word (#198);
  - the value under a secret-named name (`_SECRET_NAME`'s words plus a header's `API-KEY`) is
    withheld after `=` or `:`, read to its natural end (its closing quote, or whitespace, `,`,
    `;`, a quote, a backtick or an `&` before another `name=`), the floor of the header form's
    credential's mark on the whole value, and withheld whole — never through the header value's
    alphabet (review of PR #445) — never a value that starts with `$` or a URL scheme, the name and
    separator kept; SigV4's `Credential` and `X-Amz-Credential` are quoted as written (#198);
  - a presigned URL's `X-Amz-Signature=<64 hex>` is withheld (#198);
  - a `Digest` / SigV4 parameter list is read as comma-separated `name=value` pairs, so a header
    longer than 1,000 characters is withheld and a `response=` after a prose word is not (#198);
  - the userinfo pattern needs its `@`, so a URL with no userinfo keeps its host, and a userinfo of
    exactly `git` (an SSH remote's user) is no credential;
  - the platform's `_redact` regex (https userinfo only) is no substitute;
  - the claim above the quote names the withholding.
"""

TEST = "tests/test_a_credential_the_agent_echoes_never_reaches_the_pull_request.py"
MACHINE = "beeverforge/orchestrator/machine.py"
MODEL = "beeverforge/product/model.py"
#: The preservation property: the cuts that withhold too much must turn THIS test red.
PROSE = TEST + "::test_plain_prose_is_quoted_exactly_as_before"

MUTATIONS = [
    # ── the executor's quote ────────────────────────────────────────────────────────────────────
    ("the quote withholds nothing", MACHINE,
     "    text = _without_credentials(text)\n"
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n',
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n'),
    ("the quote withholds after neutralising each line", MACHINE,
     "    text = _without_credentials(text)\n"
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n',
     '    return [f"> {_without_credentials(_neutralised(line))}" if line.strip() else ">"\n'
     "            for line in text.splitlines()]\n"),
    ("the quote withholds line by line", MACHINE,
     "    text = _without_credentials(text)\n"
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n',
     '    return [f"> {_neutralised(_without_credentials(line))}" if line.strip() else ">"\n'
     "            for line in text.splitlines()]\n"),
    # ── a later pass's line ─────────────────────────────────────────────────────────────────────
    ("a pass line withholds nothing", MACHINE,
     '    words = " ".join(_without_credentials(final_text(res)).split())\n',
     '    words = " ".join(final_text(res).split())\n'),
    ("a pass line withholds after the 200-character cut", MACHINE,
     '    words = " ".join(_without_credentials(final_text(res)).split())\n'
     "    if not words:\n"
     '        return "the pass ended without a final message"\n'
     "    cut = words[:AGENT_PASS_WORDS_MAX]\n",
     '    words = " ".join(final_text(res).split())\n'
     "    if not words:\n"
     '        return "the pass ended without a final message"\n'
     "    cut = _without_credentials(words[:AGENT_PASS_WORDS_MAX])\n"),
    ("a pass line withholds after the whitespace fold", MACHINE,
     '    words = " ".join(_without_credentials(final_text(res)).split())\n',
     '    words = _without_credentials(" ".join(final_text(res).split()))\n'),
    # ── what is withheld, and how it is said ────────────────────────────────────────────────────
    ("a URL's userinfo is dropped with no marker", MACHINE,
     '    return scrub_credentials(text, userinfo=WITHHELD_CREDENTIAL + "@")\n',
     "    return scrub_credentials(text)\n"),
    ("no Authorization value is withheld", MODEL,
     "    text = _AUTHORIZATION.sub(lambda m: (m.group(1) or m.group(2)) + WITHHELD_CREDENTIAL, "
     "text)\n",
     ""),
    ("any word after Bearer is withheld", MODEL,
     '    r"|(\\bBearer[ \\t]+)(?=[\\w.~+/-]*\\d)[\\w.~+/-]{16,}=*", re.IGNORECASE)\n',
     '    r"|(\\bBearer[ \\t]+)[\\w.~+/-]+=*", re.IGNORECASE)\n', PROSE),
    # re-pinned 2026-10-21: the header value moved to its own line with the credential's mark;
    # re-pinned again: `+` and `/` left the mark set (review on cfe48e02); and again: `=` counts
    # only as trailing padding (review on 34209477). #198: the same line is now `_MARKED_VALUE`;
    # re-pinned on the review of PR #445: its case pair is `_CASE_PAIR`, shared with the secret-
    # named shape, which reads its own value (`_WHOLE_VALUE`) — so this cut and the two below cut
    # the header form only
    ("a variable reference is read as a value", MODEL,
     '    r"(?=[\\w.~+/-]*(?:\\d|=+(?!\\.?[\\w~+/-])|" + _CASE_PAIR + r"))[\\w.~+/-]{8,}=*"\n',
     '    r"(?=[\\w.~+/$-]*(?:\\d|=+(?!\\.?[\\w~+/-])|" + _CASE_PAIR + r"))[\\w.~+/$-]{8,}=*"\n', PROSE),
    ("a slash is a credential's mark", MODEL, '(?:\\d|=+(?!\\.?[\\w~+/-])|',
     '(?:\\d|[+/]|=+(?!\\.?[\\w~+/-])|', PROSE),
    # review on 34209477: `=` is a mark only as the padding that ends a value
    ("padding is not a credential's mark", MODEL, '|=+(?!\\.?[\\w~+/-])|', '|'),
    # review on c0bb69c0: a full stop after the padding ends the sentence, not the value
    ("padding before a sentence's full stop is no mark", MODEL, '=+(?!\\.?[\\w~+/-])',
     '=+(?![\\w.~+/-])'),
    ("any = is a credential's mark", MODEL, '=+(?!\\.?[\\w~+/-])', '=', PROSE),
    # review on c0bb69c0: one lowercase letter followed by one capital is the mark, not by two
    ("a case pair needs a second capital", MODEL, '(?-i:[a-z][A-Z])', '(?-i:[a-z][A-Z]{2})'),
    ("a word after an Authorization scheme is withheld", MODEL,
     '    r"(?=[\\w.~+/-]*(?:\\d|=+(?!\\.?[\\w~+/-])|" + _CASE_PAIR + r"))[\\w.~+/-]{8,}=*"\n',
     '    r"(?=[\\w.~+/-]*(?:\\d|=+(?!\\.?[\\w~+/-])|" + _CASE_PAIR + r"))[\\w.~+/-]+=*"\n', PROSE),
    ("a header value needs no credential's mark", MODEL,
     '    r"(?=[\\w.~+/-]*(?:\\d|=+(?!\\.?[\\w~+/-])|" + _CASE_PAIR + r"))[\\w.~+/-]{8,}=*"\n',
     '    r"[\\w.~+/-]{8,}=*"\n', PROSE),
    ("any word is read as an Authorization scheme", MODEL,
     '(?:Bearer|Basic|token|Bot|Negotiate|NTLM)',  # re-pinned 2026-10-21: Digest and AWS4 left for _SIGNED_PARAMETER
     "[A-Za-z][\\w-]*", PROSE),
    # review on 28e5da94: the forms the shape's comment claims, each its own cut
    ("a lowercase header name is not read", MODEL,
     '    r"|(\\bBearer[ \\t]+)(?=[\\w.~+/-]*\\d)[\\w.~+/-]{16,}=*", re.IGNORECASE)\n',
     '    r"|(\\bBearer[ \\t]+)(?=[\\w.~+/-]*\\d)[\\w.~+/-]{16,}=*", 0)\n'),
    ("a JSON key's closing quote ends the shape", MODEL,
     '(\\bAuthorization[\\"\']?\\s*',
     '(\\bAuthorization\\s*'),
    ("Authorization= is not read", MODEL,
     '\\s*[:=]\\s*',
     '\\s*:\\s*'),
    ("an ssh remote's git user is shown as a withheld credential", MODEL,
     '    text = _USERINFO.sub(lambda m: m.group(0) if userinfo and m.group(0)[len(m.group(1)):] == "git@"\n                         else m.group(1) + userinfo, text)\n',
     '    text = _USERINFO.sub(lambda m: m.group(1) + userinfo, text)\n', PROSE),
    ("any user that starts with git is exempt", MODEL,
     'm.group(0)[len(m.group(1)):] == "git@"',
     'm.group(0)[len(m.group(1)):].startswith("git")'),
    ("Bot is not a scheme", MODEL,
     "|token|Bot|",
     "|token|"),
    ("Negotiate is not a scheme", MODEL,
     "|Negotiate|",
     "|"),
    ("NTLM is not a scheme", MODEL,
     "|NTLM)",
     ")"),
    # decision on the review of 5fe330d2: a parameter list withholds its secret parameter only
    ("Digest's response is quoted", MODEL,
     '\\bresponse[',
     '\\bresponse_never['),
    ("AWS4-HMAC-SHA256's Signature is quoted", MODEL,
     '\\bSignature[',
     '\\bSignature_never['),
    # review on 34209477: RFC 7616's SHA-256 response is 64 hex
    ("a Digest response is read to 32 hex only", MODEL, '\\"?)[0-9a-f]{32,}"', '\\"?)[0-9a-f]{32}"'),
    ("Digest is read in one case only", MODEL, '[0-9a-f]{64}", re.IGNORECASE)', '[0-9a-f]{64}")'),
    ("Digest is read as a one-token scheme, its first parameter's name withheld", MODEL,
     '(?:Bearer|Basic|token|Bot|Negotiate|NTLM)',
     '(?:Bearer|Basic|Digest|token|Bot|Negotiate|NTLM)'),
    ("AWS4-HMAC-SHA256 is read as a one-token scheme, its first parameter's name withheld", MODEL,
     '(?:Bearer|Basic|token|Bot|Negotiate|NTLM)',
     '(?:Bearer|Basic|token|Bot|Negotiate|NTLM|AWS4-HMAC-SHA256)'),
    # ── #198: the shapes another machine's credential takes ──────────────────────────────────────
    ("a scheme-less Authorization value is quoted", MODEL,
     "    text = _SCHEMELESS_AUTHORIZATION.sub(lambda m: m.group(1) + WITHHELD_CREDENTIAL, text)\n",
     ""),
    ("a scheme-less Authorization value needs no digit", MODEL,
     '    r"(?=[\\w.~+/-]*\\d)[\\w.~+/-]{16,}=*", re.IGNORECASE)\n',
     '    r"[\\w.~+/-]{16,}=*", re.IGNORECASE)\n', PROSE),
    ("a scheme-less Authorization value needs 8 characters, not 16", MODEL,
     '    r"(?=[\\w.~+/-]*\\d)[\\w.~+/-]{16,}=*", re.IGNORECASE)\n',
     '    r"(?=[\\w.~+/-]*\\d)[\\w.~+/-]{8,}=*", re.IGNORECASE)\n', PROSE),
    ("the SigV4 scheme word is read as a scheme-less value", MODEL,
     "(?!AWS4-HMAC-SHA256\\b)", ""),
    ("a hyphenated Api-Key header is not secret-named", MODEL, "|API-KEY)", ")"),
    ("a secret-named value is quoted", MODEL,
     "    text = _SECRET_NAMED_VALUE.sub(_secret_named_value_withheld, text)\n", ""),
    # re-pinned on the review of PR #445: the value is `_WHOLE_VALUE`, read to its natural end
    ("a secret-named value needs no credential's mark", MODEL,
     '    r"([\\"\']?[ \\t]*[:=][ \\t]*[\\"\']?)" + _WHOLE_VALUE, re.IGNORECASE)\n',
     '    r"([\\"\']?[ \\t]*[:=][ \\t]*[\\"\']?)(?![$])(?![a-z][a-z0-9+.-]{0,31}://)" + _VALUE_CHAR\n'
     '    + r"{8,}", re.IGNORECASE)\n', PROSE),
    # review of PR #445: a password is written with punctuation, and is read to its natural end
    ("a secret-named value is read through the header value's alphabet", MODEL,
     '    r"([\\"\']?[ \\t]*[:=][ \\t]*[\\"\']?)" + _WHOLE_VALUE, re.IGNORECASE)\n',
     '    r"([\\"\']?[ \\t]*[:=][ \\t]*[\\"\']?)" + _MARKED_VALUE, re.IGNORECASE)\n'),
    ("a double-quoted value is read to its first space, not its closing quote", MODEL,
     '    r"(?<=\\")(?=[^\\"\\n]{0,64}?(?:\\d|" + _CASE_PAIR + r"|={1,2}\\"))[^\\"\\n]{8,}(?=\\")"\n',
     '    r"(?<=\\")(?!)"\n'),
    ("a single-quoted value is read to its first space, not its closing quote", MODEL,
     '    r"|(?<=\')(?=[^\'\\n]{0,64}?(?:\\d|" + _CASE_PAIR + r"|={1,2}\'))[^\'\\n]{8,}(?=\')"\n',
     '    r"|(?<=\')(?!)"\n'),
    ("a value that starts with $ is read", MODEL, 'r"(?![$])(?![a-z]', 'r"(?![a-z]', PROSE),
    ("a value that starts with a URL scheme is read", MODEL,
     '(?![a-z][a-z0-9+.-]{0,31}://)(?:"', '(?:"', PROSE),
    ("an & always continues an unquoted value", MODEL,
     '|&(?![\\w-]{1,64}=))"', '|&)"'),
    ("a secret-named name is read with no bound on its length", MODEL,
     '    r"(?<![\\w-])([\\w-]{0,64}?(?:" + _SECRET_NAME.pattern + r"|API-KEY)[\\w-]{0,64})"\n',
     '    r"([\\w-]*?(?:" + _SECRET_NAME.pattern + r"|API-KEY)[\\w-]*)"\n'),
    ("a secret-named name is read from any character, not where a name starts", MODEL,
     '    r"(?<![\\w-])([\\w-]{0,64}?(?:" + _SECRET_NAME.pattern + r"|API-KEY)[\\w-]{0,64})"\n',
     '    r"([\\w-]{0,64}?(?:" + _SECRET_NAME.pattern + r"|API-KEY)[\\w-]{0,64})"\n'),
    ("SigV4's Credential header parameter is withheld", MODEL,
     'if name == "credential" or name.endswith("amz-credential"):',
     'if name.endswith("amz-credential"):'),
    ("a presigned URL's X-Amz-Credential is withheld", MODEL,
     'if name == "credential" or name.endswith("amz-credential"):',
     'if name == "credential":', PROSE),
    ("a presigned URL's signature is quoted", MODEL,
     "    text = _PRESIGNED_SIGNATURE.sub(lambda m: m.group(1) + WITHHELD_CREDENTIAL, text)\n", ""),
    ("a parameter list is scanned to 1,000 characters, not read as pairs", MODEL,
     '    r"(?:[\\w-]+[ \\t]*=[ \\t]*(?:\\"[^\\"\\n]*\\"|[^\\s,\\"]*)[ \\t]*,[ \\t]*)*?"\n',
     '    r"[^\\n]{0,1000}?"\n'),
    ("a parameter list is scanned freely, not read as pairs", MODEL,
     '    r"(?:[\\w-]+[ \\t]*=[ \\t]*(?:\\"[^\\"\\n]*\\"|[^\\s,\\"]*)[ \\t]*,[ \\t]*)*?"\n',
     '    r"[^\\n]*?"\n'),
    ("a quoted parameter value ends at a comma inside its quotes", MODEL,
     '(?:\\"[^\\"\\n]*\\"|', '(?:\\"[^\\",\\n]*\\"|'),
    ("a URL with no userinfo loses its host", MODEL,
     '_USERINFO = re.compile(r"(\\b[a-zA-Z][a-zA-Z0-9+.-]*://)[^\\s/@]+@")\n',
     '_USERINFO = re.compile(r"(\\b[a-zA-Z][a-zA-Z0-9+.-]*://)[^\\s/@]+")\n', PROSE),
    ("the adapters' _redact stands in for the withholding", MACHINE,
     '    return scrub_credentials(text, userinfo=WITHHELD_CREDENTIAL + "@")\n',
     '    return re.sub(r"(https?://)[^@/\\s]+@", r"\\1***@", text)\n'),
    # ── the claim ───────────────────────────────────────────────────────────────────────────────
    ("the claim names no withholding", MACHINE,
     '_CLAIM = ("This is the implementing agent\'s own account, as it wrote it, with any credential '
     'in it "\n'
     '          f"shown as {WITHHELD_CREDENTIAL}. No gate checked it, and the reviewer was not shown '
     'it.")\n',
     '_CLAIM = ("This is the implementing agent\'s own account, as it wrote it. No gate checked it, '
     'and "\n'
     '          "the reviewer was not shown it.")\n'),
]
