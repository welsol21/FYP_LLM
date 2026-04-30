#!/usr/bin/env python3
"""Build targeted question-tag sentence pairs from COBUILD 2011 chapter 5."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import html


MEMBER = "OEBPS/c05.htm"
SECTION_SPECS = (
    ("5.16", "Question tags are formed with an auxiliary or form of be/do plus a pronoun referring to the subject."),
    ("5.17", "Question tags are short questions added to a statement to check or confirm something."),
    ("5.19", "Question tags can also be used for reactions, suggestions, or softened instructions."),
)

BAD_UTF_REPLACEMENTS = {
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "—": " - ",
    "–": " - ",
}
WS_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
QUESTION_TAG_CONTEXT_RE = re.compile(
    r",\s*(?:am|is|are|was|were|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must)"
    r"(?:n't| not)?\s+(?:i|you|he|she|it|we|they|there)\?",
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
    text = re.sub(r"\baren['’]?st\b", "aren't", text, flags=re.IGNORECASE)
    return _norm(text)


def build_pairs(*, epub_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    epub = Path(epub_path)
    with zipfile.ZipFile(epub) as zf:
        root = html.fromstring(zf.read(MEMBER))
    body = root.find(".//body")
    children = list(body) if body is not None else []

    note_by_marker = {marker: note for marker, note in SECTION_SPECS}
    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    current_marker = ""
    current_note = ""
    current_heading = ""

    for node in children:
        text = _text_of(node)
        if not text:
            continue
        if _is_heading(node):
            if current_marker and text.lower() not in {"forming question tags", "other uses of question tags", "replying to tags"}:
                current_marker = ""
                current_note = ""
            current_heading = text
            continue
        marker = next((candidate for candidate in note_by_marker if text.startswith(candidate)), "")
        if marker:
            current_marker = marker
            current_note = note_by_marker[marker]
            continue
        if not current_marker or node.tag != "div":
            continue
        for sentence in SENTENCE_SPLIT_RE.split(text):
            sentence = _clean_sentence(sentence)
            if len(sentence.split()) < 4:
                continue
            if not sentence.endswith("?"):
                continue
            if not QUESTION_TAG_CONTEXT_RE.search(sentence):
                continue
            if "aren'st" in sentence.lower():
                continue
            key = (current_note.lower(), sentence.lower())
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                {
                    "source_path": str(epub),
                    "row_type": "cobuild_c05_question_tags",
                    "entry_head": current_heading,
                    "heading": current_heading,
                    "topic_key": "question_tags",
                    "notation_text": current_note,
                    "context_text": sentence,
                    "pair_method": "cobuild_c05_question_tags_v1",
                }
            )

    report = {
        "pipeline_version": "cobuild_c05_question_tag_pairs_v1",
        "source_path": str(epub.resolve()),
        "member": MEMBER,
        "pairs_total": len(pairs),
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
    parser = argparse.ArgumentParser(description="Build targeted question-tag pairs from COBUILD 2011 chapter 5.")
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
