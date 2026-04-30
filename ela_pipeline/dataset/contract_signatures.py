"""Contract-tree signatures for sentence-level family matching.

These signatures use the actual contract tree shape:
Sentence -> Phrase / Word descendants.
They intentionally avoid lexical content so matching generalizes across
different vocabulary with the same grammatical structure.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _span_start(node: dict[str, Any]) -> int:
    span = node.get("source_span") or {}
    try:
        return int(span.get("start", 0))
    except Exception:
        return 0


def _sorted_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = [child for child in (node.get("linguistic_elements") or []) if isinstance(child, dict)]
    return sorted(children, key=lambda item: (_span_start(item), _norm(item.get("content"))))


def _word_label(node: dict[str, Any]) -> tuple[Any, ...]:
    pos = _norm(node.get("part_of_speech")) or "unknown"
    role = _norm(node.get("grammatical_role")) or "unknown"
    tense = _norm(node.get("tense")) or "null"
    aspect = _norm(node.get("aspect")) or "null"
    mood = _norm(node.get("mood")) or "null"
    voice = _norm(node.get("voice")) or "null"
    finiteness = _norm(node.get("finiteness")) or "null"
    return ("word", pos, role, tense, aspect, mood, voice, finiteness)


def _phrase_label(node: dict[str, Any]) -> tuple[Any, ...]:
    pos = _norm(node.get("part_of_speech")) or "unknown"
    role = _norm(node.get("grammatical_role")) or "unknown"
    return ("phrase", pos, role)


def _sentence_label(node: dict[str, Any]) -> tuple[Any, ...]:
    voice = _norm(node.get("voice")) or "null"
    tense = _norm(node.get("tense")) or "null"
    aspect = _norm(node.get("aspect")) or "null"
    mood = _norm(node.get("mood")) or "null"
    finiteness = _norm(node.get("finiteness")) or "null"
    return ("sentence", voice, tense, aspect, mood, finiteness)


def _node_label(node: dict[str, Any]) -> tuple[Any, ...]:
    node_type = _norm(node.get("type"))
    if node_type == "word":
        return _word_label(node)
    if node_type == "phrase":
        return _phrase_label(node)
    return _sentence_label(node)


def contract_exact_signature(node: dict[str, Any]) -> tuple[Any, ...]:
    children = tuple(contract_exact_signature(child) for child in _sorted_children(node))
    return (_node_label(node), children)


def contract_presence_signature(signature: tuple[Any, ...]) -> tuple[Any, ...]:
    label = signature[0]
    children = signature[1] if len(signature) > 1 else ()
    compressed = tuple(sorted({contract_presence_signature(child) for child in children}, key=repr))
    return (label, compressed)


def contract_bucketed_signature(signature: tuple[Any, ...]) -> tuple[Any, ...]:
    label = signature[0]
    children = signature[1] if len(signature) > 1 else ()
    child_counter: Counter[tuple[Any, ...]] = Counter(contract_bucketed_signature(child) for child in children)
    compressed = tuple(
        sorted(
            ((child_sig, "1" if count == 1 else "2+" if count == 2 else "3+") for child_sig, count in child_counter.items()),
            key=repr,
        )
    )
    return (label, compressed)
