"""Normalize constituent references inside projected corpus note candidates.

This layer does not replace the corpus lineage. Instead it produces a new
version where note candidates gain a slot-aware projection:

- slot_template_text
- slot_values
- slot_rendered_note
- slot_template_kind
- slot_risk_flags
- slot_templated

For phrase notes with obviously lexicalized borrowed members from a book
example, the visible note text is repaired to the slot-rendered note while
preserving the old text in `lexicalized_note_text`.
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


PREPOSITIONS = {
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "around",
    "as",
    "at",
    "before",
    "behind",
    "below",
    "beneath",
    "beside",
    "between",
    "beyond",
    "by",
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
    "out",
    "outside",
    "over",
    "past",
    "through",
    "to",
    "toward",
    "under",
    "up",
    "upon",
    "with",
    "within",
    "without",
}
RELATIVE_MARKERS = {"who", "which", "that", "whom", "whose", "where", "when", "why"}
TAG_PRONOUNS = {"i", "you", "he", "she", "it", "we", "they", "there"}
WORD_RE = re.compile(r"[A-Za-z]+(?:n't)?")
QUOTED_RE = re.compile(r'"([^"]+)"')
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


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render(template: str, slots: dict[str, Any]) -> str:
    rendered = template
    for key, value in slots.items():
        rendered = rendered.replace("{{" + key + "}}", _norm(value))
    rendered = re.sub(r"\s+", " ", rendered).strip()
    rendered = rendered.replace(" .", ".")
    rendered = rendered.replace(" ,", ",")
    return rendered


def _has_all_required_slots(template_text: str, slot_values: dict[str, Any]) -> bool:
    required = allowed_slots_for_template_text(template_text)
    return all(_norm(slot_values.get(slot)) for slot in required)


def _extract_preposition_object(phrase_text: str) -> tuple[str | None, str | None]:
    text = _norm(phrase_text)
    if not text:
        return None, None
    parts = text.split()
    if not parts:
        return None, None
    head = parts[0]
    if head.lower() not in PREPOSITIONS:
        return None, None
    obj = " ".join(parts[1:]).strip() or None
    return head, obj


def _extract_relative_marker(phrase_text: str) -> str | None:
    for token in WORD_RE.findall(_norm(phrase_text).lower()):
        if token in RELATIVE_MARKERS:
            return token
    return None


def _quoted_fragments(text: str) -> list[str]:
    return [_norm(item) for item in QUOTED_RE.findall(text or "") if _norm(item)]


def _sentence_has_fragment(sentence_text: str, fragment: str) -> bool:
    return _norm_lower(fragment) in _norm_lower(sentence_text)


def _extract_question_tag_slots(sentence_text: str) -> dict[str, str] | None:
    match = QUESTION_TAG_RE.search(_norm(sentence_text))
    if not match:
        return None
    auxiliary = _norm(match.group(1))
    pronoun = _norm(match.group(2))
    if pronoun.lower() not in TAG_PRONOUNS:
        return None
    return {"TAG_AUXILIARY": auxiliary, "TAG_PRONOUN": pronoun}


def _base_slot_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    note_text = _norm(candidate.get("note_text"))
    return {
        "slot_template_kind": "passthrough",
        "slot_template_text": note_text,
        "slot_values": {},
        "slot_rendered_note": note_text,
        "slot_risk_flags": [],
        "slot_templated": False,
    }


def _normalize_phrase_candidate(
    phrase_entry: dict[str, Any],
    candidate: dict[str, Any],
    counters: Counter[str],
) -> dict[str, Any]:
    out = copy.deepcopy(candidate)
    payload = _base_slot_payload(out)
    phrase_text = _norm(phrase_entry.get("content"))
    note_text = _norm(out.get("note_text"))
    topic = _norm_lower(out.get("topic"))
    template_kind = _norm(out.get("template_kind"))
    quoted = _quoted_fragments(note_text)
    prep, obj = _extract_preposition_object(phrase_text)
    rel = _extract_relative_marker(phrase_text)

    repaired_text = None

    if template_kind in {"prepositional_phrase_structure", "prepositional_phrase_object"} or (
        "prepositional phrase" in topic and quoted
    ):
        payload["slot_template_kind"] = template_kind or "prepositional_phrase_slot"
        if template_kind == "prepositional_phrase_object":
            payload["slot_template_text"] = (
                'Here, "{{OBJECT_NP}}" functions as the object of the preposition "{{PREPOSITION}}".'
            )
        else:
            payload["slot_template_text"] = (
                'This prepositional phrase contains the preposition "{{PREPOSITION}}" and the object "{{OBJECT_NP}}".'
            )
        payload["slot_values"] = {"PREPOSITION": prep, "OBJECT_NP": obj}
        if not prep:
            payload["slot_risk_flags"].append("missing_preposition_slot")
        if not obj:
            payload["slot_risk_flags"].append("missing_object_slot")
        payload["slot_rendered_note"] = _render(payload["slot_template_text"], payload["slot_values"])
        payload["slot_templated"] = True
        if quoted and not all(_sentence_has_fragment(phrase_text, fragment) for fragment in quoted):
            repaired_text = payload["slot_rendered_note"]
            counters["phrase_lexicalized_note_repaired"] += 1
        counters["phrase_slot_templated"] += 1

    elif template_kind == "relative_clause_preposition_marker" and quoted:
        payload["slot_template_kind"] = "relative_clause_preposition_marker_slot"
        payload["slot_template_text"] = (
            'This pattern uses "{{PREPOSITION}}" + "{{RELATIVE_MARKER}}" in the relative clause.'
        )
        payload["slot_values"] = {"PREPOSITION": prep, "RELATIVE_MARKER": rel}
        if not prep:
            payload["slot_risk_flags"].append("missing_preposition_slot")
        if not rel:
            payload["slot_risk_flags"].append("missing_relative_marker_slot")
        payload["slot_rendered_note"] = _render(payload["slot_template_text"], payload["slot_values"])
        payload["slot_templated"] = True
        if not all(_sentence_has_fragment(phrase_text, fragment) for fragment in quoted):
            repaired_text = payload["slot_rendered_note"]
            counters["phrase_lexicalized_note_repaired"] += 1
        counters["phrase_slot_templated"] += 1

    elif template_kind == "relative_clause_modifier" and quoted:
        # Leave the visible note unchanged unless it is clearly lexicalized.
        payload["slot_template_kind"] = "relative_clause_modifier_passthrough"
        payload["slot_template_text"] = note_text
        payload["slot_values"] = {}
        payload["slot_rendered_note"] = note_text
        payload["slot_templated"] = False
        if not all(_sentence_has_fragment(phrase_text, fragment) for fragment in quoted):
            payload["slot_risk_flags"].append("quoted_relative_reference_unresolved")

    else:
        template_id = topic_to_template_id("Phrase", topic)
        template_text = canonical_template_text_for_template_id(
            template_id,
            node={
                "type": "Phrase",
                "part_of_speech": phrase_entry.get("part_of_speech"),
                "grammatical_role": phrase_entry.get("grammatical_role"),
                "tam_construction": None,
            },
        )
        slot_values = {
            "CONTENT": phrase_text or None,
            "PART_OF_SPEECH": _norm(phrase_entry.get("part_of_speech")) or None,
            "GRAMMATICAL_ROLE": _norm(phrase_entry.get("grammatical_role")) or None,
            "PREPOSITION": prep,
            "OBJECT_NP": obj,
            "RELATIVE_MARKER": rel,
        }
        if template_id and template_text and _has_all_required_slots(template_text, slot_values):
            payload["slot_template_kind"] = f"topic_template::{template_id.lower()}"
            payload["slot_template_text"] = template_text
            payload["slot_values"] = slot_values
            payload["slot_rendered_note"] = _render(template_text, slot_values)
            payload["slot_templated"] = True
            counters["phrase_slot_templated"] += 1

    out.update(payload)
    if repaired_text and repaired_text != note_text:
        out["lexicalized_note_text"] = note_text
        out["note_text"] = repaired_text
        if not out.get("original_note_text"):
            out["original_note_text"] = note_text
    return out


def _normalize_sentence_candidate(
    sentence_text: str,
    candidate: dict[str, Any],
    counters: Counter[str],
) -> dict[str, Any]:
    out = copy.deepcopy(candidate)
    payload = _base_slot_payload(out)
    note_text = _norm(out.get("note_text"))
    topic = _norm_lower(out.get("topic"))

    tag_slots = _extract_question_tag_slots(sentence_text)
    if tag_slots and ("question tag" in topic or "question tag" in _norm_lower(note_text)):
        payload["slot_template_kind"] = "question_tag_sentence_slot"
        payload["slot_template_text"] = (
            'Question tags repeat "{{TAG_AUXILIARY}}" and use "{{TAG_PRONOUN}}" as the pronoun subject.'
        )
        payload["slot_values"] = tag_slots
        payload["slot_rendered_note"] = _render(payload["slot_template_text"], payload["slot_values"])
        payload["slot_templated"] = True
        counters["sentence_slot_templated"] += 1
    else:
        template_id = topic_to_template_id("Sentence", topic)
        template_text = canonical_template_text_for_template_id(
            template_id,
            node={"type": "Sentence", "tam_construction": None},
        )
        slot_values = tag_slots or {}
        if template_id and template_text and _has_all_required_slots(template_text, slot_values):
            payload["slot_template_kind"] = f"topic_template::{template_id.lower()}"
            payload["slot_template_text"] = template_text
            payload["slot_values"] = slot_values
            payload["slot_rendered_note"] = _render(template_text, slot_values)
            payload["slot_templated"] = True
            counters["sentence_slot_templated"] += 1

    out.update(payload)
    return out


def build_slot_normalized_corpus(input_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()

    for row in _iter_jsonl(input_path):
        out = copy.deepcopy(row)
        sentence_text = _norm(out.get("sentence_text"))

        sentence_candidates = []
        for candidate in out.get("sentence_note_candidates") or []:
            sentence_candidates.append(_normalize_sentence_candidate(sentence_text, candidate, counters))
        out["sentence_note_candidates"] = sentence_candidates

        phrase_entries = []
        for phrase in out.get("phrase_entries") or []:
            new_phrase = copy.deepcopy(phrase)
            new_candidates = []
            for candidate in phrase.get("note_candidates") or []:
                new_candidates.append(_normalize_phrase_candidate(new_phrase, candidate, counters))
            new_phrase["note_candidates"] = new_candidates
            phrase_entries.append(new_phrase)
        out["phrase_entries"] = phrase_entries

        out["projection_version"] = "book_projection_v16_slot_normalized"
        rows.append(out)

    report = {
        "projection_version": "book_projection_v16_slot_normalized",
        "input_path": str(Path(input_path).resolve()),
        "rows_total": len(rows),
        "slot_templating_counters": dict(counters),
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize constituent references inside projected corpus notes.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows, report = build_slot_normalized_corpus(args.input)
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(rows),
                "output_jsonl": str(Path(args.output_jsonl).resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
