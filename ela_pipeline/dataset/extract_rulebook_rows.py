"""Extract structured rows from rulebook-style grammar dictionaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ela_pipeline.dataset.book_extraction import UniversalBookExtractionEngine, build_default_parsers
from ela_pipeline.dataset.book_extraction.oxford_dictionary_adapter import (
    OXFORD_DICTIONARY_CONFIG,
    extract_oxford_dictionary_rows,
)


def _write_jsonl(path: str, rows: list[dict]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: str, payload: dict) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


PROFILE_HANDLERS = {
    OXFORD_DICTIONARY_CONFIG.name: extract_oxford_dictionary_rows,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract rulebook-aware rows from a grammar dictionary.")
    parser.add_argument("--input", required=True, help="Book path.")
    parser.add_argument("--profile", default=OXFORD_DICTIONARY_CONFIG.name, choices=sorted(PROFILE_HANDLERS))
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--cache-dir", default="data/processed_book_text_cache")
    parser.add_argument("--ocr-max-pages", type=int, default=40)
    parser.add_argument("--disable-ocr", action="store_true")
    args = parser.parse_args()

    engine = UniversalBookExtractionEngine(
        parsers=build_default_parsers(
            enable_ocr=not args.disable_ocr,
            ocr_max_pages=max(1, int(args.ocr_max_pages)),
        ),
        cache_dir=args.cache_dir,
    )
    payload = engine.parse_book(args.input)
    handler = PROFILE_HANDLERS[args.profile]
    rows = [row.as_dict() for row in handler(payload)]
    report = {
        "profile": args.profile,
        "input": str(Path(args.input).resolve()),
        "cache_dir": str(Path(args.cache_dir).resolve()),
        "rows_total": len(rows),
        "row_types": {
            key: sum(1 for row in rows if row.get("row_type") == key)
            for key in sorted({str(row.get("row_type")) for row in rows})
        },
        "example_bearing_rows": sum(1 for row in rows if int(row.get("example_marker_count") or 0) > 0),
    }
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
