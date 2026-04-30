#!/usr/bin/env python3
"""Split typed grammar dataset for engine-facing and span-extraction workflows."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


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


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("node_type", "")),
            str(row.get("topic_key", "")),
            str(row.get("source_name", "")),
            str(row.get("context_text", "")),
        ),
    )


def build_splits(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    engine_ready: list[dict[str, Any]] = []
    span_backlog: list[dict[str, Any]] = []
    phrase_word: list[dict[str, Any]] = []
    clause_only: list[dict[str, Any]] = []

    for row in rows:
        node_type = str(row.get("node_type") or "")
        span_status = str(row.get("span_status") or "")
        if node_type in {"Sentence", "Clause"}:
            engine_ready.append(row)
        if node_type == "Clause":
            clause_only.append(row)
        if node_type in {"Phrase", "Word"}:
            phrase_word.append(row)
        if span_status == "needs_span_extraction":
            span_backlog.append(row)

    return {
        "engine_ready_sentence_clause": _sort_rows(engine_ready),
        "clause_only": _sort_rows(clause_only),
        "phrase_word_backlog": _sort_rows(phrase_word),
        "needs_span_extraction": _sort_rows(span_backlog),
    }


def summarize(rows: list[dict[str, Any]], *, name: str) -> dict[str, Any]:
    node_counts = Counter(str(row.get("node_type") or "") for row in rows)
    topic_counts = Counter(str(row.get("topic_key") or "") for row in rows)
    span_counts = Counter(str(row.get("span_status") or "") for row in rows)
    source_counts = Counter(str(row.get("source_name") or "") for row in rows)
    return {
        "name": name,
        "rows_total": len(rows),
        "node_type_counts": dict(sorted(node_counts.items())),
        "topic_counts": dict(sorted(topic_counts.items())),
        "span_status_counts": dict(sorted(span_counts.items())),
        "top_sources": dict(source_counts.most_common(20)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Split typed grammar dataset for engine and span workflows.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_path = Path(args.input_jsonl)
    output_dir = Path(args.output_dir)
    rows = list(_iter_jsonl(input_path))
    splits = build_splits(rows)

    report: dict[str, Any] = {
        "input_jsonl": str(input_path.resolve()),
        "rows_total": len(rows),
        "node_type_counts": dict(sorted(Counter(str(r.get("node_type") or "") for r in rows).items())),
        "context_type_counts": dict(sorted(Counter(str(r.get("context_type") or "") for r in rows).items())),
        "split_reports": {},
    }

    for split_name, split_rows in splits.items():
        out_jsonl = output_dir / f"{split_name}.jsonl"
        _write_jsonl(out_jsonl, split_rows)
        report["split_reports"][split_name] = summarize(split_rows, name=split_name)

    _write_json(output_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
