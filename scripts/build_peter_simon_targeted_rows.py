#!/usr/bin/env python3
"""Extract targeted sentence-learning rows from Peter Simon's Grammaring Guide."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


WS_RE = re.compile(r"\s+")

SECTION_SPECS = (
    {"topic_key": "progressive", "heading": "Present continuous for actions in progress at the time of speaking", "min_line": 2400},
    {"topic_key": "progressive", "heading": "Present continuous for gradual development", "min_line": 2400},
    {"topic_key": "progressive", "heading": "Present continuous for frequently repeated actions in the present", "min_line": 2400},
    {"topic_key": "progressive", "heading": "Present continuous for temporary habitual actions in the present", "min_line": 2400},
    {"topic_key": "progressive", "heading": "Present continuous for habitual actions in the present", "min_line": 2400},
    {"topic_key": "perfect", "heading": "Present perfect for past events", "min_line": 2600},
    {"topic_key": "perfect", "heading": "Present perfect for recent events with a result in the present", "min_line": 2600},
    {"topic_key": "perfect", "heading": "Present perfect with an incomplete period", "min_line": 2600},
    {"topic_key": "perfect", "heading": "Present perfect with FOR and SINCE", "min_line": 2600},
    {"topic_key": "perfect", "heading": "Present perfect with JUST", "min_line": 2600},
    {"topic_key": "perfect", "heading": "Present perfect with YET and ALREADY", "min_line": 2600},
    {"topic_key": "perfect", "heading": "IT'S (BEEN) + DAYS / WEEKS / MONTHS / etc. + SINCE", "min_line": 2600},
    {"topic_key": "perfect", "heading": "Present perfect with quantities", "min_line": 2600},
    {"topic_key": "perfect", "heading": "Present perfect with superlative forms of adjectives", "min_line": 2600},
    {"topic_key": "perfect", "heading": "Present perfect with WHEN", "min_line": 2600},
    {"topic_key": "conditional_sentences", "heading": "Zero conditional", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "First conditional", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Present continuous in the first conditional", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Present perfect in the first conditional", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Imperatives in the first conditional", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Modals in the first conditional", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Second conditional", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Third conditional", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Mixed conditionals", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Less likely conditions", "min_line": 6200},
    {"topic_key": "conditional_sentences", "heading": "Conditionals and inversion", "min_line": 6200},
    {"topic_key": "passive_voice", "heading": "The difference between the active and passive voice", "min_line": 8400},
    {"topic_key": "passive_voice", "heading": "Form: passive voice", "min_line": 8400},
    {"topic_key": "passive_voice", "heading": "Verbs which cannot be used in the passive voice", "min_line": 8400},
    {"topic_key": "passive_voice", "heading": "Ditransitive verbs in the passive voice", "min_line": 8400},
    {"topic_key": "passive_voice", "heading": "The agent with the passive voice", "min_line": 8400},
    {"topic_key": "passive_voice", "heading": "The use of the passive voice", "min_line": 8400},
    {"topic_key": "passive_voice", "heading": "The passive with GET", "min_line": 8400},
    {"topic_key": "passive_voice", "heading": "Passive voice with reporting verbs", "min_line": 8400},
    {"topic_key": "relative_clauses", "heading": "What is a relative clause?", "min_line": 9880},
    {"topic_key": "relative_clauses", "heading": "Defining relative clause", "min_line": 9880},
    {"topic_key": "relative_clauses", "heading": "Non-defining relative clause", "min_line": 9880},
    {"topic_key": "relative_clauses", "heading": "The difference between defining and non-defining relative clauses", "min_line": 9880},
    {"topic_key": "question_tags", "heading": "Subject-auxiliary inversion in question tags", "min_line": 12890},
)

ALL_HEADINGS = {str(spec["heading"]) for spec in SECTION_SPECS}
STOP_PREFIXES = (
    "The Grammaring Guide to English Grammar with Exercises",
    "Related topics:",
    "Revision questions:",
    "Exercises:",
    "Answer key",
    "Quotes:",
)


def _norm(value: Any) -> str:
    return WS_RE.sub(" ", str(value or "").strip())


def _load_lines(path: Path) -> list[str]:
    return [_norm(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()]


def build_rows(*, payload_txt: str, source_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lines = _load_lines(Path(payload_txt))
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for spec in SECTION_SPECS:
        heading = str(spec["heading"])
        topic_key = str(spec["topic_key"])
        min_line = int(spec["min_line"])
        candidates = [idx for idx, line in enumerate(lines) if idx + 1 >= min_line and line == heading]
        if not candidates:
            continue
        best_start = -1
        best_text = ""
        for start_idx in candidates:
            chunk: list[str] = [heading]
            for idx in range(start_idx + 1, len(lines)):
                line = lines[idx]
                if not line:
                    if chunk and chunk[-1] != "":
                        chunk.append("")
                    continue
                if line in ALL_HEADINGS and line != heading:
                    break
                if any(line.startswith(prefix) for prefix in STOP_PREFIXES):
                    break
                chunk.append(line)
                if len("\n".join(chunk)) > 2600:
                    break
            text = "\n".join(item for item in chunk if item is not None).strip()
            if len(text) > len(best_text):
                best_text = text
                best_start = start_idx
        text = best_text
        if len(text) < 120:
            continue
        key = (topic_key, text.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source_path": source_path,
                "row_type": "peter_simon_targeted_snippet",
                "topic_key": topic_key,
                "heading": heading,
                "text": text,
                "start_line": best_start + 1,
            }
        )

    report = {
        "pipeline_version": "peter_simon_targeted_rows_v1",
        "payload_txt": str(Path(payload_txt).resolve()),
        "source_path": source_path,
        "rows_total": len(rows),
        "topic_counts": {
            key: sum(1 for row in rows if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in rows})
        },
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
    parser = argparse.ArgumentParser(description="Extract targeted Peter Simon grammar sections.")
    parser.add_argument("--payload-txt", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows, report = build_rows(payload_txt=args.payload_txt, source_path=args.source_path)
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
