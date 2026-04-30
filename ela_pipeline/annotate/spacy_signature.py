"""Helpers for compact spaCy-style structural signatures."""

from __future__ import annotations

import hashlib
from typing import Any


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _sort_children(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            int((item.get("source_span") or {}).get("start", 0)),
            int((item.get("source_span") or {}).get("end", 0)),
            0 if str(item.get("type") or "") == "Word" else 1,
        ),
    )


def _signature_label(node: dict[str, Any]) -> str:
    node_type = str(node.get("type") or "").strip()
    if node_type == "Sentence":
        return "ROOT"
    if node_type == "Word":
        return _norm(node.get("dep_label")).lower()
    return ""


def build_spacy_signature(node: dict[str, Any], *, depth: int = 2) -> list[str]:
    labels: list[str] = []

    def walk(cur: dict[str, Any], remaining_depth: int) -> None:
        label = _signature_label(cur)
        if label:
            labels.append(label)
        if remaining_depth <= 0:
            return
        children = [child for child in (cur.get("linguistic_elements") or []) if isinstance(child, dict)]
        for child in _sort_children(children):
            walk(child, remaining_depth - 1)

    walk(node, depth)
    return labels


def spacy_signature_text(node: dict[str, Any], *, depth: int = 2) -> str:
    return " -> ".join(build_spacy_signature(node, depth=depth))


def spacy_signature_family_id(signature_text: str) -> str:
    digest = hashlib.sha1(signature_text.encode("utf-8")).hexdigest()[:12]
    return f"spacy_sig_{digest}"
