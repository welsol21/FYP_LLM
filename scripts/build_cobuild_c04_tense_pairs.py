#!/usr/bin/env python3
"""Build targeted progressive/perfect sentence pairs from COBUILD 2011 chapter 4."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import html


MEMBER = "OEBPS/c04.htm"
SECTION_NOTE_SPECS = (
    ("4.17", "progressive", "The present progressive describes an activity that is in progress at the moment of speaking."),
    ("4.18", "progressive", "The present progressive can emphasize the present moment or a temporary situation."),
    ("4.19", "progressive", "The present progressive can describe changes, trends, development, and progress."),
    ("4.20", "progressive", "The present progressive can describe a new or temporary habitual action."),
    ("4.31", "progressive", "The past progressive describes an action in progress or repeated actions in the past."),
    ("4.32", "progressive", "The past progressive can provide background for an event that happened afterwards."),
    ("4.35", "perfect", "The present perfect or present perfect progressive can describe an activity that started in the past and still continues."),
    ("4.36", "perfect", "The present perfect progressive can emphasize the duration of a recent event."),
    ("4.38", "perfect", "The past perfect progressive can emphasize an earlier ongoing activity before a past time."),
)

BAD_UTF_REPLACEMENTS = {
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "—": " - ",
    "–": " - ",
    "…": "...",
}
WS_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
BAD_TRAILING_ABBREV_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.$")
PROGRESSIVE_CONTEXT_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being|will be|have been|has been|had been)\b(?:\s+\w+){0,2}\s+\w+ing\b",
    re.IGNORECASE,
)
PERFECT_CONTEXT_RE = re.compile(
    r"\b(?:have|has|had)\b(?:\s+\w+){0,2}\s+\w+(?:ed|en|wn|lt|pt|nt|ft|ing)\b",
    re.IGNORECASE,
)


def _norm(value: Any) -> str:
    text = str(value or "")
    for src, dst in BAD_UTF_REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+([?.!,;:])", r"\1", text)
    return WS_RE.sub(" ", text.strip())


def _text_of(node) -> str:
    pieces = [piece.strip() for piece in node.xpath(".//text()")]
    return _norm(" ".join(piece for piece in pieces if piece))


def _is_heading(node) -> bool:
    return node.tag in {"h1", "h2", "h3", "h4", "h5"}


def _clean_sentence(text: str) -> str:
    text = _norm(text)
    text = re.sub(r"^\d+\.\d+\s*", "", text)
    return _norm(text)


def build_pairs(*, epub_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    epub = Path(epub_path)
    with zipfile.ZipFile(epub) as zf:
        root = html.fromstring(zf.read(MEMBER))
    body = root.find(".//body")
    children = list(body) if body is not None else []

    spec_by_marker = {marker: {"topic_key": topic, "note": note} for marker, topic, note in SECTION_NOTE_SPECS}
    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    current_marker = ""
    current_heading = ""
    current_topic = ""
    current_note = ""

    for node in children:
        text = _text_of(node)
        if not text:
            continue
        if _is_heading(node):
            if current_marker:
                current_marker = ""
                current_topic = ""
                current_note = ""
            current_heading = text
            continue
        marker = next((candidate for candidate in spec_by_marker if text.startswith(candidate)), "")
        if marker:
            current_marker = marker
            current_topic = spec_by_marker[marker]["topic_key"]
            current_note = spec_by_marker[marker]["note"]
            continue
        if not current_marker or node.tag != "div":
            continue
        for sentence in SENTENCE_SPLIT_RE.split(text):
            sentence = _clean_sentence(sentence)
            if len(sentence.split()) < 4:
                continue
            if not sentence.endswith((".", "!", "?")):
                continue
            if sentence.endswith("?"):
                continue
            if BAD_TRAILING_ABBREV_RE.search(sentence):
                continue
            if current_topic == "progressive":
                if not PROGRESSIVE_CONTEXT_RE.search(sentence):
                    continue
            elif current_topic == "perfect":
                if not PERFECT_CONTEXT_RE.search(sentence):
                    continue
            key = (current_topic, current_note.lower(), sentence.lower())
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                {
                    "source_path": str(epub),
                    "row_type": "cobuild_c04_tense_section",
                    "entry_head": current_heading,
                    "heading": current_heading,
                    "topic_key": current_topic,
                    "notation_text": current_note,
                    "context_text": sentence,
                    "pair_method": "cobuild_c04_tense_v1",
                }
            )

    report = {
        "pipeline_version": "cobuild_c04_tense_pairs_v1",
        "source_path": str(epub.resolve()),
        "member": MEMBER,
        "pairs_total": len(pairs),
        "topic_counts": {
            key: sum(1 for row in pairs if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in pairs})
        },
    }
    return pairs, report


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
    parser = argparse.ArgumentParser(description="Build targeted progressive/perfect pairs from COBUILD 2011 chapter 4.")
    parser.add_argument("--epub-path", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    pairs, report = build_pairs(epub_path=args.epub_path)
    _write_jsonl(args.output_jsonl, pairs)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
