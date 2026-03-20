"""Generic front-matter rulebook adapter for dictionary/reference grammar books."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .engine import BookTextPayload


_CONTROL_GLYPH_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WHITESPACE_RE = re.compile(r"\s+")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_ROMAN_PAGE_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
_ENTRY_EXAMPLE_RE = re.compile(r"\b(e\.g\.|for example|example:|examples:)\b", re.IGNORECASE)
_ENTRY_HEAD_SPLIT_RE = re.compile(r"\s+(?:See\b|see\b|1\.)")
_INLINE_HEAD_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9'/.&, -]*(?: [A-Za-z][A-Za-z0-9'/.&, -]*){0,4})(?: \([^)]{1,48}\))?\s+(?=(?:[A-Z*(]|\d+\.))"
)
_FALSE_HEAD_PREFIXES = (
    "see also ",
    "compare ",
    "contrasted with ",
    "also called ",
    "the term ",
)
_FALSE_HEAD_FIRST_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "if",
    "in",
    "of",
    "or",
    "some",
    "the",
    "to",
    "typically",
    "when",
    "with",
}
_FALSE_HEAD_LAST_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "by",
    "for",
    "in",
    "of",
    "or",
    "the",
    "to",
    "with",
}
_FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "if",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(slots=True)
class RulebookAdapterConfig:
    name: str
    source_markers: tuple[str, ...]
    front_matter_sections: tuple[tuple[str, str], ...]
    body_start_heading: str


@dataclass(slots=True)
class RulebookRow:
    source_path: str
    row_type: str
    heading: str
    text: str
    entry_head: str = ""
    example_marker_count: int = 0
    line_start: int = 0
    line_end: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(value: Any) -> str:
    value = _CONTROL_GLYPH_RE.sub(" ", str(value or ""))
    return _WHITESPACE_RE.sub(" ", value.strip())


def supports_payload(payload: BookTextPayload, config: RulebookAdapterConfig) -> bool:
    lowered = f"{payload.source_path} {payload.metadata}".lower()
    return any(marker in lowered for marker in config.source_markers)


def _normalize_lines(text: str) -> list[str]:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw_text.split("\n")]


def _paragraphs(lines: list[str]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    start = -1
    chunk: list[str] = []
    for idx, line in enumerate(lines):
        if line:
            if start < 0:
                start = idx
            chunk.append(line)
            continue
        if chunk:
            out.append((start, idx - 1, _norm(" ".join(chunk))))
            start = -1
            chunk = []
    if chunk:
        out.append((start, len(lines) - 1, _norm(" ".join(chunk))))
    return out


def _paragraphs_in_range(lines: list[str], start_line: int, end_line: int) -> list[tuple[int, int, str]]:
    return _paragraphs(lines[start_line:end_line])


def _find_section_index(paragraphs: list[tuple[int, int, str]], target: str) -> int:
    target = _norm(target).lower()
    for idx, (_, _, text) in enumerate(paragraphs):
        if text.lower() == target:
            return idx
    return -1


def _find_line_index(lines: list[str], target: str) -> int:
    target = _norm(target).lower()
    for idx, text in enumerate(lines):
        if text.lower() == target:
            return idx
    return -1


def _next_nonblank_line(lines: list[str], start_idx: int) -> str:
    for idx in range(start_idx + 1, len(lines)):
        text = _norm(lines[idx])
        if text:
            return text
    return ""


def _find_best_line_index(
    lines: list[str],
    target: str,
    *,
    start_after: int = -1,
    protected_sections: set[str] | None = None,
) -> int:
    target = _norm(target).lower()
    protected_sections = {item.lower() for item in (protected_sections or set())}
    for idx in range(start_after + 1, len(lines)):
        text = _norm(lines[idx]).lower()
        if text != target:
            continue
        next_line = _next_nonblank_line(lines, idx)
        next_lower = next_line.lower()
        if not next_line:
            continue
        if _PAGE_NUMBER_RE.fullmatch(next_line) or _ROMAN_PAGE_RE.fullmatch(next_line):
            continue
        if next_lower in protected_sections:
            continue
        return idx
    return -1


def _is_letter_heading(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]", text))


def _looks_plausible_head_candidate(text: str) -> bool:
    text = _norm(text)
    if not text:
        return False
    lowered = text.lower()
    if any(lowered.startswith(prefix) for prefix in _FALSE_HEAD_PREFIXES):
        return False
    words = [token.strip("()[]{}.,;:") for token in text.split() if token.strip("()[]{}.,;:")]
    if not words:
        return False
    first_word = words[0].lower()
    last_word = words[-1].lower()
    if first_word in _FALSE_HEAD_FIRST_WORDS or last_word in _FALSE_HEAD_LAST_WORDS:
        return False
    if len(words) > 1 and sum(1 for token in words if token.lower() in _FUNCTION_WORDS) >= len(words) - 1:
        return False
    return True


def _is_probable_headword(text: str, config: RulebookAdapterConfig) -> bool:
    text = _norm(text)
    if not text:
        return False
    if _PAGE_NUMBER_RE.fullmatch(text) or _ROMAN_PAGE_RE.fullmatch(text):
        return False
    if _is_letter_heading(text):
        return False
    if len(text) > 90:
        return False
    if text.endswith((".", ";", ":")):
        return False
    words = text.split()
    if not (1 <= len(words) <= 8):
        return False
    if words[0][:1].isdigit():
        return False
    protected = {section.lower() for section, _ in config.front_matter_sections}
    protected.add(config.body_start_heading.lower())
    if text.lower() in protected:
        return False
    return _looks_plausible_head_candidate(text)


def _extract_inline_entry_head(text: str) -> str:
    text = _norm(text)
    if not text:
        return ""
    match = _INLINE_HEAD_RE.match(text)
    if not match:
        return ""
    candidate = _norm(match.group(1))
    if not _looks_plausible_head_candidate(candidate):
        return ""
    return candidate


def _extract_entry_head(text: str, fallback: str) -> str:
    inline_head = _extract_inline_entry_head(text)
    if inline_head:
        return inline_head
    match = _ENTRY_HEAD_SPLIT_RE.search(text)
    if match:
        candidate = _norm(text[: match.start()])
        if candidate:
            return candidate
    inline = _INLINE_HEAD_RE.match(text)
    if inline:
        candidate = _norm(inline.group(1))
        if candidate:
            return candidate
    words = text.split()
    if len(words) >= 1 and len(words[0]) <= 40:
        return fallback or words[0]
    return fallback


def _strip_entry_head_prefix(text: str, entry_head: str) -> str:
    text = _norm(text)
    entry_head = _norm(entry_head)
    if not text or not entry_head:
        return text
    if text == entry_head:
        return ""
    lowered = text.lower()
    head_lower = entry_head.lower()
    if lowered.startswith(f"{head_lower} "):
        return _norm(text[len(entry_head) :])
    return text


def _slice_section(
    lines: list[str],
    *,
    section_name: str,
    row_type: str,
    start_line: int,
    end_line: int,
) -> list[RulebookRow]:
    if start_line < 0:
        return []
    paragraphs = _paragraphs_in_range(lines, start_line + 1, end_line)
    rows: list[RulebookRow] = []
    for rel_start, rel_end, text in paragraphs:
        if not text or _is_letter_heading(text):
            continue
        if text.lower() == section_name.lower():
            continue
        if _PAGE_NUMBER_RE.fullmatch(text) or _ROMAN_PAGE_RE.fullmatch(text):
            continue
        rows.append(
            RulebookRow(
                source_path="",
                row_type=row_type,
                heading=section_name,
                text=text,
                example_marker_count=len(_ENTRY_EXAMPLE_RE.findall(text)),
                line_start=start_line + rel_start + 1,
                line_end=start_line + rel_end + 1,
            )
        )
    return rows


def _extract_entry_rows(
    lines: list[str],
    *,
    config: RulebookAdapterConfig,
    source_path: str,
) -> list[RulebookRow]:
    last_front_matter = -1
    for section_name, _ in config.front_matter_sections:
        section_line = _find_best_line_index(
            lines,
            section_name,
            start_after=last_front_matter,
            protected_sections={name for name, _ in config.front_matter_sections} | {config.body_start_heading},
        )
        if section_line > last_front_matter:
            last_front_matter = section_line
    start_line = _find_best_line_index(
        lines,
        config.body_start_heading,
        start_after=last_front_matter,
        protected_sections={name for name, _ in config.front_matter_sections} | {config.body_start_heading},
    )
    if start_line < 0:
        return []
    rows: list[RulebookRow] = []
    current_head = ""
    current_parts: list[str] = []
    current_start = 0
    current_end = 0

    def flush() -> None:
        nonlocal current_head, current_parts, current_start, current_end
        if not current_head and not current_parts:
            return
        parts = [_norm(part) for part in current_parts if _norm(part)]
        if parts and current_head:
            parts[0] = _strip_entry_head_prefix(parts[0], current_head)
        text = _norm(" ".join(part for part in parts if part))
        if text:
            rows.append(
                RulebookRow(
                    source_path=source_path,
                    row_type="dictionary_entry",
                    heading=current_head or "",
                    entry_head=current_head or "",
                    text=text,
                    example_marker_count=len(_ENTRY_EXAMPLE_RE.findall(text)),
                    line_start=current_start,
                    line_end=current_end,
                )
            )
        current_head = ""
        current_parts = []
        current_start = 0
        current_end = 0

    for absolute_index in range(start_line + 1, len(lines)):
        text = _norm(lines[absolute_index])
        if not text:
            continue
        if _PAGE_NUMBER_RE.fullmatch(text) or _ROMAN_PAGE_RE.fullmatch(text):
            continue
        if _is_letter_heading(text):
            continue
        inline_head = _extract_inline_entry_head(text)
        if inline_head:
            flush()
            current_head = inline_head
            current_parts = [text]
            current_start = absolute_index + 1
            current_end = absolute_index + 1
            continue
        if _is_probable_headword(text, config):
            flush()
            current_head = text
            current_parts = []
            current_start = absolute_index + 1
            current_end = absolute_index + 1
            continue
        if not current_head:
            continue
        current_parts.append(text)
        current_end = absolute_index + 1
    flush()
    return rows


def extract_rulebook_rows(payload: BookTextPayload, config: RulebookAdapterConfig) -> list[RulebookRow]:
    if not supports_payload(payload, config):
        return []
    lines = _normalize_lines(payload.text)
    rows: list[RulebookRow] = []
    protected_sections = {name for name, _ in config.front_matter_sections} | {config.body_start_heading}
    section_positions: list[tuple[str, str, int]] = []
    last_position = -1
    for section_name, row_type in config.front_matter_sections:
        line_index = _find_best_line_index(
            lines,
            section_name,
            start_after=last_position,
            protected_sections=protected_sections,
        )
        section_positions.append((section_name, row_type, line_index))
        if line_index > last_position:
            last_position = line_index
    body_start = _find_best_line_index(
        lines,
        config.body_start_heading,
        start_after=last_position,
        protected_sections=protected_sections,
    )

    for idx, (section_name, row_type, start_line) in enumerate(section_positions):
        if start_line < 0:
            continue
        end_line = body_start if body_start > start_line else len(lines)
        for _, _, next_start in section_positions[idx + 1 :]:
            if next_start > start_line:
                end_line = min(end_line, next_start)
                break
        rows.extend(
            _slice_section(
                lines,
                section_name=section_name,
                row_type=row_type,
                start_line=start_line,
                end_line=end_line,
            )
        )
    rows.extend(_extract_entry_rows(lines, config=config, source_path=payload.source_path))

    for row in rows:
        row.source_path = payload.source_path
    return rows
