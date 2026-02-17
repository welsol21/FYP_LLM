"""Adapt legacy contract-like payloads into current unified contract shape."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_NULLABLE_TAM_FIELDS = ("tense", "aspect", "mood", "voice", "finiteness")


def _adapt_node(node: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(node)

    for field in _NULLABLE_TAM_FIELDS:
        if out.get(field) == "null":
            out[field] = None

    if "notes" not in out and isinstance(out.get("linguistic_notes"), list):
        out["notes"] = [
            {
                "text": str(text),
                "kind": "syntactic",
                "confidence": None,
                "source": "legacy",
            }
            for text in out.get("linguistic_notes", [])
            if isinstance(text, str) and text.strip()
        ]

    node_type = str(out.get("type") or "")
    if "cefr_level" not in out:
        if node_type == "Sentence" and isinstance(out.get("sentence_cefr"), str):
            out["cefr_level"] = out["sentence_cefr"]
        elif node_type == "Phrase" and isinstance(out.get("phrase_cefr"), str):
            out["cefr_level"] = out["phrase_cefr"]
        elif node_type == "Word" and isinstance(out.get("word_cefr"), str):
            out["cefr_level"] = out["word_cefr"]

    if "linguistic_elements" not in out or not isinstance(out.get("linguistic_elements"), list):
        out["linguistic_elements"] = []

    children = []
    for child in out.get("linguistic_elements", []):
        if isinstance(child, dict):
            children.append(_adapt_node(child))
    out["linguistic_elements"] = children

    if "schema_version" not in out:
        out["schema_version"] = "v2"

    return out


def adapt_legacy_contract_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy sentence payload map into unified contract-compatible map."""
    out: dict[str, Any] = {}
    for sentence_text, sentence_node in (doc or {}).items():
        if not isinstance(sentence_node, dict):
            continue
        out[str(sentence_text)] = _adapt_node(sentence_node)
    return out
