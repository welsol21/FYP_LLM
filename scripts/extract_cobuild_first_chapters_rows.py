#!/usr/bin/env python3
"""Extract handbook rows from selected Collins COBUILD English Grammar (2011) chapters."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import html


DEFAULT_CHAPTER_FILES = ("OEBPS/c01.htm", "OEBPS/c02.htm")
SEC_ID_RE = re.compile(r"^sec\d+\.\d+$")
WS_RE = re.compile(r"\s+")


def _norm(value: Any) -> str:
    return WS_RE.sub(" ", str(value or "").strip())


def _iter_top_children(epub_path: Path, member: str):
    with zipfile.ZipFile(epub_path) as zf:
        raw = zf.read(member)
    root = html.fromstring(raw)
    body = root.find(".//body")
    if body is None:
        return []
    return list(body)


def _text_of(node) -> str:
    pieces = [t.strip() for t in node.xpath(".//text()")]
    return _norm(" ".join(piece for piece in pieces if piece))


def _is_heading(node) -> bool:
    return node.tag in {"h1", "h2", "h3", "h4", "h5"}


def _is_section_start(node) -> bool:
    if node.tag == "div":
        paragraphs = node.xpath("./p[@id]")
        if paragraphs:
            pid = paragraphs[0].get("id") or ""
            return bool(SEC_ID_RE.match(pid))
    if node.tag == "p":
        pid = node.get("id") or ""
        return bool(SEC_ID_RE.match(pid))
    return False


def _topic_key_from_heading(heading: str, chapter_heading: str) -> str:
    lowered = f"{chapter_heading} {heading}".lower()
    if "question tag" in lowered:
        return "question_tags"
    if "conditional" in lowered or "if-clause" in lowered or "unless" in lowered:
        return "conditional_sentences"
    if "passive" in lowered:
        return "passive_voice"
    if "relative clause" in lowered or "defining relative" in lowered or "non-defining relative" in lowered:
        return "relative_clauses"
    if "that-clause" in lowered:
        return "that_clause"
    if "present perfect" in lowered or "past perfect" in lowered or "future perfect" in lowered:
        return "perfect"
    if "progressive" in lowered or "continuous" in lowered:
        return "progressive"
    if "modal" in lowered:
        return "modal"
    if "there is" in lowered or "there are" in lowered:
        return "existential"
    if "adjective" in lowered:
        return "adjectives"
    if "noun phrase" in lowered:
        return "noun_phrase"
    if "pronoun" in lowered:
        return "pronouns"
    if "determiner" in lowered:
        return "determiners"
    if "noun" in lowered:
        return "nouns"
    return ""


def build_rows(epub_path: str, chapter_files: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    epub = Path(epub_path)
    rows: list[dict[str, Any]] = []
    chapter_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}

    for member in chapter_files:
        children = _iter_top_children(epub, member)
        current_chapter = ""
        current_heading = ""
        index = 0
        while index < len(children):
            node = children[index]
            text = _text_of(node)
            if not text:
                index += 1
                continue
            if _is_heading(node):
                if node.tag == "h1":
                    current_chapter = text
                current_heading = text
                index += 1
                continue
            if not _is_section_start(node):
                index += 1
                continue

            chunks = [text]
            last_index = index
            follow = 0
            for look_ahead in range(index + 1, len(children)):
                nxt = children[look_ahead]
                if _is_heading(nxt) or _is_section_start(nxt):
                    break
                nxt_text = _text_of(nxt)
                if not nxt_text:
                    continue
                if len(nxt_text) > 900:
                    break
                chunks.append(nxt_text)
                last_index = look_ahead
                follow += 1
                if follow >= 4:
                    break

            row_text = "\n\n".join(chunks)
            if len(row_text) > 3200:
                index += 1
                continue
            topic_key = _topic_key_from_heading(current_heading, current_chapter)
            rows.append(
                {
                    "source_path": str(epub),
                    "row_type": "cobuild_first_chapter_snippet",
                    "chapter_file": member,
                    "heading": current_heading,
                    "chapter_heading": current_chapter,
                    "topic_key": topic_key,
                    "text": row_text,
                }
            )
            chapter_counts[member] = chapter_counts.get(member, 0) + 1
            topic_counts[topic_key or "(none)"] = topic_counts.get(topic_key or "(none)", 0) + 1
            index = last_index + 1

    report = {
        "pipeline_version": "cobuild_first_chapters_rows_v1",
        "source_path": str(epub.resolve()),
        "chapters": list(chapter_files),
        "rows_total": len(rows),
        "chapter_counts": chapter_counts,
        "topic_counts": topic_counts,
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
    parser = argparse.ArgumentParser(description="Extract handbook rows from selected COBUILD 2011 chapters.")
    parser.add_argument("--epub-path", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--chapters", nargs="*", default=list(DEFAULT_CHAPTER_FILES))
    args = parser.parse_args()

    rows, report = build_rows(args.epub_path, tuple(args.chapters))
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
