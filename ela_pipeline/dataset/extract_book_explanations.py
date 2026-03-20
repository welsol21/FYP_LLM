"""CLI for the universal grammar-book extraction engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ela_pipeline.dataset.book_extraction import UniversalBookExtractionEngine, build_default_parsers
from ela_pipeline.dataset.book_extraction.engine import discover_supported_book_paths


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract explanatory snippets from grammar books.")
    parser.add_argument("--input", required=True, help="Book file or directory.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--max-books", type=int, default=0, help="Optional limit for processed books.")
    parser.add_argument("--ocr-max-pages", type=int, default=40, help="How many pages to OCR per scanned PDF.")
    parser.add_argument("--disable-ocr", action="store_true", help="Disable OCR fallback for scanned PDFs and images.")
    parser.add_argument(
        "--cache-dir",
        default="data/processed_book_text_cache",
        help="Directory where parsed raw book texts and metadata are cached.",
    )
    args = parser.parse_args()

    engine = UniversalBookExtractionEngine(
        parsers=build_default_parsers(
            enable_ocr=not args.disable_ocr,
            ocr_max_pages=max(1, int(args.ocr_max_pages)),
        ),
        cache_dir=args.cache_dir,
    )
    paths = discover_supported_book_paths(args.input, engine)
    if args.max_books > 0:
        paths = paths[: args.max_books]
    snippets = []
    for path in paths:
        snippets.extend(item.as_dict() for item in engine.extract_from_path(path))

    report = {
        "input": str(Path(args.input).resolve()),
        "books_processed": len(paths),
        "snippets_total": len(snippets),
        "ocr_enabled": not args.disable_ocr,
        "ocr_max_pages": max(1, int(args.ocr_max_pages)),
        "cache_dir": str(Path(args.cache_dir).resolve()),
        "books": paths,
    }
    _write_jsonl(args.output_jsonl, snippets)
    _write_json(args.report_json, report)
    print(json.dumps({"status": "ok", "snippets_total": len(snippets)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
