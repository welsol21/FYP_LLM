"""Quality checks for generated linguistic notes."""

from __future__ import annotations

import re

_BAD_PATTERNS = [
    re.compile(r"\bnode[_:\-]?\w*", re.IGNORECASE),
    re.compile(r"\bpart_of_speech\b", re.IGNORECASE),
    re.compile(r"\bnode_type\b", re.IGNORECASE),
    re.compile(r"\bcontent\b", re.IGNORECASE),
    re.compile(r"\btense\b", re.IGNORECASE),
    re.compile(r"^true$", re.IGNORECASE),
    re.compile(r"^false$", re.IGNORECASE),
    re.compile(r"^[\W_]+$"),
]


def sanitize_note(note: str) -> str:
    return " ".join(note.strip().split())


def is_valid_note(note: str) -> bool:
    text = sanitize_note(note)
    if not text:
        return False

    if len(text) < 12:
        return False

    if len(text.split()) < 3:
        return False

    for pattern in _BAD_PATTERNS:
        if pattern.search(text):
            return False

    return True
