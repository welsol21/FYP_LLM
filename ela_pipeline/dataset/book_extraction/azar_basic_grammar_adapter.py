"""Section-based adapter for Azar Basic English Grammar (2nd ed.)."""

from __future__ import annotations

import re

from .engine import BookTextPayload
from .handbook_adapter import HandbookRow


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_SECTION_RE = re.compile(r"^(?P<section>\d{1,2}-\d{1,2})\s+(?P<title>.+)$")
_SECTION_ONLY_RE = re.compile(r"^\d{1,2}-\d{1,2}$")
_CHAPTER_RE = re.compile(r"^CHAPTER\b", re.IGNORECASE)
_EXERCISE_RE = re.compile(r"^EXERCISE\b", re.IGNORECASE)
_MIN_CONTENT_LINE = 500


def _norm(value: object) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def _normalize_lines(text: str) -> list[str]:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw_text.split("\n")]


def _infer_topic_key(title: str) -> str:
    lowered = _norm(title).lower()
    if "clauses with if" in lowered or "if-clauses" in lowered or "if clause" in lowered:
        return "conditional_sentences"
    if "using can" in lowered or "using could" in lowered or "using should" in lowered or "using must" in lowered:
        return "modal"
    if "modal auxiliaries" in lowered or "summary chart: modal auxiliaries" in lowered:
        return "modal"
    if "prepositions of time" in lowered or "prepositions of location" in lowered or "more about prepositions" in lowered:
        return "prepositions"
    if "present perfect" in lowered or "using have been" in lowered:
        return "perfect"
    return ""


def _looks_headingish(line: str) -> bool:
    text = _norm(line)
    if not text or len(text) > 120:
        return False
    alpha = [ch for ch in text if ch.isalpha()]
    if not alpha:
        return False
    upper_ratio = sum(1 for ch in alpha if ch.isupper()) / len(alpha)
    return upper_ratio >= 0.6 or text.lower().startswith(("using ", "summary", "clauses with if", "if-clause"))


def _finalize_row(
    *,
    rows: list[HandbookRow],
    payload: BookTextPayload,
    topic_key: str,
    heading: str,
    anchor: str,
    start_line: int,
    end_line: int,
    body_lines: list[str],
) -> None:
    if not topic_key or not body_lines:
        return
    text = "\n".join(line for line in body_lines if line)
    compact = _norm(text)
    if not compact:
        return
    rows.append(
        HandbookRow(
            source_path=payload.source_path,
            row_type="azar_section",
            topic_key=topic_key,
            anchor=anchor,
            heading=heading,
            text=text,
            start_line=start_line,
            end_line=end_line,
        )
    )


def extract_azar_basic_grammar_rows(payload: BookTextPayload) -> list[HandbookRow]:
    lines = _normalize_lines(payload.text)
    min_content_line = _MIN_CONTENT_LINE if len(lines) >= _MIN_CONTENT_LINE else 1
    rows: list[HandbookRow] = []
    current_heading = ""
    current_anchor = ""
    current_topic = ""
    current_start = 0
    body_lines: list[str] = []
    capturing = False

    idx = 1
    while idx <= len(lines):
        line = lines[idx - 1]
        if idx < min_content_line:
            idx += 1
            continue
        if not line:
            if capturing and body_lines and body_lines[-1] != "":
                body_lines.append("")
            idx += 1
            continue

        section_match = _SECTION_RE.match(line)
        if section_match:
            if capturing:
                _finalize_row(
                    rows=rows,
                    payload=payload,
                    topic_key=current_topic,
                    heading=current_heading,
                    anchor=current_anchor,
                    start_line=current_start,
                    end_line=idx - 1,
                    body_lines=body_lines,
                )
            current_heading = f"{section_match.group('section')} {section_match.group('title')}"
            current_anchor = section_match.group('title')
            current_topic = _infer_topic_key(section_match.group('title'))
            current_start = idx
            body_lines = []
            capturing = bool(current_topic)
            idx += 1
            continue

        if _SECTION_ONLY_RE.match(line):
            next_line = _norm(lines[idx]) if idx < len(lines) else ""
            next_topic = _infer_topic_key(next_line)
            if next_line and next_topic and _looks_headingish(next_line):
                if capturing:
                    _finalize_row(
                        rows=rows,
                        payload=payload,
                        topic_key=current_topic,
                        heading=current_heading,
                        anchor=current_anchor,
                        start_line=current_start,
                        end_line=idx - 1,
                        body_lines=body_lines,
                    )
                current_heading = f"{line} {next_line}"
                current_anchor = next_line
                current_topic = next_topic
                current_start = idx
                body_lines = []
                capturing = True
                idx += 2
                continue

        inline_topic = _infer_topic_key(line)
        if inline_topic and _looks_headingish(line):
            if capturing:
                _finalize_row(
                    rows=rows,
                    payload=payload,
                    topic_key=current_topic,
                    heading=current_heading,
                    anchor=current_anchor,
                    start_line=current_start,
                    end_line=idx - 1,
                    body_lines=body_lines,
                )
            current_heading = line
            current_anchor = line
            current_topic = inline_topic
            current_start = idx
            body_lines = []
            capturing = True
            idx += 1
            continue

        if _CHAPTER_RE.match(line):
            if capturing:
                _finalize_row(
                    rows=rows,
                    payload=payload,
                    topic_key=current_topic,
                    heading=current_heading,
                    anchor=current_anchor,
                    start_line=current_start,
                    end_line=idx - 1,
                    body_lines=body_lines,
                )
            capturing = False
            current_heading = ""
            current_anchor = ""
            current_topic = ""
            current_start = 0
            body_lines = []
            idx += 1
            continue

        if capturing and _EXERCISE_RE.match(line):
            _finalize_row(
                rows=rows,
                payload=payload,
                topic_key=current_topic,
                heading=current_heading,
                anchor=current_anchor,
                start_line=current_start,
                end_line=idx - 1,
                body_lines=body_lines,
            )
            capturing = False
            current_heading = ""
            current_anchor = ""
            current_topic = ""
            current_start = 0
            body_lines = []
            idx += 1
            continue

        if capturing:
            body_lines.append(line)
        idx += 1

    if capturing:
        _finalize_row(
            rows=rows,
            payload=payload,
            topic_key=current_topic,
            heading=current_heading,
            anchor=current_anchor,
            start_line=current_start,
            end_line=len(lines),
            body_lines=body_lines,
        )

    return rows
