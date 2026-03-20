"""Deterministic context serialization for note generation."""

from __future__ import annotations

from typing import Any


EXCLUDED_FROM_NOTE_CONTEXT = {
    "active_translation_provider",
    "linguistic_notes",
    "node_id",
    "note_generator_version",
    "phonetic",
    "schema_version",
    "synonyms",
    "translations",
}


def _norm(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).strip()
    return text if text else "null"


def _has_value(value: Any) -> bool:
    return _norm(value) != "null"


def _classes_text(classes: Any) -> str:
    if not isinstance(classes, list):
        return "none"
    out: list[str] = []
    for item in classes:
        if isinstance(item, dict):
            cid = str(item.get("class_id") or "").strip().lower()
            if cid:
                out.append(cid)
    return ",".join(sorted(set(out))) if out else "none"


def _span_text(span: Any) -> str:
    if not isinstance(span, dict):
        return "null"
    start = span.get("start")
    end = span.get("end")
    if isinstance(start, int) and isinstance(end, int):
        return f"{start}:{end}"
    return "null"


def _field_block(prefix: str, node: dict[str, Any] | None) -> list[str]:
    if not isinstance(node, dict):
        return [f"{prefix}.type=null"]

    parts = [f"{prefix}.type={_norm(node.get('type'))}"]

    if _has_value(node.get("content")):
        parts.append(f"{prefix}.content={_norm(node.get('content'))}")
    if _has_value(node.get("part_of_speech")):
        parts.append(f"{prefix}.part_of_speech={_norm(node.get('part_of_speech'))}")
    if _has_value(node.get("grammatical_role")):
        parts.append(f"{prefix}.grammatical_role={_norm(node.get('grammatical_role'))}")
    if _has_value(node.get("tense")):
        parts.append(f"{prefix}.tense={_norm(node.get('tense'))}")
    if _has_value(node.get("aspect")):
        parts.append(f"{prefix}.aspect={_norm(node.get('aspect'))}")
    if _has_value(node.get("mood")):
        parts.append(f"{prefix}.mood={_norm(node.get('mood'))}")
    if _has_value(node.get("voice")):
        parts.append(f"{prefix}.voice={_norm(node.get('voice'))}")
    if _has_value(node.get("finiteness")):
        parts.append(f"{prefix}.finiteness={_norm(node.get('finiteness'))}")
    if _has_value(node.get("tam_construction")):
        parts.append(f"{prefix}.tam_construction={_norm(node.get('tam_construction'))}")
    grammar_classes = _classes_text(node.get("grammar_classes"))
    if grammar_classes != "none":
        parts.append(f"{prefix}.grammar_classes={grammar_classes}")
    if _has_value(node.get("dep_label")):
        parts.append(f"{prefix}.dep_label={_norm(node.get('dep_label'))}")
    span_text = _span_text(node.get("source_span"))
    if span_text != "null":
        parts.append(f"{prefix}.source_span={span_text}")
    return parts


def _children_summary(node: dict[str, Any]) -> list[str]:
    children = node.get("linguistic_elements")
    if not isinstance(children, list):
        return ["tree.child_count=0"]
    child_types: list[str] = []
    child_pos: list[str] = []
    child_roles: list[str] = []
    child_contents: list[str] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        child_types.append(str(child.get("type") or "").strip().lower() or "null")
        child_pos.append(str(child.get("part_of_speech") or "").strip().lower() or "null")
        child_roles.append(str(child.get("grammatical_role") or "").strip().lower() or "null")
        child_content = str(child.get("content") or "").strip()
        if child_content:
            child_contents.append(child_content.replace("|", "/"))
    parts = [f"tree.child_count={len(child_types)}"]
    if child_types:
        parts.append(f"tree.child_types={','.join(sorted(set(child_types)))}")
    if child_pos:
        parts.append(f"tree.child_pos={','.join(sorted(set(child_pos)))}")
    if child_roles:
        parts.append(f"tree.child_roles={','.join(sorted(set(child_roles)))}")
    if child_contents:
        parts.append(f"tree.child_content_preview={' || '.join(child_contents[:4])}")
    return parts


def build_note_context_prompt(
    *,
    node: dict[str, Any],
    parent: dict[str, Any] | None,
    sentence_node: dict[str, Any],
    path_types: list[str],
    depth: int,
    sibling_index: int,
    sibling_count: int,
    template_version: str = "v2_compact_context",
) -> str:
    parts: list[str] = [
        "task: write_linguistic_note",
        f"template_version: {template_version}",
        f"path.types={'>'.join(path_types) if path_types else 'null'}",
        f"tree.depth={depth}",
        f"tree.sibling_index={sibling_index}",
        f"tree.sibling_count={sibling_count}",
    ]
    parts.extend(_field_block("self", node))
    if isinstance(parent, dict):
        parts.extend(_field_block("parent", parent))

    same_sentence_as_self = (
        isinstance(sentence_node, dict)
        and node.get("type") == "Sentence"
        and _norm(node.get("content")) == _norm(sentence_node.get("content"))
    )
    if same_sentence_as_self:
        parts.append("sentence.same_as_self=true")
    else:
        parts.extend(_field_block("sentence", sentence_node))

    parts.extend(_children_summary(node))
    return " | ".join(parts)
