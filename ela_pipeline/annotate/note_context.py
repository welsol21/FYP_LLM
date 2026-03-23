"""Deterministic flat-context serialization for note generation."""

from __future__ import annotations

from typing import Any


EXCLUDED_FROM_NOTE_CONTEXT = {
    "active_translation_provider",
    "content",
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
        return [
            f"{prefix}.type=null",
            f"{prefix}.part_of_speech=null",
            f"{prefix}.grammatical_role=null",
            f"{prefix}.cefr_level=null",
            f"{prefix}.tense=null",
            f"{prefix}.aspect=null",
            f"{prefix}.mood=null",
            f"{prefix}.voice=null",
            f"{prefix}.finiteness=null",
            f"{prefix}.tam_construction=null",
            f"{prefix}.grammar_classes=none",
            f"{prefix}.dep_label=null",
            f"{prefix}.head_id=null",
            f"{prefix}.source_span=null",
        ]
    return [
        f"{prefix}.type={_norm(node.get('type'))}",
        f"{prefix}.part_of_speech={_norm(node.get('part_of_speech'))}",
        f"{prefix}.grammatical_role={_norm(node.get('grammatical_role'))}",
        f"{prefix}.cefr_level={_norm(node.get('cefr_level'))}",
        f"{prefix}.tense={_norm(node.get('tense'))}",
        f"{prefix}.aspect={_norm(node.get('aspect'))}",
        f"{prefix}.mood={_norm(node.get('mood'))}",
        f"{prefix}.voice={_norm(node.get('voice'))}",
        f"{prefix}.finiteness={_norm(node.get('finiteness'))}",
        f"{prefix}.tam_construction={_norm(node.get('tam_construction'))}",
        f"{prefix}.grammar_classes={_classes_text(node.get('grammar_classes'))}",
        f"{prefix}.dep_label={_norm(node.get('dep_label'))}",
        f"{prefix}.head_id={_norm(node.get('head_id'))}",
        f"{prefix}.source_span={_span_text(node.get('source_span'))}",
    ]


def _children_summary(node: dict[str, Any]) -> list[str]:
    children = node.get("linguistic_elements")
    if not isinstance(children, list):
        return [
            "tree.child_count=0",
            "tree.child_types=none",
            "tree.child_pos=none",
            "tree.child_roles=none",
        ]
    child_types: list[str] = []
    child_pos: list[str] = []
    child_roles: list[str] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        child_types.append(str(child.get("type") or "").strip().lower() or "null")
        child_pos.append(str(child.get("part_of_speech") or "").strip().lower() or "null")
        child_roles.append(str(child.get("grammatical_role") or "").strip().lower() or "null")
    return [
        f"tree.child_count={len(child_types)}",
        f"tree.child_types={','.join(sorted(set(child_types))) if child_types else 'none'}",
        f"tree.child_pos={','.join(sorted(set(child_pos))) if child_pos else 'none'}",
        f"tree.child_roles={','.join(sorted(set(child_roles))) if child_roles else 'none'}",
    ]


def build_note_context_prompt(
    *,
    node: dict[str, Any],
    parent: dict[str, Any] | None,
    sentence_node: dict[str, Any],
    path_types: list[str],
    depth: int,
    sibling_index: int,
    sibling_count: int,
    template_version: str = "v2_flat_context",
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
    parts.extend(_field_block("parent", parent))
    parts.extend(_field_block("sentence", sentence_node))
    parts.extend(_children_summary(node))
    return " | ".join(parts)
