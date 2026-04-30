"""Build a sentence-only family-aligned note pool for projection experiments."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_JSONL = "data/processed_sentence_seed/family_aligned_sentence_note_pool_v1.jsonl"
DEFAULT_REPORT_JSON = "data/processed_sentence_seed/family_aligned_sentence_note_pool_v1.report.json"

SOURCE_FILES = [
    "data/processed_book_notes_cobuild_2011_family_v1/book_note_rows_family_aligned_v2.jsonl",
    "data/processed_book_notes_mark_azar_family_v1/book_note_rows_family_aligned_v2.jsonl",
    "data/processed_book_notes_selected_2026_03_family_v1/book_note_rows_family_aligned_v2.jsonl",
    "data/processed_book_notes_open_access_2026_03_family_v1/book_note_rows_family_aligned_v2.jsonl",
    "data/processed_book_notes_yule_family_v1/book_note_rows_family_aligned_v2.jsonl",
]


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pair_key(row: dict[str, Any]) -> tuple[str, str]:
    context = row.get("context") or {}
    target = row.get("target") or {}
    return (
        _norm(context.get("sentence_text")).lower(),
        _norm(target.get("note_text")).lower(),
    )


def _sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    source = row.get("source") or {}
    context = row.get("context") or {}
    return (
        _norm(source.get("document_id")),
        _norm(source.get("topic")),
        _norm(context.get("sentence_text")),
    )


def build_pool() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reject_counts: Counter[str] = Counter()
    source_file_counts: Counter[str] = Counter()
    source_doc_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()
    seen_pairs: set[tuple[str, str]] = set()
    total_seen = 0

    for rel_path in SOURCE_FILES:
        path = Path(rel_path)
        if not path.exists():
            reject_counts[f"missing::{rel_path}"] += 1
            continue
        for row in _iter_jsonl(path):
            total_seen += 1
            context = row.get("context") or {}
            source = row.get("source") or {}
            if _norm(context.get("node_type")) != "Sentence":
                reject_counts["non_sentence_row"] += 1
                continue
            if not _norm(context.get("sentence_text")) or not _norm((row.get("target") or {}).get("note_text")):
                reject_counts["missing_text"] += 1
                continue
            alignment = (row.get("family_alignment") or {}).get("sentence") or {}
            if not any(_norm(alignment.get(key)) for key in ("exact_family_id", "bucketed_family_id", "presence_family_id")):
                reject_counts["missing_sentence_family_alignment"] += 1
                continue
            pair_key = _pair_key(row)
            if pair_key in seen_pairs:
                reject_counts["duplicate_pair"] += 1
                continue
            seen_pairs.add(pair_key)
            rows.append(row)
            source_file_counts[rel_path] += 1
            source_doc_counts[_norm(source.get("document_id"))] += 1
            topic_counts[_norm(source.get("topic"))] += 1

    rows.sort(key=_sort_key)
    report = {
        "builder": "build_family_aligned_sentence_note_pool.py",
        "source_files": SOURCE_FILES,
        "rows_seen": total_seen,
        "rows_kept": len(rows),
        "reject_counts": dict(reject_counts),
        "source_file_counts": dict(source_file_counts),
        "source_doc_counts": dict(source_doc_counts),
        "topic_counts_top50": dict(topic_counts.most_common(50)),
        "unique_note_texts": len({_norm((r.get('target') or {}).get('note_text')).lower() for r in rows}),
        "unique_sentences": len({_norm((r.get('context') or {}).get('sentence_text')).lower() for r in rows}),
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the family-aligned sentence note pool.")
    parser.add_argument("--output-jsonl", default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--report-json", default=DEFAULT_REPORT_JSON)
    args = parser.parse_args()

    rows, report = build_pool()
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
