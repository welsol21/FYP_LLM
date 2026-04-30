#!/usr/bin/env python3
"""Build targeted passive/existential sentence pairs from Geraldine Woods 2010 EPUB."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import html


SECTION_SPECS = (
    {
        "member": "OEBPS/25_546642-ch18.xhtml",
        "anchor": "a2",
        "topic_key": "passive_voice",
        "heading": "Giving Voice to Verbs",
        "note": "The passive voice presents the subject as the receiver or affected participant of the action.",
    },
    {
        "member": "OEBPS/25_546642-ch18.xhtml",
        "anchor": "a5",
        "topic_key": "existential",
        "heading": "There is a problem with boring verbs",
        "note": "Existential there often introduces the existence or presence of something.",
    },
    {
        "member": "OEBPS/08_546642-ch04.xhtml",
        "anchor": "a12",
        "topic_key": "existential",
        "heading": "Choosing the correct verb for here and there sentences",
        "note": "In existential there sentences, the verb agrees with the real subject that follows it.",
    },
)

BAD_UTF_REPLACEMENTS = {
    "â": "'",
    "â": "'",
    "â": '"',
    "â": '"',
    "â": " - ",
    "â": " - ",
}
WS_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
PASSIVE_CONTEXT_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being|get|gets|got|have been|has been|had been|will be)\b"
    r"(?:\s+\w+){0,3}\s+\w+(?:ed|en|wn|lt|pt|nt|ft)\b",
    re.IGNORECASE,
)
EXISTENTIAL_CONTEXT_RE = re.compile(
    r"\bthere\s+(?:is|are|was|were|'s|will be|would be|could be|can be|might be|may be|must be|should be|"
    r"has been|have been|had been|to be|being|could have been|would have been|might have been)\b",
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
    return (node.get("class") or "") in {"heading-1", "heading-2", "chap-title"}


def _allowed_example_node(node, *, topic_key: str) -> bool:
    cls = node.get("class") or ""
    if topic_key == "passive_voice":
        return cls.startswith("unnumbered") or cls == "num-list1"
    if topic_key == "existential":
        return cls.startswith("unnumbered") or cls == "num-list1"
    return False


def _clean_sentence(text: str) -> str:
    text = _norm(text)
    text = re.sub(r"^[A-Z]\.\s*", "", text)
    text = re.sub(r"\s+\(.*?\)\s*$", "", text)
    text = re.sub(r"\s+NOT\s+.*$", "", text, flags=re.IGNORECASE)
    return _norm(text)


def _collect_pairs(children: list[Any], start_idx: int, spec: dict[str, str]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    seen_contexts: set[str] = set()
    topic_key = spec["topic_key"]
    note = spec["note"]
    for idx in range(start_idx + 1, len(children)):
        node = children[idx]
        if idx > start_idx + 1 and _is_heading(node):
            break
        if not _allowed_example_node(node, topic_key=topic_key):
            continue
        text = _text_of(node)
        if not text:
            continue
        for sentence in SENTENCE_SPLIT_RE.split(text):
            sentence = _clean_sentence(sentence)
            if len(sentence.split()) < 4:
                continue
            if not sentence.endswith((".", "!", "?")):
                continue
            if topic_key == "passive_voice":
                if not PASSIVE_CONTEXT_RE.search(sentence):
                    continue
            elif topic_key == "existential":
                if not EXISTENTIAL_CONTEXT_RE.search(sentence):
                    continue
            if sentence.lower() in seen_contexts:
                continue
            seen_contexts.add(sentence.lower())
            pairs.append(
                {
                    "source_path": spec["source_path"],
                    "row_type": "geraldine2010_targeted_section",
                    "entry_head": spec["heading"],
                    "heading": spec["heading"],
                    "topic_key": topic_key,
                    "notation_text": note,
                    "context_text": sentence,
                    "pair_method": "geraldine2010_targeted_v1",
                }
            )
    return pairs


def build_pairs(*, epub_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    epub = Path(epub_path)
    pairs: list[dict[str, Any]] = []
    with zipfile.ZipFile(epub) as zf:
        cache: dict[str, list[Any]] = {}
        for raw_spec in SECTION_SPECS:
            spec = dict(raw_spec)
            spec["source_path"] = str(epub)
            member = spec["member"]
            if member not in cache:
                root = html.fromstring(zf.read(member))
                body = root.find(".//body")
                story = body.xpath(".//div[contains(@class, 'story')]") if body is not None else []
                container = story[0] if story else body
                cache[member] = list(container.iterchildren()) if container is not None else []
            children = cache[member]
            for idx, node in enumerate(children):
                if (node.get("id") or "") != spec["anchor"]:
                    continue
                pairs.extend(_collect_pairs(children, idx, spec))
                break

    report = {
        "pipeline_version": "geraldine2010_targeted_pairs_v1",
        "source_path": str(epub.resolve()),
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
    parser = argparse.ArgumentParser(description="Build Geraldine 2010 passive/existential sentence pairs.")
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
