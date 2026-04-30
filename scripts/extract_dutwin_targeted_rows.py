#!/usr/bin/env python3
"""Extract targeted grammar sections from Phyllis Dutwin's EPUB."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

from lxml import html


SECTION_SPECS = (
    {
        "member": "ops/ch01.html",
        "anchor": "ch01sec1lev4",
        "heading": "Perfect Verb Tenses",
        "topic_key": "perfect",
    },
    {
        "member": "ops/ch03.html",
        "anchor": "ch03sec1lev1",
        "heading": "Perfect Tenses",
        "topic_key": "perfect",
    },
    {
        "member": "ops/ch03.html",
        "anchor": "ch03sec1lev7",
        "heading": "Relative Pronouns",
        "topic_key": "relative_clauses",
    },
    {
        "member": "ops/ch03.html",
        "anchor": "ch03sec1lev8",
        "heading": "Who, Whom, That, or Which?",
        "topic_key": "relative_clauses",
    },
)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split())


def _text_of(node) -> str:
    pieces = [piece.strip() for piece in node.xpath(".//text()")]
    return _norm(" ".join(piece for piece in pieces if piece))


def _is_major_heading(node) -> bool:
    return node.tag in {"h3", "h4"}


def _iter_container_children(root) -> list[Any]:
    body = root.find(".//body")
    return list(body.iterchildren()) if body is not None else []


def _collect_section(children: list[Any], start_idx: int) -> str:
    chunks: list[str] = []
    for idx in range(start_idx + 1, len(children)):
        node = children[idx]
        if _is_major_heading(node):
            break
        text = _text_of(node)
        if not text:
            continue
        if text.startswith("Written Practice"):
            break
        if text.startswith("COMMON ERRORS"):
            break
        if text.startswith("Answer Key"):
            break
        chunks.append(text)
        if len("\n\n".join(chunks)) > 2600:
            break
    return "\n\n".join(chunks).strip()


def build_rows(*, epub_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    epub = Path(epub_path)
    cache: dict[str, list[Any]] = {}
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(epub) as zf:
        for spec in SECTION_SPECS:
            member = str(spec["member"])
            if member not in cache:
                root = html.fromstring(zf.read(member))
                cache[member] = _iter_container_children(root)
            children = cache[member]
            anchor = str(spec["anchor"])
            heading = str(spec["heading"])
            found_idx = -1
            for idx, node in enumerate(children):
                node_ids = {node.get("id") or ""} | {str(item) for item in node.xpath(".//@id")}
                if anchor in node_ids:
                    found_idx = idx
                    break
            if found_idx < 0:
                continue
            text = _collect_section(children, found_idx)
            if len(text) < 160:
                continue
            rows.append(
                {
                    "source_path": str(epub),
                    "row_type": "dutwin_targeted_section",
                    "source_book": "phyllis_dutwin_grammar_demystified_2010",
                    "chapter_member": member,
                    "heading": heading,
                    "topic_key": str(spec["topic_key"]),
                    "text": text,
                }
            )

    report = {
        "pipeline_version": "dutwin_targeted_rows_v1",
        "source_path": str(epub.resolve()),
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
    parser = argparse.ArgumentParser(description="Extract targeted sections from Phyllis Dutwin EPUB.")
    parser.add_argument("--epub-path", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows, report = build_rows(epub_path=args.epub_path)
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
