"""Extract structured rows from chapter-style grammar handbooks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.handbook_adapter import supports_payload
from ela_pipeline.dataset.book_extraction.oxford_handbook_adapter import (
    OXFORD_HANDBOOK_CONFIG,
    extract_oxford_handbook_rows,
)


def _write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract handbook-aware rows from a grammar handbook.")
    parser.add_argument("--payload-json", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    payload_dict = json.loads(Path(args.payload_json).read_text(encoding="utf-8"))
    payload_txt = Path(args.payload_json).with_name("payload.txt")
    payload = BookTextPayload(
        source_path=str(payload_dict.get("source_path") or ""),
        parser_name=str(payload_dict.get("parser_name") or ""),
        format=str(payload_dict.get("format") or ""),
        text=payload_txt.read_text(encoding="utf-8", errors="ignore"),
        metadata=dict(payload_dict.get("metadata") or {}),
    )

    if not supports_payload(payload, OXFORD_HANDBOOK_CONFIG):
        raise SystemExit("Unsupported handbook payload")

    rows = [row.as_dict() for row in extract_oxford_handbook_rows(payload)]
    report = {
        "pipeline_version": "handbook_rows_v1",
        "source_path": payload.source_path,
        "rows_total": len(rows),
        "topic_counts": {
            key: sum(1 for row in rows if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in rows})
        },
    }
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
