"""Book-specific adapter for English for Everyone: English Grammar Guide Practice Book (2019)."""

from __future__ import annotations

import re

from .engine import BookTextPayload
from .handbook_adapter import HandbookRow


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_PAGE_RE = re.compile(r"^\d{1,3}$")
_ALL_CAPS_RE = re.compile(r"^[A-Z0-9 ,.'\"():/-]+$")

_TOPIC_HEADINGS = {
    "The passive": "passive_voice",
    "The passive in the past": "passive_voice",
    "The passive in the future": "passive_voice",
    "The passive with modals": "passive_voice",
    "Other passive constructions": "passive_voice",
    "Conditional sentences": "conditional_sentences",
    "Other conditional sentences": "conditional_sentences",
    "Conditional sentences review": "conditional_sentences",
    "Question tags": "question_tags",
    "Verb patterns with prepositions": "prepositions",
    "Other prepositions": "prepositions",
    "Dependent prepositions": "prepositions",
    "Modal verbs": "modal",
    "Ability": "modal",
    "Permission, requests, and offers": "modal",
    "Suggestions and advice": "modal",
    "Obligations": "modal",
    "Making deductions": "modal",
    "Possibility": "modal",
    "Defining relative clauses": "relative_clauses",
    "Non-defining relative clauses": "relative_clauses",
    "Other relative structures": "relative_clauses",
}

_MIN_START_LINE = 1300
_MAX_END_LINE = 3750
_MAX_SECTION_LINES = 70


def _norm(value: object) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def _normalize_lines(text: str) -> list[str]:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw_text.split("\n")]


def _looks_heading(line: str) -> bool:
    return line in _TOPIC_HEADINGS


def _keep_line(line: str) -> bool:
    if not line:
        return False
    if _PAGE_RE.fullmatch(line):
        return False
    if line == "Answers":
        return False
    if _ALL_CAPS_RE.fullmatch(line) and len(line.split()) >= 3:
        return False
    return True


def extract_english_for_everyone_practice_rows(payload: BookTextPayload) -> list[HandbookRow]:
    lines = _normalize_lines(payload.text)
    rows: list[HandbookRow] = []
    idx = 0
    while idx < len(lines):
        line_no = idx + 1
        line = lines[idx]
        if line_no < _MIN_START_LINE:
            idx += 1
            continue
        if line_no > _MAX_END_LINE:
            break
        if line == "Answers":
            break
        if not _looks_heading(line):
            idx += 1
            continue

        heading = line
        topic_key = _TOPIC_HEADINGS[heading]
        section_lines = [heading]
        start_line = line_no
        idx += 1
        consumed = 0
        while idx < len(lines):
            current_line_no = idx + 1
            current = lines[idx]
            if current_line_no > _MAX_END_LINE or current == "Answers":
                break
            if consumed >= _MAX_SECTION_LINES:
                break
            if _looks_heading(current):
                break
            if _keep_line(current):
                section_lines.append(current)
            idx += 1
            consumed += 1

        text = _norm(" ".join(section_lines))
        if text and len(re.findall(r"[A-Za-z]{2,}", text)) >= 12:
            rows.append(
                HandbookRow(
                    source_path=payload.source_path,
                    row_type="practice_book_section",
                    topic_key=topic_key,
                    anchor=heading.lower().replace(" ", "_"),
                    heading=heading,
                    text=text,
                    start_line=start_line,
                    end_line=min(idx, _MAX_END_LINE),
                )
            )
    return rows
