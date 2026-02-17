"""Helpers to bridge contract nodes to visualizer payloads and editor-style field edits."""

from __future__ import annotations

import copy
import re
from typing import Any


_SEGMENT_RE = re.compile(r"^([A-Za-z_]\w*)(?:\[(\d+)\])?$")


def _node_to_visualizer(node: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "node_id": node.get("node_id", ""),
        "type": node.get("type", ""),
        "content": node.get("content", ""),
        "part_of_speech": node.get("part_of_speech"),
        "cefr_level": node.get("cefr_level"),
        "children": [],
    }
    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            payload["children"].append(_node_to_visualizer(child))
    return payload


def build_visualizer_payload(sentence_node: dict[str, Any]) -> dict[str, Any]:
    """Convert one sentence node into stable visualizer-friendly payload."""
    return _node_to_visualizer(sentence_node)


def build_visualizer_payload_for_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert full contract document into visualizer payload list."""
    out: list[dict[str, Any]] = []
    for sentence_text, sentence_node in (doc or {}).items():
        if not isinstance(sentence_node, dict):
            continue
        out.append(
            {
                "sentence_text": sentence_text,
                "tree": build_visualizer_payload(sentence_node),
            }
        )
    return out


def _iter_nodes(node: dict[str, Any]):
    yield node
    for child in node.get("linguistic_elements", []) or []:
        if isinstance(child, dict):
            yield from _iter_nodes(child)


def _find_node_by_id(sentence_node: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for n in _iter_nodes(sentence_node):
        if str(n.get("node_id", "")) == node_id:
            return n
    return None


def _resolve_path_container(root: dict[str, Any], field_path: str) -> tuple[Any, str | None, int | None]:
    segments = [seg for seg in field_path.split(".") if seg]
    if not segments:
        raise ValueError("field_path must not be empty")

    current: Any = root
    for seg in segments[:-1]:
        m = _SEGMENT_RE.match(seg)
        if not m:
            raise ValueError(f"Invalid path segment: {seg!r}")
        key = m.group(1)
        idx_str = m.group(2)
        if not isinstance(current, dict):
            raise ValueError(f"Expected dict at segment {seg!r}")
        if key not in current:
            current[key] = [] if idx_str is not None else {}
        current = current[key]
        if idx_str is not None:
            idx = int(idx_str)
            if not isinstance(current, list):
                raise ValueError(f"Expected list at segment {seg!r}")
            while len(current) <= idx:
                current.append({})
            current = current[idx]

    last = segments[-1]
    m = _SEGMENT_RE.match(last)
    if not m:
        raise ValueError(f"Invalid path segment: {last!r}")
    key = m.group(1)
    idx_str = m.group(2)
    idx = int(idx_str) if idx_str is not None else None
    return current, key, idx


def apply_node_edit(
    doc: dict[str, Any],
    *,
    sentence_text: str,
    node_id: str,
    field_path: str,
    new_value: Any,
) -> dict[str, Any]:
    """Apply one editor-style patch by node_id/field_path and return updated copy."""
    updated = copy.deepcopy(doc)
    sentence_node = updated.get(sentence_text)
    if not isinstance(sentence_node, dict):
        raise KeyError(f"Sentence not found: {sentence_text!r}")
    target = _find_node_by_id(sentence_node, node_id)
    if target is None:
        raise KeyError(f"node_id not found: {node_id!r}")

    container, key, idx = _resolve_path_container(target, field_path)
    if not isinstance(container, dict):
        raise ValueError(f"Invalid edit path container for {field_path!r}")
    if idx is None:
        container[key] = new_value
        return updated

    if key not in container or not isinstance(container[key], list):
        container[key] = []
    lst = container[key]
    while len(lst) <= idx:
        lst.append(None)
    lst[idx] = new_value
    return updated
