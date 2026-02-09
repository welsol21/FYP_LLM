"""Quality checks for generated linguistic notes."""

from __future__ import annotations

import re

_BAD_PATTERNS = [
    re.compile(r"\bnode[_:\-]?\w*", re.IGNORECASE),
    re.compile(r"\bpart_of_speech\b", re.IGNORECASE),
    re.compile(r"\bnode_type\b", re.IGNORECASE),
    re.compile(r"\bcontent\b", re.IGNORECASE),
    re.compile(r"^true$", re.IGNORECASE),
    re.compile(r"^false$", re.IGNORECASE),
    re.compile(r"^[\W_]+$"),
]

_GENERIC_TEMPLATE_PATTERNS = [
    re.compile(r"\bsubordinate clause of concession\b", re.IGNORECASE),
    re.compile(r"\bsubordinate clause of reason\b", re.IGNORECASE),
    re.compile(r"\bsubordinate clause of reference\b", re.IGNORECASE),
    re.compile(r"\bverb-?centred phrase expressing what happens\b", re.IGNORECASE),
    re.compile(r"\bverb-?centred sentence expressing what happens\b", re.IGNORECASE),
    re.compile(r"\bverb-?centred speech\b", re.IGNORECASE),
    re.compile(r"\bverb-?centred subject\b", re.IGNORECASE),
    re.compile(r"\bsimple expression with an initial\b", re.IGNORECASE),
    re.compile(r"\bsimple note with\b", re.IGNORECASE),
    re.compile(r"\bshort (educational|linguistic|note)\b", re.IGNORECASE),
    re.compile(r"\bsensibilisation\b", re.IGNORECASE),
    re.compile(r"\bemphase\b", re.IGNORECASE),
    re.compile(r"\bsensation posed\b", re.IGNORECASE),
]


def sanitize_note(note: str) -> str:
    return " ".join(note.strip().split())


def is_generic_template(note: str) -> bool:
    text = sanitize_note(note)
    for pattern in _GENERIC_TEMPLATE_PATTERNS:
        if pattern.search(text):
            return True
    return False


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

    if is_generic_template(text):
        return False

    return True
