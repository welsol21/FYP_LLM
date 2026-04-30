#!/usr/bin/env python3
"""Build perfect-tense note/context pairs from Woods 2017 chapter 6 rows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
BAD_UTF_REPLACEMENTS = {
    "â": "'",
    "â": "'",
    "â": '"',
    "â": '"',
    "â": " - ",
}

HEADING_TO_NOTE = {
    "Present perfect and present perfect progressive": "The present perfect links a past action or state to the present.",
    "Past perfect and past perfect progressive": "The past perfect shows an earlier action before another past action.",
    "Future perfect and future perfect progressive": "The future perfect shows an action completed before another future point.",
}

PERFECT_PATTERNS = {
    "Present perfect and present perfect progressive": re.compile(
        r"\b(?:have|has|have been|has been)\b", re.IGNORECASE
    ),
    "Past perfect and past perfect progressive": re.compile(
        r"\b(?:had|had been)\b", re.IGNORECASE
    ),
    "Future perfect and future perfect progressive": re.compile(
        r"\b(?:will have|will have been)\b", re.IGNORECASE
    ),
}


def _norm(value: Any) -> str:
    text = str(value or "")
    for src, dst in BAD_UTF_REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"\s+([?.!,;:])", r"\1", text)
    return text


def _clean_context(text: str) -> str:
    text = _norm(text)
    text = re.sub(r"^(?:First, check out examples with plain present perfect tense:\s*)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:Here are some examples of the past perfect tense:\s*)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:First, take a look at the plain version of the future perfect:\s*)", "", text, flags=re.IGNORECASE)
    return _norm(text)


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


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


def build_pairs(rows_jsonl: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    rows = list(_iter_jsonl(rows_jsonl))

    for row in rows:
        heading = _norm(row.get("heading"))
        if heading not in HEADING_TO_NOTE:
            continue
        note = HEADING_TO_NOTE[heading]
        pattern = PERFECT_PATTERNS[heading]
        text = _norm(row.get("text"))
        for sentence in SENTENCE_SPLIT_RE.split(text):
            sentence = _norm(sentence)
            if len(sentence.split()) < 5:
                continue
            if not sentence.endswith((".", "!", "?")):
                continue
            if not pattern.search(sentence):
                continue
            if "Table 6-" in sentence or "The verb" in sentence or "pronouns" in sentence:
                continue
            if sentence.startswith("For that pairing, you need has."):
                continue
            if sentence.lower().startswith(("the present perfect", "the past perfect", "the future perfect", "the two present perfect")):
                continue
            sentence = _clean_context(sentence)
            if len(sentence.split()) < 5:
                continue
            key = (_norm(row.get("topic_key")).lower(), note.lower(), sentence.lower())
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                {
                    "source_path": row.get("source_path"),
                    "row_type": "woods2017_ch6_perfect_section",
                    "entry_head": heading,
                    "heading": heading,
                    "topic_key": "perfect",
                    "notation_text": note,
                    "context_text": sentence,
                    "pair_method": "woods2017_ch6_perfect_v1",
                }
            )

    report = {
        "pipeline_version": "woods2017_ch6_perfect_pairs_v1",
        "rows_jsonl": str(Path(rows_jsonl).resolve()),
        "rows_seen": len(rows),
        "pairs_total": len(pairs),
        "topic_counts": {
            key: sum(1 for row in pairs if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in pairs})
        },
    }
    return pairs, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Woods 2017 perfect-tense pairs from targeted rows.")
    parser.add_argument("--rows-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    pairs, report = build_pairs(args.rows_jsonl)
    _write_jsonl(args.output_jsonl, pairs)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
