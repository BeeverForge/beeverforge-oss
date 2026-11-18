"""Bytes a person wrote in the project's repository, read as UTF-8 text — or one sentence saying
where they stop being UTF-8.

A file saved in another encoding looks right in the editor that saved it, so a
`UnicodeDecodeError` out of a reader tells its author nothing they can see. This names the file,
the offset of the first byte that is not UTF-8 text, and the remedy.

A NUL IS NOT TEXT. UTF-16 written without a byte-order mark (`p\\x00r\\x00...`) is valid UTF-8,
because NUL is a code point, so it decodes and then fails as YAML in words that name neither the
encoding nor the remedy. The first NUL is refused at its offset, as `adapters/extract/text.py`
already reads one.

Neutral on purpose: both the product module and the preview read through it, and neither imports
from the other's domain.
"""

from __future__ import annotations

from pathlib import Path

_UTF16_MARKS = (b"\xff\xfe", b"\xfe\xff")


def decode(raw: bytes, shown: str) -> tuple[str | None, str]:
    """`(text, "")` for UTF-8 bytes with no NUL; `(None, sentence)` otherwise, the sentence naming
    `shown`, the zero-based offset of the first byte that cannot be read, and the remedy."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, _refusal(raw, shown, exc.start)
    if "\x00" in text:
        return None, _refusal(raw, shown, raw.index(b"\x00"))
    return text, ""


def text_of(path: Path, shown: str, refused: type[ValueError] = ValueError) -> str:
    """The file at `path` as UTF-8 text, whatever the machine's locale — or `refused` carrying
    `decode`'s sentence alone: a `ValueError` for a reader that already refuses a file it cannot
    use by catching one (the project's manifest, as `loader` and `explain` read it), or the
    reader's own refusal (a thresholds file, a battery, a fixture's product manifest)."""
    text, unread = decode(path.read_bytes(), shown)
    if text is None:
        raise refused(unread)
    return text


def _refusal(raw: bytes, shown: str, at: int) -> str:
    hint = " (it looks like UTF-16)" if raw.startswith(_UTF16_MARKS) or raw[at] == 0 else ""
    return (f"`{shown}` is not UTF-8 text: the byte at offset {at} (0x{raw[at]:02x}) cannot be "
            f"read{hint} — save it as UTF-8.")
