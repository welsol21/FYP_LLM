#!/usr/bin/env python3
"""Extract targeted tense sections from Geraldine Woods' chapter 3 EPUB HTML."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

from lxml import html


SECTION_SPECS = (
    {"anchor": "a7", "heading": "Present and present progressive", "topic_key": "progressive"},
    {"anchor": "a8", "heading": "Past and past progressive", "topic_key": "progressive"},
    {"anchor": "a9", "heading": "Future and future progressive", "topic_key": "progressive"},
    {"anchor": "a11", "heading": "Present perfect and present perfect progressive", "topic_key": "perfect"},
    {"anchor": "a12", "heading": "Past perfect and past perfect progressive", "topic_key": "perfect"},
    {"anchor": "a13", "heading": "Future perfect and future perfect progressive", "topic_key": "perfect"},
)
DEFAULT_MEMBER = "OEBPS/07_546642-ch03.xhtml"
QUIZ_PROMPT = "Now find the verbs and sort them into present progressive, past progressive, and future progressive forms."


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split())


def _text_of(node) -> str:
    pieces = [piece.strip() for piece in node.xpath(".//text()")]
    return _norm(" ".join(piece for piece in pieces if piece))


def _is_heading(node) -> bool:
    classes = set((node.get("class") or "").split())
    return bool({"heading-1", "heading-2"} & classes)


def _collect_section(children: list[Any], start_idx: int) -> str:
    chunks: list[str] = []
    for idx in range(start_idx + 1, len(children)):
        node = children[idx]
        if _is_heading(node):
            break
        text = _text_of(node)
        if not text:
            continue
        if text.startswith("Answer:") or text.startswith("Answers:"):
            continue
        if text.startswith("Which one is correct?"):
            continue
        if text.startswith("Some tense pairs"):
            continue
        chunks.append(text)
    return "\n\n".join(chunks).strip()


def _collect_quiz_block(children: list[Any]) -> str:
    chunks: list[str] = []
    capture = False
    for node in children:
        text = _text_of(node)
        if not text:
            continue
        if not capture and text == QUIZ_PROMPT:
            capture = True
        if not capture:
            continue
        if _is_heading(node):
            break
        if text.startswith("Find the verbs and sort them into present, past, and future tenses."):
            continue
        chunks.append(text)
    return "\n\n".join(chunks).strip()


def build_rows(*, epub_path: str, member: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    epub = Path(epub_path)
    with zipfile.ZipFile(epub) as zf:
        raw = zf.read(member)
    root = html.fromstring(raw)
    story = root.xpath(".//div[contains(@class, 'story')]")
    container = story[0] if story else root.find(".//body")
    children = list(container.iterchildren()) if container is not None else []

    rows: list[dict[str, Any]] = []
    for idx, node in enumerate(children):
        node_id = node.get("id") or ""
        if not node_id:
            continue
        matched = next((spec for spec in SECTION_SPECS if spec["anchor"] == node_id), None)
        if not matched:
            continue
        heading = _text_of(node)
        if heading != matched["heading"]:
            continue
        text = _collect_section(children, idx)
        if len(text) < 120:
            continue
        rows.append(
            {
                "source_path": str(epub),
                "row_type": "dummies_chapter3_section",
                "source_book": "geraldine_woods_dummies_2010",
                "chapter_member": member,
                "heading": heading,
                "topic_key": matched["topic_key"],
                "text": text,
            }
        )

    quiz_text = _collect_quiz_block(children)
    if len(quiz_text) >= 120:
        rows.append(
            {
                "source_path": str(epub),
                "row_type": "dummies_chapter3_section",
                "source_book": "geraldine_woods_dummies_2010",
                "chapter_member": member,
                "heading": "Progressive forms practice",
                "topic_key": "progressive",
                "text": quiz_text,
            }
        )

    report = {
        "pipeline_version": "dummies_chapter3_rows_v1",
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
    parser = argparse.ArgumentParser(description="Extract targeted progressive sections from Geraldine Woods chapter 3.")
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
