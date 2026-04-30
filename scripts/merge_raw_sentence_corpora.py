from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def merge_raw_sentence_corpora(
    *,
    inputs: list[str],
    output_jsonl: str,
    report_json: str,
) -> dict[str, Any]:
    out_path = Path(output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    merged: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    duplicate_rows = 0
    per_input_read: Counter[str] = Counter()
    per_input_kept: Counter[str] = Counter()
    per_source_name: Counter[str] = Counter()

    for input_path in inputs:
        src = Path(input_path)
        rows = _iter_jsonl(src)
        per_input_read[str(src)] = len(rows)
        for row in rows:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            text_key = " ".join(text.split()).lower()
            if text_key in seen_texts:
                duplicate_rows += 1
                continue
            seen_texts.add(text_key)
            merged.append(row)
            per_input_kept[str(src)] += 1
            per_source_name[str(row.get("source_name") or "unknown").strip() or "unknown"] += 1

    with out_path.open("w", encoding="utf-8") as fh:
        for row in merged:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "inputs": inputs,
        "rows_written": len(merged),
        "duplicate_rows": duplicate_rows,
        "per_input_read": dict(per_input_read),
        "per_input_kept": dict(per_input_kept),
        "per_source_name": dict(sorted(per_source_name.items())),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge raw sentence corpora JSONL files with exact-text dedup.")
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    report = merge_raw_sentence_corpora(
        inputs=args.input,
        output_jsonl=args.output_jsonl,
        report_json=args.report_json,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
