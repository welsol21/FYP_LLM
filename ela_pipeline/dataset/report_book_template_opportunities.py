"""Report high-value family/template gaps in the projected book corpus.

This is a planning utility for expanding placeholder-template coverage.
It focuses on families that already have book-derived note candidates but
still do not have slot-safe placeholder templates.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _family_bucket() -> dict[str, Any]:
    return {
        "row_count": 0,
        "slot_row_count": 0,
        "topics": Counter(),
        "books": Counter(),
        "note_examples": [],
        "sentence_examples": [],
        "phrase_examples": [],
    }


def _add_example(items: list[str], value: str, *, limit: int = 5) -> None:
    value = _norm(value)
    if not value or value in items:
        return
    if len(items) < limit:
        items.append(value)


def _update_bucket(
    bucket: dict[str, Any],
    *,
    topic: str,
    source_book: str,
    note_text: str,
    sentence_text: str,
    phrase_text: str = "",
    slot_templated: bool = False,
) -> None:
    bucket["row_count"] += 1
    if slot_templated:
        bucket["slot_row_count"] += 1
    if topic:
        bucket["topics"][topic] += 1
    if source_book:
        bucket["books"][source_book] += 1
    _add_example(bucket["note_examples"], note_text)
    _add_example(bucket["sentence_examples"], sentence_text)
    if phrase_text:
        _add_example(bucket["phrase_examples"], phrase_text)


def _serialize_bucket(family_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "family_id": family_id,
        "row_count": int(payload["row_count"]),
        "slot_row_count": int(payload["slot_row_count"]),
        "topics_top": payload["topics"].most_common(8),
        "books_top": payload["books"].most_common(8),
        "note_examples": list(payload["note_examples"]),
        "sentence_examples": list(payload["sentence_examples"]),
        "phrase_examples": list(payload["phrase_examples"]),
    }


def build_report(input_path: str, *, top_n: int = 25) -> dict[str, Any]:
    sentence_totals: Counter[str] = Counter()
    phrase_totals: Counter[str] = Counter()
    sentence_with_book: dict[str, dict[str, Any]] = defaultdict(_family_bucket)
    phrase_with_book: dict[str, dict[str, Any]] = defaultdict(_family_bucket)
    uncovered_sentence_topics: Counter[str] = Counter()
    uncovered_phrase_topics: Counter[str] = Counter()

    for row in _iter_jsonl(input_path):
        sentence_text = _norm(row.get("sentence_text"))
        sent_alignment = row.get("sentence_family_alignment") or {}
        sent_family = _norm(sent_alignment.get("exact_family_id"))
        if sent_family:
            sentence_totals[sent_family] += 1
        for candidate in row.get("sentence_note_candidates") or []:
            source_book = _norm(candidate.get("source_book"))
            if not source_book or source_book == "internal_pedagogical_grammar":
                continue
            topic = _norm(candidate.get("topic"))
            note_text = _norm(candidate.get("slot_template_text") or candidate.get("note_text"))
            slot_templated = bool(candidate.get("slot_templated"))
            if sent_family:
                _update_bucket(
                    sentence_with_book[sent_family],
                    topic=topic,
                    source_book=source_book,
                    note_text=note_text,
                    sentence_text=sentence_text,
                    slot_templated=slot_templated,
                )
                if not slot_templated and topic:
                    uncovered_sentence_topics[topic] += 1

        for phrase in row.get("phrase_entries") or []:
            phrase_family = _norm(phrase.get("exact_family_id"))
            phrase_text = _norm(phrase.get("content"))
            if phrase_family:
                phrase_totals[phrase_family] += 1
            for candidate in phrase.get("note_candidates") or []:
                source_book = _norm(candidate.get("source_book"))
                if not source_book or source_book == "internal_pedagogical_grammar":
                    continue
                topic = _norm(candidate.get("topic"))
                note_text = _norm(candidate.get("slot_template_text") or candidate.get("note_text"))
                slot_templated = bool(candidate.get("slot_templated"))
                if phrase_family:
                    _update_bucket(
                        phrase_with_book[phrase_family],
                        topic=topic,
                        source_book=source_book,
                        note_text=note_text,
                        sentence_text=sentence_text,
                        phrase_text=phrase_text,
                        slot_templated=slot_templated,
                    )
                    if not slot_templated and topic:
                        uncovered_phrase_topics[topic] += 1

    uncovered_sentence = [
        _serialize_bucket(family_id, payload)
        for family_id, payload in sentence_with_book.items()
        if payload["row_count"] > 0 and payload["slot_row_count"] == 0
    ]
    uncovered_sentence.sort(
        key=lambda item: (
            -int(item["row_count"]),
            -len(item["note_examples"]),
            item["family_id"],
        )
    )

    uncovered_phrase = [
        _serialize_bucket(family_id, payload)
        for family_id, payload in phrase_with_book.items()
        if payload["row_count"] > 0 and payload["slot_row_count"] == 0
    ]
    uncovered_phrase.sort(
        key=lambda item: (
            -int(item["row_count"]),
            -len(item["note_examples"]),
            item["family_id"],
        )
    )

    covered_sentence = sum(1 for payload in sentence_with_book.values() if payload["slot_row_count"] > 0)
    covered_phrase = sum(1 for payload in phrase_with_book.values() if payload["slot_row_count"] > 0)

    return {
        "report_version": "book_template_opportunities_v1",
        "input_path": str(Path(input_path).resolve()),
        "sentence_summary": {
            "exact_families_total_in_projection": len(sentence_totals),
            "exact_families_with_book_notes": len(sentence_with_book),
            "exact_families_with_book_slot_templates": covered_sentence,
            "exact_families_with_book_notes_but_no_slot_templates": len(uncovered_sentence),
        },
        "phrase_summary": {
            "exact_families_total_in_projection": len(phrase_totals),
            "exact_families_with_book_notes": len(phrase_with_book),
            "exact_families_with_book_slot_templates": covered_phrase,
            "exact_families_with_book_notes_but_no_slot_templates": len(uncovered_phrase),
        },
        "top_uncovered_sentence_families": uncovered_sentence[:top_n],
        "top_uncovered_phrase_families": uncovered_phrase[:top_n],
        "top_uncovered_sentence_topics": uncovered_sentence_topics.most_common(top_n),
        "top_uncovered_phrase_topics": uncovered_phrase_topics.most_common(top_n),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report high-value template coverage gaps in the projected book corpus.")
    parser.add_argument("--input", required=True, help="Projected corpus JSONL, e.g. projection_v16.")
    parser.add_argument("--output", required=True, help="JSON report path.")
    parser.add_argument("--top-n", type=int, default=25)
    args = parser.parse_args()

    report = build_report(args.input, top_n=max(1, int(args.top_n)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(output.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
