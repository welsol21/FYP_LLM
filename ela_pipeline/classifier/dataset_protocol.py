"""Dataset normalization protocol for classifier training rows.

This module enforces a single canonical row shape aligned with the CEFR
grammar/lexical parsing guide:
- canonical grammar class ids
- non-empty note blueprints (3 pedagogical bands)
- stable CEFR/source_text/grammar_label fields
"""

from __future__ import annotations

from typing import Any

from .class_taxonomy import normalize_grammar_class_id
from .grammar_blueprints import PEDAGOGICAL_CLASS_SPECS, build_note_blueprints

REQUIRED_BLUEPRINT_KEYS = ("elementary_text", "intermediate_text", "advanced_text")


def canonicalize_grammar_classes(value: Any, *, keep_unknown: bool = False) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        cid = normalize_grammar_class_id(str(item or "").strip())
        if not cid:
            continue
        if cid not in PEDAGOGICAL_CLASS_SPECS and not keep_unknown:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def _fallback_blueprints(*, cefr: str, class_id: str) -> dict[str, str]:
    readable = class_id.replace("_", " ").strip() if class_id else "grammar pattern"
    level = str(cefr or "B1").strip().upper() or "B1"
    return {
        "elementary_text": f"[{level}] Identify {readable} in this context.",
        "intermediate_text": f"[{level}] Explain how {readable} works in this sentence.",
        "advanced_text": f"[{level}] Analyze the discourse role of {readable} in context.",
    }


def ensure_note_blueprints(
    *,
    note_blueprints: Any,
    cefr_label: str,
    grammar_classes: list[str],
) -> dict[str, str]:
    existing = note_blueprints if isinstance(note_blueprints, dict) else {}
    primary = str(grammar_classes[0]).strip().lower() if grammar_classes else ""
    generated = build_note_blueprints(grammar_classes=[primary] if primary else [], cefr_level=cefr_label)
    fallback = _fallback_blueprints(cefr=cefr_label, class_id=primary)

    out: dict[str, str] = {}
    for key in REQUIRED_BLUEPRINT_KEYS:
        val = str(existing.get(key) or "").strip()
        if not val:
            val = str(generated.get(key) or "").strip()
        if not val:
            val = fallback[key]
        out[key] = val
    return out


def normalize_classifier_row(row: dict[str, Any]) -> dict[str, Any]:
    source_text = str(
        row.get("source_text")
        or row.get("text")
        or ""
    ).strip()
    cefr_label = str(row.get("cefr_label") or row.get("cefr_level") or "").strip().upper()
    grammar_classes = canonicalize_grammar_classes(row.get("grammar_classes"))
    note_blueprints = ensure_note_blueprints(
        note_blueprints=row.get("note_blueprints"),
        cefr_label=cefr_label,
        grammar_classes=grammar_classes,
    )

    out = dict(row)
    if source_text:
        out["source_text"] = source_text
    if cefr_label:
        out["cefr_label"] = cefr_label
    if grammar_classes:
        out["grammar_classes"] = grammar_classes
    out["note_blueprints"] = note_blueprints
    if grammar_classes:
        out["grammar_label"] = "|".join(sorted(grammar_classes))
    return out
