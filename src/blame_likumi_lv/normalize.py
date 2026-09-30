from __future__ import annotations

import hashlib
import re
import unicodedata


_SPACE_CHARS = "\u00a0\u202f\u2007"
_SPACE_TRANSLATION = str.maketrans({char: " " for char in _SPACE_CHARS})


def normalize_text(text: str) -> str:
    """Return the single canonical text representation used by build and verify.

    This is intentionally a small technical normalization, not a legal-text
    rewrite: Unicode is NFC-normalized, HTML whitespace variants become a
    normal space, line endings are LF, trailing whitespace is removed, and the
    file has exactly one final newline.
    """

    text = text.replace("\ufeff", "")
    text = unicodedata.normalize("NFC", text).translate(_SPACE_TRANSLATION)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

