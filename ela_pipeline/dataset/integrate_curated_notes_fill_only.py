"""Integrate curated family-level notes into an existing corpus by fill-only rules.

This script is intentionally conservative:

- keep existing book-based notes untouched;
- add curated sentence notes only where a sentence has no sentence notes;
- add curated phrase notes only where a phrase slot has no phrase notes.
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


def _phrase_key(phrase: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _norm(phrase.get("content")),
        _norm(phrase.get("part_of_speech")).lower(),
        _norm(phrase.get("grammatical_role")).lower(),
    )


def integrate_fill_only(
    *,
    base_rows: list[dict[str, Any]],
    curated_rows: list[dict[str, Any]],
    projection_version: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    curated_by_key = {_row_key(row): row for row in curated_rows}
    output_rows: list[dict[str, Any]] = []

    report = {
        "base_rows_total": len(base_rows),
        "curated_rows_total": len(curated_rows),
        "matched_rows_total": 0,
        "missing_curated_rows_total": 0,
        "sentence_rows_filled": 0,
        "sentence_candidates_added": 0,
        "phrase_slots_filled": 0,
        "phrase_candidates_added": 0,
        "rows_with_any_curated_fill": 0,
    }

    for base_row in base_rows:
        key = _row_key(base_row)
        curated_row = curated_by_key.get(key)
        row = json.loads(json.dumps(base_row, ensure_ascii=False))
        row_fill_count = 0
        row["projection_version"] = projection_version

        if curated_row is None:
            report["missing_curated_rows_total"] += 1
            output_rows.append(row)
            continue

        report["matched_rows_total"] += 1

        if not (row.get("sentence_note_candidates") or []):
            curated_sentence_candidates = list(curated_row.get("sentence_note_candidates") or [])
            if curated_sentence_candidates:
                row["sentence_note_candidates"] = curated_sentence_candidates
                report["sentence_rows_filled"] += 1
                report["sentence_candidates_added"] += len(curated_sentence_candidates)
                row_fill_count += 1

        base_phrases = row.get("phrase_entries") or []
        curated_phrases_by_key = {
            _phrase_key(phrase): phrase for phrase in (curated_row.get("phrase_entries") or [])
        }
        for phrase in base_phrases:
            if phrase.get("note_candidates") or []:
                continue
            curated_phrase = curated_phrases_by_key.get(_phrase_key(phrase))
            if curated_phrase is None:
                continue
            curated_candidates = list(curated_phrase.get("note_candidates") or [])
            if not curated_candidates:
                continue
            phrase["note_candidates"] = curated_candidates
            report["phrase_slots_filled"] += 1
            report["phrase_candidates_added"] += len(curated_candidates)
            row_fill_count += 1

        if row_fill_count:
            report["rows_with_any_curated_fill"] += 1
            row["curated_fill_meta"] = {
                "fill_strategy": "fill_only",
                "curated_source": "ingested_corpus_book_projection_v8_curated_notes",
            }

        output_rows.append(row)

    report["output_rows_total"] = len(output_rows)
    return output_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill uncovered corpus slots with curated family-level notes.")
    parser.add_argument("--base-input", required=True)
    parser.add_argument("--curated-input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--projection-version", default="book_note_corpus_projection_v9")
    args = parser.parse_args()

    rows, report = integrate_fill_only(
        base_rows=list(_iter_jsonl(args.base_input)),
        curated_rows=list(_iter_jsonl(args.curated_input)),
        projection_version=args.projection_version,
    )
    report.update(
        {
            "base_input": str(Path(args.base_input).resolve()),
            "curated_input": str(Path(args.curated_input).resolve()),
            "projection_version": args.projection_version,
        }
    )
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
