#!/usr/bin/env python3
"""Build sentence-oriented handbook rows from Oxford Practical English Usage."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ENTRY_MANIFEST = (
    {"entry_id": 256, "topic_key": "conditional_sentences"},
    {"entry_id": 257, "topic_key": "conditional_sentences"},
    {"entry_id": 258, "topic_key": "conditional_sentences"},
    {"entry_id": 259, "topic_key": "conditional_sentences"},
    {"entry_id": 260, "topic_key": "conditional_sentences"},
    {"entry_id": 262, "topic_key": "conditional_sentences"},
    {"entry_id": 263, "topic_key": "conditional_sentences"},
    {"entry_id": 264, "topic_key": "conditional_sentences"},
    {"entry_id": 265, "topic_key": "conditional_sentences"},
    {"entry_id": 413, "topic_key": "passive_voice"},
    {"entry_id": 414, "topic_key": "passive_voice"},
    {"entry_id": 415, "topic_key": "passive_voice"},
    {"entry_id": 416, "topic_key": "passive_voice"},
    {"entry_id": 417, "topic_key": "passive_voice"},
    {"entry_id": 418, "topic_key": "passive_voice"},
    {"entry_id": 419, "topic_key": "passive_voice"},
    {"entry_id": 420, "topic_key": "passive_voice"},
    {"entry_id": 455, "topic_key": "perfect"},
    {"entry_id": 456, "topic_key": "perfect"},
    {"entry_id": 457, "topic_key": "perfect"},
    {"entry_id": 458, "topic_key": "perfect"},
    {"entry_id": 459, "topic_key": "perfect"},
    {"entry_id": 460, "topic_key": "perfect"},
    {"entry_id": 464, "topic_key": "progressive"},
    {"entry_id": 465, "topic_key": "progressive"},
    {"entry_id": 466, "topic_key": "progressive"},
    {"entry_id": 487, "topic_key": "question_tags"},
    {"entry_id": 488, "topic_key": "question_tags"},
    {"entry_id": 494, "topic_key": "relative_clauses"},
    {"entry_id": 495, "topic_key": "relative_clauses"},
    {"entry_id": 496, "topic_key": "relative_clauses"},
    {"entry_id": 497, "topic_key": "relative_clauses"},
    {"entry_id": 498, "topic_key": "relative_clauses"},
    {"entry_id": 587, "topic_key": "existential"},
)

ENTRY_HEADER_RE = re.compile(r"^(?P<entry_id>\d{2,3})\s+(?P<title>.+?)\s*$")
SUBSECTION_RE = re.compile(r"^(?P<num>\d{1,2})\s+(?P<title>.+?)\s*$")
PAGE_LINE_RE = re.compile(r"^page\s+[xivlcdm0-9]+$", re.IGNORECASE)
CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
WS_RE = re.compile(r"\s+")


def _norm(value: Any) -> str:
    value = CONTROL_RE.sub(" ", str(value or ""))
    return WS_RE.sub(" ", value.strip())


def _load_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [_norm(line) for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _collect_entry_ranges(lines: list[str]) -> dict[int, tuple[int, int, str]]:
    starts: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        match = ENTRY_HEADER_RE.match(line)
        if not match:
            continue
        entry_id = int(match.group("entry_id"))
        title = _norm(match.group("title"))
        starts.append((idx, entry_id, title))
    starts.sort()
    ranges: dict[int, tuple[int, int, str]] = {}
    for pos, (start_idx, entry_id, title) in enumerate(starts):
        end_idx = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        ranges[entry_id] = (start_idx, end_idx, title)
    return ranges


def _clean_entry_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not line:
            continue
        if PAGE_LINE_RE.match(line):
            continue
        if line == ">>" or line == ">" or line == "«" or line == "»":
            continue
        if line.isdigit():
            continue
        lowered = line.lower()
        if lowered.startswith("for more about ") or lowered.startswith("for more details"):
            continue
        if lowered.startswith("for details of ") or lowered.startswith("for the difference between "):
            continue
        out.append(line)
    return out


def _window_block_lines(
    *,
    body_lines: list[str],
    max_chars: int,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current_subhead = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = "\n".join(line for line in buffer if line).strip()
        if len(text) > 40:
            chunks.append({"text": text, "subheading": current_subhead})
        buffer = []
        if current_subhead:
            buffer.append(current_subhead)

    for line in body_lines:
        sub = SUBSECTION_RE.match(line)
        if sub:
            if len("\n".join(buffer)) > 120:
                flush()
            current_subhead = _norm(f"{sub.group('num')} {sub.group('title')}")
            buffer.append(current_subhead)
            continue
        projected = "\n".join(buffer + [line])
        if len(projected) > max_chars and len(buffer) > 2:
            flush()
        buffer.append(line)

    flush()
    return chunks


def build_rows(
    *,
    text_path: str,
    source_path: str,
    max_chars: int = 1600,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lines = _load_lines(Path(text_path))
    ranges = _collect_entry_ranges(lines)
    rows: list[dict[str, Any]] = []
    missing_entries: list[int] = []
    topic_counter: Counter[str] = Counter()
    entry_counter: Counter[int] = Counter()

    for spec in ENTRY_MANIFEST:
        entry_id = int(spec["entry_id"])
        topic_key = str(spec["topic_key"])
        if entry_id not in ranges:
            missing_entries.append(entry_id)
            continue
        start_idx, end_idx, title = ranges[entry_id]
        block_lines = _clean_entry_lines(lines[start_idx + 1 : end_idx])
        heading = _norm(f"{entry_id} {title}")
        chunks = _window_block_lines(body_lines=block_lines, max_chars=max_chars)
        for chunk_idx, chunk in enumerate(chunks, start=1):
            rows.append(
                {
                    "source_path": source_path,
                    "row_type": "oxford_peu_entry_window",
                    "source_book": "oxford_practical_english_usage_2005",
                    "heading": heading,
                    "entry_id": entry_id,
                    "topic_key": topic_key,
                    "window_index": chunk_idx,
                    "subheading": chunk.get("subheading") or "",
                    "text": chunk["text"],
                }
            )
            topic_counter[topic_key] += 1
            entry_counter[entry_id] += 1

    report = {
        "pipeline_version": "oxford_peu_sentence_rows_v1",
        "text_path": str(Path(text_path).resolve()),
        "source_path": source_path,
        "rows_total": len(rows),
        "topic_counts": dict(sorted(topic_counter.items())),
        "entry_counts": dict(sorted(entry_counter.items())),
        "missing_entries": sorted(missing_entries),
        "max_chars": max_chars,
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
    parser = argparse.ArgumentParser(description="Build Oxford PEU sentence-oriented handbook rows.")
    parser.add_argument("--text-path", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--max-chars", type=int, default=1600)
    args = parser.parse_args()

    rows, report = build_rows(
        text_path=args.text_path,
        source_path=args.source_path,
        max_chars=args.max_chars,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
