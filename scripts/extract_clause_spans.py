#!/usr/bin/env python3
"""Heuristically extract clause-level annotated spans from full-sentence contexts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


RELATIVE_MARKERS = (" who ", " which ", " that ", " where ", " when ", " whose ", " whom ")
SUBORDINATORS = ("if ", "unless ", "although ", "because ", "when ", "while ", "before ", "after ", "since ", "though ", "whereas ", "once ")
PURPOSE_MARKERS = (" so that ", " in order to ", " in order not to ", " so as to ", " so as not to ")
REPORTING_VERBS = (
    "said",
    "asked",
    "told",
    "advised",
    "warned",
    "explained",
    "promised",
    "thought",
)


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clean_span(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" ,"))


def _span_from_conditional(text: str) -> str:
    lowered = text.lower()
    starts = ("if ", "unless ", "if only ")
    for start in starts:
        if lowered.startswith(start):
            if "," in text:
                return _clean_span(text.split(",", 1)[0])
            return _clean_span(text)
    return ""


def _trim_restrictive_relative_tail(span: str) -> str:
    # Trim a likely matrix-clause tail from restrictive relatives such as
    # "who lives next door is a doctor" -> "who lives next door".
    for pattern in (
        r"^(.*?\b(?:who|which|that|whose|whom)\b.*?\b(?:yesterday|today|tomorrow|here|there|abroad|alone|soon|well|late|early|next door))\s+\b(?:is|are|was|were)\b.*$",
        r"^(.*?\b(?:who|which|that|whose|whom)\b(?:\s+\w+){1,6})\s+\b(?:is|are|was|were)\b.*$",
    ):
        m = re.match(pattern, span, flags=re.IGNORECASE)
        if m:
            return _clean_span(m.group(1))
    return span


def _span_from_relative(text: str) -> str:
    lowered = f" {text.lower()} "
    restrictive_markers = {" who ", " which ", " that ", " whose ", " whom "}
    for marker in RELATIVE_MARKERS:
        idx = lowered.find(marker)
        if idx >= 0:
            start = max(0, idx - 1)
            raw = text[start:].strip()
            if raw.startswith(","):
                raw = raw[1:].strip()
            if "," in raw:
                return _clean_span(raw.split(",", 1)[0])
            span = _clean_span(raw)
            if marker in restrictive_markers:
                span = _trim_restrictive_relative_tail(span)
            return span
    return ""


def _span_from_tag(text: str) -> str:
    if "," not in text:
        return ""
    tail = text.rsplit(",", 1)[1].strip()
    if tail.endswith("?"):
        return _clean_span(tail)
    return ""


def _span_from_purpose(text: str) -> str:
    lowered = f" {text.lower()} "
    for marker in PURPOSE_MARKERS:
        idx = lowered.find(marker)
        if idx >= 0:
            return _clean_span(text[idx + 1 :])
    # terminal infinitive purpose
    if " to " in lowered and not lowered.startswith("to "):
        m = re.search(r"\bto\s+[A-Za-z]", text)
        if m:
            start = m.start()
            return _clean_span(text[start:])
    return ""


def _span_from_reported(text: str) -> str:
    lowered = text.lower()
    for verb in REPORTING_VERBS:
        token = f" {verb} "
        idx = lowered.find(token)
        if idx >= 0:
            start = idx + len(token) - 1
            span = text[start:].strip()
            return _clean_span(span)
    return ""


def _span_from_subordinator(text: str) -> str:
    lowered = text.lower()
    for marker in SUBORDINATORS:
        if lowered.startswith(marker):
            if "," in text:
                return _clean_span(text.split(",", 1)[0])
            return _clean_span(text)
        idx = lowered.find(f", {marker}")
        if idx >= 0:
            return _clean_span(text[idx + 2 :])
    return ""


def _extract_clause_span(row: dict[str, Any]) -> tuple[str, str]:
    topic = str(row.get("topic_key") or "")
    note = str(row.get("notation_text") or "").lower()
    text = str(row.get("context_text") or "").strip()

    span = ""
    method = ""

    if topic in {"conditional_sentences", "conditionals", "unreal_time", "wishes"}:
        span = _span_from_conditional(text)
        method = "conditional_clause"
    elif topic in {"question_tags"}:
        span = _span_from_tag(text)
        method = "question_tag"
    elif topic in {"relative_clauses", "relative_pronouns"}:
        span = _span_from_relative(text)
        method = "relative_clause"
    elif topic in {"purpose_clauses"}:
        span = _span_from_purpose(text)
        method = "purpose_clause"
    elif topic in {"reported_speech", "complement_clauses"}:
        span = _span_from_reported(text)
        method = "reported_clause"
    else:
        if "relative clause" in note:
            span = _span_from_relative(text)
            method = "relative_clause_note"
        elif "question tag" in note:
            span = _span_from_tag(text)
            method = "question_tag_note"
        elif any(token in note for token in ("if-clause", "conditional", "unless")):
            span = _span_from_conditional(text)
            method = "conditional_note"
        elif any(token in note for token in ("purpose", "so that", "in order")):
            span = _span_from_purpose(text)
            method = "purpose_note"
        elif any(token in note for token in ("reported", "statement word order", "whether")):
            span = _span_from_reported(text)
            method = "reported_note"
        else:
            span = _span_from_subordinator(text)
            method = "subordinator_fallback"

    if not span:
        return "", ""
    if len(span.split()) < 2:
        return "", ""
    return span, method


def main() -> None:
    parser = argparse.ArgumentParser(description="Heuristically extract clause spans.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    input_path = Path(args.input_jsonl)
    rows = list(_iter_jsonl(input_path))
    out_rows: list[dict[str, Any]] = []
    method_counts: Counter[str] = Counter()
    topic_success: Counter[str] = Counter()
    topic_total: Counter[str] = Counter()

    for row in rows:
        built = dict(row)
        topic = str(built.get("topic_key") or "")
        topic_total[topic] += 1
        span, method = _extract_clause_span(built)
        if span:
            built["annotated_span"] = span
            built["span_status"] = "heuristic_clause_span"
            built["span_method"] = method
            method_counts[method] += 1
            topic_success[topic] += 1
        else:
            built["annotated_span"] = built.get("annotated_span") or ""
            built["span_status"] = built.get("span_status") or "needs_span_extraction"
            built["span_method"] = ""
        out_rows.append(built)

    _write_jsonl(Path(args.output_jsonl), out_rows)
    report = {
        "input_jsonl": str(input_path.resolve()),
        "rows_total": len(rows),
        "rows_with_span": sum(1 for row in out_rows if row.get("span_status") == "heuristic_clause_span"),
        "coverage_ratio": round(
            sum(1 for row in out_rows if row.get("span_status") == "heuristic_clause_span") / len(rows), 4
        )
        if rows
        else 0.0,
        "span_method_counts": dict(sorted(method_counts.items())),
        "topic_success_counts": dict(sorted(topic_success.items())),
        "topic_total_counts": dict(sorted(topic_total.items())),
    }
    _write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
