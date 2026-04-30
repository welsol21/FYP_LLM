"""Build a clean sentence-note seed pack from v35_fixed_clean.csv.

This script converts the external CSV review artifact into sentence-level
book-note rows that can be reused in the sentence-only fast-track pipeline.

The output format matches the existing curated book-note row builders:

- id
- context
- source
- target
- template_projection

The script is intentionally strict. It prefers precision over recall and
drops rows that are long, overly editorial, or weakly tied to a transferable
sentence-level grammar note.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_INPUT = "/home/vlad/Downloads/v35_fixed_clean.csv"
DEFAULT_OUTPUT_JSONL = "data/processed_sentence_seed/v35_sentence_seed_v1.jsonl"
DEFAULT_REPORT_JSON = "data/processed_sentence_seed/v35_sentence_seed_v1.report.json"

ALLOWED_SOURCES = {
    "collins_cobuild_english_grammar_2011",
    "cobuild_english_grammar_2017",
    "farlex_complete_english_grammar_rules_2016",
    "leech_glossary_2006",
}

ALLOWED_TOPICS = {
    "conditional_sentences",
    "perfect",
    "passive_voice",
    "progressive",
    "relative_clauses",
    "question_tags",
    "existential",
    "that_clause",
    "reported_speech",
    "interrogative",
    "adverbial_clause",
}

_SPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_BOOK_META_RE = re.compile(r"\b(unit|chapter|section|paragraph|exercise)\b", re.I)
_CROSS_REF_RE = re.compile(r"\bsee\b|\bshown above\b|\bexplained above\b", re.I)
_ENUM_RE = re.compile(r"\bR\d+\b")
_EXAMPLE_HEAVY_RE = re.compile(r"\bfor example\b", re.I)


def _norm(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "").strip())


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:16]


def _template_projection(note_text: str) -> dict[str, Any]:
    return {
        "template_projection_version": "book_note_template_v4",
        "original_note_text": note_text,
        "template_kind": "passthrough",
        "note_template": note_text,
        "slot_values": {},
        "rendered_note": note_text,
        "template_risk_flags": [],
        "templated": False,
    }


def _split_sentences(text: str) -> list[str]:
    src = _norm(text)
    if not src:
        return []
    return [_norm(part) for part in _SENTENCE_SPLIT_RE.split(src) if _norm(part)]


def _trim_target(topic: str, target: str) -> str:
    sentences = _split_sentences(target)
    if not sentences:
        return ""

    # Topics that often need a short second sentence to stay intelligible.
    allow_two = {
        "relative_clauses",
        "question_tags",
        "existential",
        "reported_speech",
        "that_clause",
    }
    kept = sentences[:2] if topic in allow_two else sentences[:1]
    out = _norm(" ".join(kept))
    return out


def _reject_reason(row: dict[str, str]) -> str | None:
    source_id = _norm(row.get("source_id"))
    topic_key = _norm(row.get("topic_key"))
    node_type = _norm(row.get("node_type"))
    sentence_text = _norm(row.get("sentence_text"))
    target = _norm(row.get("target"))

    if node_type != "Sentence":
        return "non_sentence_row"
    if source_id not in ALLOWED_SOURCES:
        return "source_not_allowed"
    if topic_key not in ALLOWED_TOPICS:
        return "topic_not_allowed"
    if not sentence_text or not target:
        return "missing_text"
    if _BOOK_META_RE.search(target):
        return "book_meta"
    if _CROSS_REF_RE.search(target):
        return "cross_ref"
    if _ENUM_RE.search(target):
        return "rule_enum"
    if len(target.split()) > 45:
        return "target_too_long"
    if _EXAMPLE_HEAVY_RE.search(target) and len(target.split()) > 28:
        return "example_heavy"
    return None


def _build_row(row: dict[str, str], *, csv_path: str) -> dict[str, Any] | None:
    source_id = _norm(row.get("source_id"))
    topic_key = _norm(row.get("topic_key"))
    sentence_text = _norm(row.get("sentence_text"))
    entry_head = _norm(row.get("entry_head"))
    target = _trim_target(topic_key, _norm(row.get("target")))
    if not target:
        return None
    if len(target.split()) < 8:
        return None

    source_record_id = _stable_id(source_id, topic_key, sentence_text, target)
    return {
        "id": source_record_id,
        "context": {
            "node_type": "Sentence",
            "content": sentence_text,
            "sentence_text": sentence_text,
            "part_of_speech": "sentence",
            "grammatical_role": "clause",
        },
        "source": {
            "document_id": source_id,
            "source_path": csv_path,
            "topic": topic_key,
            "origin_unit": entry_head,
            "source_record_id": source_record_id,
        },
        "target": {
            "audience_level": "intermediate",
            "note_text": target,
        },
        "template_projection": _template_projection(target),
    }


def _iter_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_seed_rows(input_csv: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    input_path = Path(input_csv)
    stats = Counter()
    reject_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()

    rows: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for raw in _iter_csv(input_path):
        stats["rows_seen"] += 1
        reason = _reject_reason(raw)
        if reason is not None:
            reject_counts[reason] += 1
            continue
        built = _build_row(raw, csv_path=str(input_path.resolve()))
        if built is None:
            reject_counts["failed_build"] += 1
            continue

        sentence_text = _norm(built["context"]["sentence_text"]).lower()
        note_text = _norm(built["target"]["note_text"]).lower()
        pair_key = (sentence_text, note_text)
        if pair_key in seen_pairs:
            reject_counts["duplicate_pair"] += 1
            continue
        seen_pairs.add(pair_key)

        rows.append(built)
        source_counts[_norm(built["source"]["document_id"])] += 1
        topic_counts[_norm(built["source"]["topic"])] += 1
        stats["rows_kept"] += 1

    report = {
        "builder": "build_sentence_note_seed_from_v35_csv.py",
        "input_csv": str(input_path.resolve()),
        "rows_seen": stats["rows_seen"],
        "rows_kept": stats["rows_kept"],
        "rejected": stats["rows_seen"] - stats["rows_kept"],
        "reject_counts": dict(reject_counts),
        "source_counts": dict(source_counts),
        "topic_counts": dict(topic_counts),
        "allowed_sources": sorted(ALLOWED_SOURCES),
        "allowed_topics": sorted(ALLOWED_TOPICS),
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a clean sentence-note seed pack from v35_fixed_clean.csv")
    parser.add_argument("--input-csv", default=DEFAULT_INPUT)
    parser.add_argument("--output-jsonl", default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--report-json", default=DEFAULT_REPORT_JSON)
    args = parser.parse_args()

    rows, report = build_seed_rows(args.input_csv)
    output_jsonl = Path(args.output_jsonl)
    report_json = Path(args.report_json)
    _write_jsonl(output_jsonl, rows)
    _write_json(report_json, report)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows_kept": len(rows),
                "output_jsonl": str(output_jsonl.resolve()),
                "report_json": str(report_json.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
