"""Post-process aligned book notes into template-slot notes.

This keeps the original book note intact and adds a safer transferable layer:

- note_template
- slot_values
- rendered_note
- template_risk_flags
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.contract_template_builder import (
    allowed_slots_for_template_text,
    canonical_template_text_for_template_id,
)
from ela_pipeline.dataset.template_topic_mapping import topic_to_template_id
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


PREPOSITIONS = {
    "aboard",
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "amid",
    "among",
    "around",
    "as",
    "at",
    "before",
    "behind",
    "below",
    "beneath",
    "beside",
    "besides",
    "between",
    "beyond",
    "by",
    "concerning",
    "despite",
    "down",
    "during",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "near",
    "of",
    "off",
    "on",
    "onto",
    "outside",
    "over",
    "past",
    "through",
    "throughout",
    "to",
    "toward",
    "towards",
    "under",
    "until",
    "up",
    "upon",
    "with",
    "within",
    "without",
}
RELATIVE_MARKERS = {"who", "which", "that", "whom", "whose", "where", "when", "why"}
UNSAFE_HEAD_WORDS = RELATIVE_MARKERS | {
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
}
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?")
QUESTION_TAG_RE = re.compile(r",\s*([A-Za-z]+(?:n't)?)\s+([A-Za-z]+)\?\s*$", re.IGNORECASE)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _walk_nodes(node: dict[str, Any], parent: dict[str, Any] | None = None):
    yield node, parent
    for child in node.get("linguistic_elements") or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child, node)


def _descendant_words(node: dict[str, Any]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for child, _parent in _walk_nodes(node):
        if child.get("type") == "Word":
            words.append(child)
    words.sort(key=lambda item: int((item.get("source_span") or {}).get("start", 0)))
    return words


def _locate_target_node(sentence_text: str, context: dict[str, Any], nlp: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    docs = build_skeleton(sentence_text, nlp)
    if not docs:
        return None, None
    sentence_node = next(iter(docs.values()))
    target_content = _norm(context.get("content"))
    target_pos = _norm_lower(context.get("part_of_speech"))
    target_role = _norm_lower(context.get("grammatical_role"))

    exact: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    loose: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    content_only: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for node, parent in _walk_nodes(sentence_node):
        if node.get("type") != context.get("node_type"):
            continue
        node_content = _norm(node.get("content"))
        node_pos = _norm_lower(node.get("part_of_speech"))
        node_role = _norm_lower(node.get("grammatical_role"))
        if node_content == target_content:
            content_only.append((node, parent))
            if node_pos == target_pos:
                loose.append((node, parent))
                if node_role == target_role:
                    exact.append((node, parent))
    if exact:
        return exact[0]
    if loose:
        return loose[0]
    if content_only:
        return content_only[0]
    return None, sentence_node


def _previous_head_noun(sentence_node: dict[str, Any], target_node: dict[str, Any]) -> str | None:
    target_start = int((target_node.get("source_span") or {}).get("start", -1))
    if target_start < 0:
        return None
    relative_starts = [
        int((word.get("source_span") or {}).get("start", -1))
        for word in _descendant_words(target_node)
        if _norm_lower(word.get("content")) in RELATIVE_MARKERS
    ]
    anchor_start = min((start for start in relative_starts if start >= 0), default=target_start)
    candidates: list[dict[str, Any]] = []
    for node, _parent in _walk_nodes(sentence_node):
        if node.get("type") != "Word":
            continue
        node_start = int((node.get("source_span") or {}).get("start", -1))
        if node_start >= 0 and node_start < anchor_start:
            pos = _norm_lower(node.get("part_of_speech"))
            content = _norm_lower(node.get("content"))
            if pos in {"noun", "proper noun"} and content not in UNSAFE_HEAD_WORDS:
                candidates.append(node)
    if not candidates:
        return None
    candidates.sort(key=lambda item: int((item.get("source_span") or {}).get("start", 0)))
    return _norm(candidates[-1].get("content")) or None


def _relative_shape(target_node: dict[str, Any]) -> dict[str, bool]:
    words = _descendant_words(target_node)
    items = [
        (_norm_lower(word.get("content")), _norm_lower(word.get("part_of_speech")))
        for word in words
        if _norm(word.get("content"))
    ]
    marker_positions = [idx for idx, (text, _pos) in enumerate(items) if text in RELATIVE_MARKERS]
    marker_idx = marker_positions[0] if marker_positions else -1
    has_marker = marker_idx >= 0
    starts_with_marker = marker_idx == 0
    starts_with_preposition_marker = (
        marker_idx == 1 and items and items[0][1] == "preposition"
    )
    embedded_marker = has_marker and not starts_with_marker and not starts_with_preposition_marker
    return {
        "has_marker": has_marker,
        "starts_with_marker": starts_with_marker,
        "starts_with_preposition_marker": starts_with_preposition_marker,
        "embedded_marker": embedded_marker,
    }


def _safe_head_noun(slots: dict[str, Any]) -> bool:
    head = _norm_lower(slots.get("HEAD_NOUN"))
    return bool(head) and head not in UNSAFE_HEAD_WORDS


def _slot_values(sentence_node: dict[str, Any], target_node: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    phrase_text = _norm(context.get("content"))
    words = _descendant_words(target_node)
    word_texts = [_norm(word.get("content")) for word in words if _norm(word.get("content"))]
    word_pos = [_norm_lower(word.get("part_of_speech")) for word in words if _norm(word.get("content"))]
    preposition = None
    relative_marker = None
    for word, pos in zip(word_texts, word_pos):
        token = word.lower()
        if preposition is None and pos == "preposition" and token in PREPOSITIONS:
            preposition = word
        if relative_marker is None and token in RELATIVE_MARKERS:
            relative_marker = word
    object_np = None
    if preposition:
        parts = phrase_text.split()
        if parts and parts[0].lower() == preposition.lower() and len(parts) > 1:
            object_np = " ".join(parts[1:])
        else:
            idx = next((i for i, word in enumerate(word_texts) if word.lower() == preposition.lower()), -1)
            if idx >= 0 and idx + 1 < len(word_texts):
                object_np = " ".join(word_texts[idx + 1 :])

    return {
        "TARGET_PHRASE": phrase_text or None,
        "PREPOSITION": preposition,
        "OBJECT_NP": object_np,
        "RELATIVE_MARKER": relative_marker,
        "HEAD_NOUN": _previous_head_noun(sentence_node, target_node),
        "RELATIVE_SHAPE": _relative_shape(target_node),
        "PHRASE_POS": _norm(context.get("part_of_speech")) or None,
        "GRAMMATICAL_ROLE": _norm(context.get("grammatical_role")) or None,
    }


def _render(template: str, slots: dict[str, Any]) -> str:
    rendered = template
    for key, value in slots.items():
        rendered = rendered.replace("{{" + key + "}}", _norm(value))
    rendered = re.sub(r"\s+", " ", rendered).strip()
    rendered = rendered.replace(" .", ".")
    rendered = rendered.replace(" ,", ",")
    return rendered


def _extract_question_tag_slots(sentence_text: str) -> dict[str, str]:
    match = QUESTION_TAG_RE.search(_norm(sentence_text))
    if not match:
        return {}
    return {
        "TAG_AUXILIARY": _norm(match.group(1)),
        "TAG_PRONOUN": _norm(match.group(2)),
    }


def _topic_template_projection(
    *,
    node_type: str,
    topic: str,
    sentence_text: str,
    phrase_context: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any], list[str], bool]:
    flags: list[str] = []
    level = "Sentence" if _norm_lower(node_type) == "sentence" else "Phrase"
    template_id = topic_to_template_id(level, topic)
    if not template_id:
        return "passthrough", "", {}, flags, False

    node_stub = {
        "type": "Sentence" if level == "Sentence" else "Phrase",
        "part_of_speech": (phrase_context or {}).get("part_of_speech"),
        "grammatical_role": (phrase_context or {}).get("grammatical_role"),
        "tam_construction": None,
    }
    template_text = canonical_template_text_for_template_id(template_id, node=node_stub)
    if not template_text:
        return "passthrough", "", {}, flags, False

    slot_values: dict[str, Any] = {}
    if level == "Sentence":
        slot_values.update(_extract_question_tag_slots(sentence_text))
    else:
        slot_values.update(
            {
                "CONTENT": _norm((phrase_context or {}).get("content")) or None,
                "PART_OF_SPEECH": _norm((phrase_context or {}).get("part_of_speech")) or None,
                "GRAMMATICAL_ROLE": _norm((phrase_context or {}).get("grammatical_role")) or None,
            }
        )

    required_slots = allowed_slots_for_template_text(template_text)
    if any(not _norm(slot_values.get(slot)) for slot in required_slots):
        flags.append("unresolved_template_slots")
        rendered = template_text
    else:
        rendered = _render(template_text, slot_values)
    return f"topic_template::{template_id.lower()}", template_text, slot_values, flags, True


# Grammatical category terms that authors use in notes, mapped to contract slot names.
# Terms within each list are tried longest-first so "head noun" matches before "noun",
# "relative pronoun" matches before "pronoun", "object of the preposition" before "object".
_SLOT_CATEGORY_TERMS: dict[str, list[str]] = {
    "HEAD_NOUN": ["head noun", "antecedent noun", "antecedent", "noun"],
    "PREPOSITION": ["preposition"],
    "OBJECT_NP": [
        "object of the preposition",
        "object of a preposition",
        "noun phrase",
        "object np",
        "object",
    ],
    "RELATIVE_MARKER": [
        "relative pronoun",
        "relative adverb",
        "relative element",
        "relative word",
        "relative marker",
        "wh-word",
        "wh-pronoun",
    ],
    "TAG_AUXILIARY": ["tag auxiliary", "auxiliary verb", "auxiliary"],
    "TAG_PRONOUN": ["tag pronoun", "pronoun"],
}


def _parametrize_note(note_text: str, slot_names: list[str]) -> tuple[str, list[str]]:
    """Replace grammatical category terms in note_text with {{SLOT}} markers.

    Searches for the terms authors actually use ("noun", "preposition",
    "relative pronoun", etc.) rather than the contract field values, so that
    conceptual notes like "The noun modified by the relative pronoun …" become
    "The {{HEAD_NOUN}} modified by the {{RELATIVE_MARKER}} …".
    """
    result = note_text
    replaced: list[str] = []
    for slot_name in slot_names:
        terms = _SLOT_CATEGORY_TERMS.get(slot_name, [])
        marker = "{{" + slot_name + "}}"
        for term in terms:
            pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
            new_result, n = pattern.subn(marker, result, count=1)
            if n:
                result = new_result
                replaced.append(slot_name)
                break
    return result, replaced


def _template_phrase_note(topic: str, note_text: str, slots: dict[str, Any]) -> tuple[str, str, list[str]]:
    topic_lower = _norm_lower(topic)
    flags: list[str] = []
    shape = slots.get("RELATIVE_SHAPE") or {}
    safe_head = _safe_head_noun(slots)

    if "prepositional phrase" in topic_lower:
        template, replaced = _parametrize_note(note_text, ["OBJECT_NP", "PREPOSITION"])
        if replaced:
            for slot in ["PREPOSITION", "OBJECT_NP"]:
                if "{{" + slot + "}}" in template and not slots.get(slot):
                    flags.append(f"missing_{slot.lower()}_slot")
            return "prepositional_phrase_parametrized", template, flags
        flags.append("no_phrase_template_rule")
        return "phrase_passthrough", note_text, flags

    if "non-restrictive relative clause" in topic_lower or "non restrictive relative clause" in topic_lower:
        template, replaced = _parametrize_note(note_text, ["HEAD_NOUN", "RELATIVE_MARKER"])
        if replaced:
            if not safe_head and "HEAD_NOUN" in replaced:
                flags.append("unsafe_head_noun_slot")
            return "non_restrictive_relative_clause_parametrized", template, flags
        if shape.get("embedded_marker"):
            flags.append("embedded_relative_clause_scope")
        elif not (shape.get("starts_with_marker") or shape.get("starts_with_preposition_marker")):
            flags.append("relative_clause_pattern_fallback")
        flags.append("no_phrase_template_rule")
        return "phrase_passthrough", note_text, flags

    if "restrictive relative clause" in topic_lower or "relative clause" in topic_lower:
        template, replaced = _parametrize_note(note_text, ["HEAD_NOUN", "RELATIVE_MARKER", "PREPOSITION"])
        if replaced:
            if not safe_head and "HEAD_NOUN" in replaced:
                flags.append("unsafe_head_noun_slot")
            return "relative_clause_parametrized", template, flags
        if shape.get("embedded_marker"):
            flags.append("embedded_relative_clause_scope")
        elif not (shape.get("starts_with_marker") or shape.get("starts_with_preposition_marker")):
            flags.append("relative_clause_pattern_fallback")
        flags.append("no_phrase_template_rule")
        return "phrase_passthrough", note_text, flags

    flags.append("no_phrase_template_rule")
    return "phrase_passthrough", note_text, flags


def _lexical_reference_flags(note_text: str) -> list[str]:
    note_lower = _norm_lower(note_text)
    flags: list[str] = []
    if "'" in note_text:
        flags.append("quoted_lexical_reference")
    if any(term in note_lower for term in ("subject pronoun", "auxiliary verb", "object of the verb", "particular noun", "preposition and its object")):
        flags.append("member_reference_in_note")
    return flags


def _template_row(row: dict[str, Any], nlp: Any) -> tuple[dict[str, Any], list[str]]:
    out = copy.deepcopy(row)
    context = out.get("context") or {}
    note_text = _norm((out.get("target") or {}).get("note_text"))
    topic = _norm((out.get("source") or {}).get("topic"))
    risk_flags = _lexical_reference_flags(note_text)

    projection: dict[str, Any] = {
        "template_projection_version": "book_note_template_v4",
        "original_note_text": note_text,
        "template_kind": "passthrough",
        "note_template": note_text,
        "slot_values": {},
        "rendered_note": note_text,
        "template_risk_flags": risk_flags[:],
        "templated": False,
    }

    node_type = _norm(context.get("node_type")).lower()

    if node_type != "phrase":
        sentence_text = _norm(context.get("sentence_text") or context.get("content"))
        template_kind, note_template, slot_values, template_flags, templated = _topic_template_projection(
            node_type=node_type,
            topic=topic,
            sentence_text=sentence_text,
        )
        if templated:
            projection.update(
                {
                    "template_kind": template_kind,
                    "note_template": note_template,
                    "slot_values": slot_values,
                    "rendered_note": _render(note_template, slot_values) if note_template else note_text,
                    "template_risk_flags": sorted(set(risk_flags + template_flags)),
                    "templated": True,
                }
            )
        out["template_projection"] = projection
        return out, projection["template_risk_flags"]

    sentence_text = _norm(context.get("sentence_text"))
    if not sentence_text:
        projection["template_risk_flags"].append("missing_sentence_text")
        out["template_projection"] = projection
        return out, projection["template_risk_flags"]

    target_node, sentence_node = _locate_target_node(sentence_text, context, nlp)
    if target_node is None or sentence_node is None:
        projection["template_risk_flags"].append("target_node_not_found")
        out["template_projection"] = projection
        return out, projection["template_risk_flags"]

    slots = _slot_values(sentence_node, target_node, context)
    template_kind, note_template, template_flags = _template_phrase_note(topic, note_text, slots)
    projection.update(
        {
            "template_kind": template_kind,
            "note_template": note_template,
            "slot_values": slots,
            "rendered_note": _render(note_template, slots),
            "template_risk_flags": sorted(set(risk_flags + template_flags)),
            "templated": template_kind != "phrase_passthrough",
        }
    )
    out["template_projection"] = projection
    return out, projection["template_risk_flags"]


def build_template_projection(input_path: str, *, spacy_model: str = "en_core_web_sm") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    rows: list[dict[str, Any]] = []
    template_kind_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    node_type_counts: Counter[str] = Counter()

    for row in _iter_jsonl(input_path):
        templated_row, flags = _template_row(row, nlp)
        projection = templated_row.get("template_projection") or {}
        rows.append(templated_row)
        template_kind_counts[str(projection.get("template_kind") or "unknown")] += 1
        node_type_counts[_norm((templated_row.get("context") or {}).get("node_type")) or "unknown"] += 1
        for flag in flags:
            flag_counts[flag] += 1

    report = {
        "template_projection_version": "book_note_template_v4",
        "input_path": str(Path(input_path).resolve()),
        "rows_total": len(rows),
        "template_kind_counts": dict(template_kind_counts),
        "node_type_counts": dict(node_type_counts),
        "risk_flag_counts": dict(flag_counts),
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build template-slot projection for aligned book note rows.")
    parser.add_argument("--input", required=True, help="Aligned v2 note rows JSONL")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    rows, report = build_template_projection(args.input, spacy_model=args.spacy_model)
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps({"status": "ok", "rows": len(rows), "output_jsonl": str(Path(args.output_jsonl).resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
