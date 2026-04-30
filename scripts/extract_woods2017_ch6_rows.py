#!/usr/bin/env python3
"""Extract targeted tense sections from Woods 2017 chapter 6 EPUB HTML."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

from lxml import html


SECTION_SPECS = (
    {"anchor": "h3-4", "heading": "Present and present progressive", "topic_key": "progressive"},
    {"anchor": "h3-5", "heading": "Past and past progressive", "topic_key": "progressive"},
    {"anchor": "h3-6", "heading": "Future and future progressive", "topic_key": "progressive"},
    {"anchor": "h3-7", "heading": "Present perfect and present perfect progressive", "topic_key": "perfect"},
    {"anchor": "h3-8", "heading": "Past perfect and past perfect progressive", "topic_key": "perfect"},
    {"anchor": "h3-9", "heading": "Future perfect and future perfect progressive", "topic_key": "perfect"},
)
DEFAULT_MEMBER = "OEBPS/text00010.html"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split())


def _text_of(node) -> str:
    pieces = [piece.strip() for piece in node.xpath(".//text()")]
    return _norm(" ".join(piece for piece in pieces if piece))


def _collect_section(heading_node) -> str:
    chunks: list[str] = []
    for sib in heading_node.itersiblings():
        if sib.tag in {"h2", "h3"}:
            break
        text = _text_of(sib)
        if not text:
            continue
        if text.startswith("Answers:"):
            continue
        if text.startswith("TABLE "):
            continue
        if text.startswith("The historical present"):
            break
        chunks.append(text)
        if len("\n\n".join(chunks)) > 3200:
            break
    return "\n\n".join(chunks).strip()


def build_rows(*, epub_path: str, member: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    epub = Path(epub_path)
    with zipfile.ZipFile(epub) as zf:
        root = html.fromstring(zf.read(member))

    rows: list[dict[str, Any]] = []
    for spec in SECTION_SPECS:
        node = root.xpath(f"//*[@id='{spec['anchor']}']")
        if not node:
            continue
        heading_node = node[0]
        heading = _text_of(heading_node)
        if heading != spec["heading"]:
            continue
        text = _collect_section(heading_node)
        if len(text) < 160:
            continue
        rows.append(
            {
                "source_path": str(epub),
                "row_type": "woods2017_ch6_section",
                "source_book": "woods_grammar_dummies_2017",
                "chapter_member": member,
                "heading": heading,
                "topic_key": str(spec["topic_key"]),
                "text": text,
            }
        )

    report = {
        "pipeline_version": "woods2017_ch6_rows_v1",
        "source_path": str(epub.resolve()),
        "member": member,
        "rows_total": len(rows),
        "topic_counts": {
            key: sum(1 for row in rows if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in rows})
        },
        "headings": [str(row.get("heading") or "") for row in rows],
    }
    return rows, report


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract targeted tense sections from Woods 2017 chapter 6.")
    parser.add_argument("--epub-path", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--member", default=DEFAULT_MEMBER)
    args = parser.parse_args()

    rows, report = build_rows(epub_path=args.epub_path, member=args.member)
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
