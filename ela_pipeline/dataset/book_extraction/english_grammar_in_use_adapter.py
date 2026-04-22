"""Book-specific unit-based adapter for English Grammar in Use (5th ed.)."""

from __future__ import annotations

import re
from typing import Iterable

from .engine import BookTextPayload
from .handbook_adapter import HandbookRow


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_UNIT_NUMBER_LINE_RE = re.compile(r"^\d{1,3}$")
_UNIT_COMBINED_RE = re.compile(r"^(?P<number>\d{1,3})\s+(?P<title>.+)$")
_SECTION_MARK_RE = re.compile(r"^[A-H]$")


def _norm(value: object) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def _normalize_lines(text: str) -> list[str]:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw_text.split("\n")]


def _infer_topic_key(title: str) -> str:
    lowered = _norm(title).lower()
    if "question tags" in lowered:
        return "question_tags"
    if "relative clauses" in lowered:
        return "relative_clauses"
    if lowered.startswith("passive") or " passive " in f" {lowered} ":
        return "passive_voice"
    if lowered.startswith("if ") or lowered.startswith("wish") or " if " in f" {lowered} ":
        return "conditional_sentences"
    if "present perfect" in lowered or "past perfect" in lowered or "perfect continuous" in lowered:
        return "perfect"
    if "present continuous" in lowered or "past continuous" in lowered or "progressive" in lowered:
        return "progressive"
    if lowered.startswith("can") or lowered.startswith("could") or lowered.startswith("must") or lowered.startswith("may") or lowered.startswith("might") or lowered.startswith("should") or lowered.startswith("would"):
        return "modal"
    if lowered.startswith("preposition") or "preposition" in lowered:
        return "prepositions"
    if "noun phrase" in lowered:
        return "noun_phrase"
    if "verb phrase" in lowered:
        return "verb_phrase"
    return ""


def _parse_unit_header(lines: list[str], unit_idx: int) -> tuple[str, str, int] | None:
    probe: list[tuple[int, str]] = []
    for idx in range(unit_idx + 1, min(len(lines), unit_idx + 8)):
        if lines[idx]:
            probe.append((idx, lines[idx]))
    if not probe:
        return None
    first_idx, first_text = probe[0]
    combined = _UNIT_COMBINED_RE.match(first_text)
    if combined:
        return combined.group("number"), _norm(combined.group("title")), first_idx
    if len(probe) >= 2 and _UNIT_NUMBER_LINE_RE.fullmatch(probe[1][1]):
        return probe[1][1], first_text, probe[1][0]
    return None


def _collect_until(lines: list[str], start_idx: int) -> tuple[list[str], int]:
    chunk: list[str] = []
    idx = start_idx
    while idx < len(lines):
        current = lines[idx]
        if current == "Unit":
            break
        if current == "Exercises":
            break
        chunk.append(current)
        idx += 1
    return chunk, idx


def _paragraphs(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    block: list[str] = []
    for line in lines:
        if line:
            block.append(line)
            continue
        if block:
            out.append(_norm(" ".join(block)))
            block = []
    if block:
        out.append(_norm(" ".join(block)))
    return out


def extract_english_grammar_in_use_rows(payload: BookTextPayload) -> list[HandbookRow]:
    lines = _normalize_lines(payload.text)
    rows: list[HandbookRow] = []
    idx = 0
    while idx < len(lines):
        if lines[idx] != "Unit":
            idx += 1
            continue
        parsed = _parse_unit_header(lines, idx)
        if parsed is None:
            idx += 1
            continue
        unit_number, unit_title, header_end_idx = parsed
        topic_key = _infer_topic_key(unit_title)
        body_lines, next_idx = _collect_until(lines, header_end_idx + 1)
        idx = max(idx + 1, next_idx)
        if not topic_key:
            continue
        paragraphs = _paragraphs(body_lines)
        if not paragraphs:
            continue
        current_section = ""
        section_lines: list[str] = []

        def flush_section() -> None:
            nonlocal section_lines
            if not section_lines:
                return
            text = _norm(" ".join(section_lines))
            if text:
                rows.append(
                    HandbookRow(
                        source_path=payload.source_path,
                        row_type="egu_unit_section",
                        topic_key=topic_key,
                        anchor=f"unit_{unit_number}",
                        heading=f"Unit {unit_number} {unit_title}",
                        text=text,
                        start_line=header_end_idx + 1,
                        end_line=next_idx,
                    )
                )
            section_lines = []

        for para in paragraphs:
            if _SECTION_MARK_RE.fullmatch(para):
                flush_section()
                current_section = para
                continue
            if not section_lines:
                section_lines.append(unit_title)
                if current_section:
                    section_lines.append(current_section)
            section_lines.append(para)
        flush_section()
    return rows
