"""Promote the best sentence-level additions from v11 into a new v12 corpus.

The intent is conservative:

- keep v10 as the base,
- append only new book-fallback rows from v11 that carry sentence notes,
- ignore noisy or low-value phrase-only spillover from the open-access experiment.
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


def build_v12(
    *,
    v10_input: str,
    v11_input: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_rows = list(_iter_jsonl(v10_input))
    v11_rows = list(_iter_jsonl(v11_input))

    base_keys = {_row_key(row) for row in base_rows}
    selected_rows: list[dict[str, Any]] = []

    for row in v11_rows:
        if _row_key(row) in base_keys:
            continue
        augmentation = row.get("augmentation_meta") or {}
        if _norm(augmentation.get("augmentation_type")) != "book_sentence_fallback":
            continue
        sentence_candidates = row.get("sentence_note_candidates") or []
        if not sentence_candidates:
            continue
        selected_rows.append(row)

    merged_rows = base_rows + selected_rows

    report = {
        "promotion_version": "v11_sentence_fallbacks_to_v12",
        "base_input": str(Path(v10_input).resolve()),
        "source_input": str(Path(v11_input).resolve()),
        "base_rows_total": len(base_rows),
        "v11_rows_total": len(v11_rows),
        "selected_sentence_fallback_rows": len(selected_rows),
        "selected_source_document_ids": sorted(
            {
                _norm((row.get("augmentation_meta") or {}).get("source_document_id"))
                for row in selected_rows
                if _norm((row.get("augmentation_meta") or {}).get("source_document_id"))
            }
        ),
        "selected_sentence_note_texts": sorted(
            {
                _norm(candidate.get("note_text"))
                for row in selected_rows
                for candidate in (row.get("sentence_note_candidates") or [])
                if _norm(candidate.get("note_text"))
            }
        ),
        "output_rows_total": len(merged_rows),
    }
    return merged_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote the best sentence-level additions from v11 into v12.")
    parser.add_argument("--v10-input", required=True)
    parser.add_argument("--v11-input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows, report = build_v12(v10_input=args.v10_input, v11_input=args.v11_input)
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(rows),
                "selected_sentence_fallback_rows": report["selected_sentence_fallback_rows"],
                "output_jsonl": str(Path(args.output_jsonl).resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
