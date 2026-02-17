"""Editable-review schema for HIL corrections."""

from __future__ import annotations

import re


ALLOWED_REVIEW_ROOT_FIELDS = {
    "notes",
    "translation",
    "phonetic",
    "synonyms",
    "cefr_level",
    "tense",
    "aspect",
    "mood",
    "voice",
    "finiteness",
    "grammatical_role",
    "tam_construction",
    "part_of_speech",
    "dep_label",
    "features",
}

_ROOT_RE = re.compile(r"^([A-Za-z_]\w*)")


def review_field_root(field_path: str) -> str | None:
    raw = (field_path or "").strip()
    if not raw:
        return None
    m = _ROOT_RE.match(raw)
    if not m:
        return None
    return m.group(1)


def is_allowed_review_field_path(field_path: str) -> bool:
    root = review_field_root(field_path)
    if root is None:
        return False
    return root in ALLOWED_REVIEW_ROOT_FIELDS
