"""Merge a base projected corpus with a newly projected note pack.

The base corpus may already contain previous book-note candidates and fallback
rows. The delta corpus is typically a fresh projection over the natural corpus
for a new book pack. Matching rows are merged by sentence identity; unmatched
base rows are preserved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _row_key(row: dict[str, Any]) -> tuple[str, int, int]:
    span = row.get("source_span") or {}
    return (
        _norm(row.get("sentence_text")),
        int(span.get("start", -1)),
        int(span.get("end", -1)),
    )


def _candidate_key(candidate: dict[str, Any]) -> tuple[str, str]:
    return (
        _norm(candidate.get("source_record_id")),
        _norm(candidate.get("note_text") or candidate.get("rendered_note")),
    )


def _merge_candidates(base: list[dict[str, Any]], delta: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    merged = list(base)
    seen = {_candidate_key(candidate) for candidate in merged}
    added = 0
    for candidate in delta:
        key = _candidate_key(candidate)
        if key in seen:
            continue
        merged.append(candidate)
        seen.add(key)
        added += 1
    return merged, added


def _phrase_key(phrase: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _norm(phrase.get("content")),
        _norm(phrase.get("part_of_speech")).lower(),
        _norm(phrase.get("grammatical_role")).lower(),
    )


def _merge_rows(base_row: dict[str, Any], delta_row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    stats = {
        "sentence_candidates_added": 0,
        "phrase_candidates_added": 0,
        "phrase_rows_matched_by_key": 0,
    }
    merged = dict(base_row)

    sentence_candidates, added = _merge_candidates(
        list(base_row.get("sentence_note_candidates") or []),
        list(delta_row.get("sentence_note_candidates") or []),
    )
    merged["sentence_note_candidates"] = sentence_candidates
    stats["sentence_candidates_added"] += added

    base_phrases = list(base_row.get("phrase_entries") or [])
    delta_phrases = list(delta_row.get("phrase_entries") or [])
    merged_phrases = [dict(phrase) for phrase in base_phrases]

    delta_by_key = {_phrase_key(phrase): phrase for phrase in delta_phrases}
    for idx, base_phrase in enumerate(base_phrases):
        key = _phrase_key(base_phrase)
        delta_phrase = delta_by_key.get(key)
        if delta_phrase is None and idx < len(delta_phrases):
            fallback = delta_phrases[idx]
            if _phrase_key(fallback) == key:
                delta_phrase = fallback
        if delta_phrase is None:
            continue
        merged_candidates, added = _merge_candidates(
            list(base_phrase.get("note_candidates") or []),
            list(delta_phrase.get("note_candidates") or []),
        )
        merged_phrases[idx]["note_candidates"] = merged_candidates
        stats["phrase_candidates_added"] += added
        stats["phrase_rows_matched_by_key"] += 1

    merged["phrase_entries"] = merged_phrases
    return merged, stats


def merge_projected_corpora(base_rows: list[dict[str, Any]], delta_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    delta_by_key = {_row_key(row): row for row in delta_rows}

    merged_rows: list[dict[str, Any]] = []
    report = {
        "base_rows_total": len(base_rows),
        "delta_rows_total": len(delta_rows),
        "matched_sentence_rows": 0,
        "sentence_candidates_added": 0,
        "phrase_candidates_added": 0,
        "phrase_rows_matched_by_key": 0,
        "base_only_rows_preserved": 0,
        "delta_only_rows_ignored": 0,
    }

    matched_keys: set[tuple[str, int, int]] = set()
    for base_row in base_rows:
        key = _row_key(base_row)
        delta_row = delta_by_key.get(key)
        if delta_row is None:
            merged_rows.append(base_row)
            report["base_only_rows_preserved"] += 1
            continue
        merged, stats = _merge_rows(base_row, delta_row)
        merged_rows.append(merged)
        matched_keys.add(key)
        report["matched_sentence_rows"] += 1
        report["sentence_candidates_added"] += stats["sentence_candidates_added"]
        report["phrase_candidates_added"] += stats["phrase_candidates_added"]
        report["phrase_rows_matched_by_key"] += stats["phrase_rows_matched_by_key"]

    report["delta_only_rows_ignored"] = sum(1 for key in delta_by_key if key not in matched_keys)
    report["merged_rows_total"] = len(merged_rows)
    return merged_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge two projected book-note corpora.")
    parser.add_argument("--base-input", required=True)
    parser.add_argument("--delta-input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    merged_rows, report = merge_projected_corpora(
        list(_iter_jsonl(args.base_input)),
        list(_iter_jsonl(args.delta_input)),
    )
    report.update(
        {
            "base_input": str(Path(args.base_input).resolve()),
            "delta_input": str(Path(args.delta_input).resolve()),
        }
    )
    _write_jsonl(args.output_jsonl, merged_rows)
    _write_json(args.report_json, report)
    print(
        json.dumps(
            {
                "status": "ok",
                "merged_rows": len(merged_rows),
                "output_jsonl": str(Path(args.output_jsonl).resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
