"""Book-specific adapter for English Grammar Today (A-Z article reference grammar)."""

from __future__ import annotations

import re
from typing import Iterable

from .engine import BookTextPayload
from .handbook_adapter import HandbookRow


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_ARTICLE_HEADING_RE = re.compile(r"^(?P<title>[A-Z][A-Za-z/&(),'\- ]{1,120}) (?P<page>\d{1,3}[a-z]?)$")
_SUBSECTION_RE = re.compile(r"^\d{1,3}[a-z]$")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_ROMAN_PAGE_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
_FRONT_MATTER_HEADINGS = (
    ("Introduction", "introduction_rule"),
    ("Organisation", "organisation_rule"),
    ("The Cambridge International Corpus", "corpus_rule"),
    ("Typical errors", "typical_errors_rule"),
    ("Examples in context", "examples_in_context_rule"),
    ("Standard and non-standard", "standard_nonstandard_rule"),
    ("Correct English", "correct_english_rule"),
    ("Symbols used in English Grammar Today", "symbols_rule"),
)
_TOPIC_HEADINGS: dict[str, tuple[str, ...]] = {
    "question_tags": ("question tags", "tags"),
    "relative_clauses": ("relative clauses",),
    "prepositional_phrases": ("prepositional phrases", "prepositional phrases after verbs"),
    "prepositions": ("prepositions", "prepositions: uses", "prepositions or conjunctions?", "prepositions or adverbs?"),
    "passive_voice": (
        "get passive",
        "passive: active and passive",
        "passive: forms",
        "passive: uses",
        "passive: other forms",
        "passives with an agent",
        "passives without an agent",
        "passive: typical errors",
    ),
    "that_clause": ("that-clauses",),
    "wh_clause": ("wh-cleft sentences", "wh-questions", "wh-clause as direct object", "wh-clause + to-infinitive"),
    "conditional_sentences": (
        "conditionals",
        "conditionals: imagined situations",
        "conditionals in speaking",
        "if",
        "if and politeness",
        "if and whether",
        "if only",
        "unless",
    ),
    "modal": (
        "modal expressions",
        "modal verbs",
        "modal words and expressions",
        "modal verbs and adverbs",
        "modal meaning",
        "modal verbs in past, present and future time",
        "modality",
        "will and shall",
        "will or shall",
        "will and shall: uses",
        "will and shall: form",
        "would",
        "would or will?",
        "would like in offers and requests",
        "would prefer",
        "would rather",
        "would sooner, would just as soon",
        "can",
        "could",
        "may",
        "might",
        "must",
        "should",
    ),
    "perfect": ("future perfect simple: use",),
    "progressive": (),
}
_TOPIC_PRIORITY = (
    "question_tags",
    "relative_clauses",
    "prepositional_phrases",
    "prepositions",
    "passive_voice",
    "that_clause",
    "wh_clause",
    "conditional_sentences",
    "perfect",
    "progressive",
    "modal",
)
_IGNORE_BLOCK_PREFIXES = (
    "> ",
    "— 613 Glossary",
    "English Grammar Today",
    "Additional CD-ROM sections",
    "The following entries are on the CD-ROM:",
)


def _norm(value: object) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def _normalize_lines(text: str) -> list[str]:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw_text.split("\n")]


def _page_line_groups(text: str) -> list[list[tuple[int, str]]]:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    pages = raw_text.split("\f")
    groups: list[list[tuple[int, str]]] = []
    line_no = 0
    for page in pages:
        page_rows: list[tuple[int, str]] = []
        for raw_line in page.split("\n"):
            line_no += 1
            page_rows.append((line_no, _norm(raw_line)))
        groups.append(page_rows)
    return groups


def _find_first_line(lines: list[str], target: str, *, start_after: int = -1) -> int:
    needle = _norm(target).lower()
    for idx in range(max(0, start_after + 1), len(lines)):
        if lines[idx].lower() == needle:
            return idx
    return -1


def _article_heading_match(text: str) -> re.Match[str] | None:
    text = _norm(text)
    if not text:
        return None
    match = _ARTICLE_HEADING_RE.fullmatch(text)
    if not match:
        return None
    title = _norm(match.group("title"))
    if len(title.split()) > 16:
        return None
    if title.lower() in {"introduction", "table of irregular verbs", "glossary", "index"}:
        return None
    return match


def _infer_topic_key(heading: str) -> str:
    lowered = _norm(heading).lower()
    for topic_key in _TOPIC_PRIORITY:
        for pattern in _TOPIC_HEADINGS[topic_key]:
            if lowered == pattern or lowered.startswith(f"{pattern} "):
                return topic_key
    return ""


def _paragraphs(lines: list[str], start: int, end: int) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    para_start = -1
    chunk: list[str] = []
    for idx in range(start, min(end, len(lines))):
        line = lines[idx]
        if line:
            if para_start < 0:
                para_start = idx
            chunk.append(line)
            continue
        if chunk:
            out.append((para_start, idx - 1, _norm(" ".join(chunk))))
            para_start = -1
            chunk = []
    if chunk:
        out.append((para_start, min(end, len(lines)) - 1, _norm(" ".join(chunk))))
    return out


def _is_headingish(text: str) -> bool:
    text = _norm(text)
    if not text:
        return False
    if _SUBSECTION_RE.fullmatch(text):
        return True
    if _PAGE_NUMBER_RE.fullmatch(text) or _ROMAN_PAGE_RE.fullmatch(text):
        return True
    if any(text.startswith(prefix) for prefix in _IGNORE_BLOCK_PREFIXES):
        return True
    if _article_heading_match(text):
        return True
    if len(text) > 120:
        return False
    if text.endswith((".", "!", ";")):
        return False
    words = text.split()
    if not (1 <= len(words) <= 14):
        return False
    if sum(ch.isdigit() for ch in text) > 4:
        return False
    if any(mark in text for mark in (". ", "! ", "; ")):
        return False
    if text.endswith("?") and len(words) <= 12:
        return True
    return text.istitle() or ":" in text


def _sanitize_article_paragraphs(paragraphs: Iterable[tuple[int, int, str]], heading: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    heading_lower = _norm(heading).lower()
    for start, end, text in paragraphs:
        compact = _norm(text)
        if not compact:
            continue
        lowered = compact.lower()
        if lowered == heading_lower:
            continue
        if any(lowered.startswith(prefix.lower()) for prefix in _IGNORE_BLOCK_PREFIXES):
            continue
        if _PAGE_NUMBER_RE.fullmatch(compact) or _ROMAN_PAGE_RE.fullmatch(compact):
            continue
        out.append((start, end, compact))
    return out


def _make_windows(
    *,
    source_path: str,
    heading: str,
    topic_key: str,
    paragraphs: list[tuple[int, int, str]],
) -> list[HandbookRow]:
    rows: list[HandbookRow] = []
    block: list[tuple[int, int, str]] = []
    block_start = 0
    block_end = 0
    last_subheading = ""

    def flush() -> None:
        nonlocal block, block_start, block_end
        if not block:
            return
        text_parts: list[str] = []
        if last_subheading:
            text_parts.append(last_subheading)
        text_parts.extend(text for _, _, text in block)
        compact = _norm("\n\n".join(text_parts))
        if compact and len(compact) <= 2400:
            rows.append(
                HandbookRow(
                    source_path=source_path,
                    row_type="egt_article_window",
                    topic_key=topic_key,
                    anchor=heading,
                    heading=heading,
                    text=compact,
                    start_line=block_start + 1,
                    end_line=block_end + 1,
                )
            )
        block = []

    for start, end, text in paragraphs:
        if _is_headingish(text):
            flush()
            if not (_SUBSECTION_RE.fullmatch(text) or _PAGE_NUMBER_RE.fullmatch(text) or _ROMAN_PAGE_RE.fullmatch(text)):
                last_subheading = text
            continue
        if not block:
            block_start = start
            block_end = end
            block.append((start, end, text))
            continue
        candidate = _norm("\n\n".join([segment for _, _, segment in block] + [text]))
        if len(candidate) > 1800:
            flush()
            block_start = start
            block_end = end
            block.append((start, end, text))
            continue
        block.append((start, end, text))
        block_end = end
    flush()
    return rows


def extract_english_grammar_today_rows(payload: BookTextPayload) -> list[HandbookRow]:
    lines = _normalize_lines(payload.text)
    body_start = _find_first_line(lines, "A/an and the 1")
    if body_start < 0:
        return []
    body_end = _find_first_line(lines, "Glossary", start_after=body_start + 1)
    if body_end < 0:
        body_end = len(lines)

    rows: list[HandbookRow] = []
    for section_name, row_type in _FRONT_MATTER_HEADINGS:
        section_start = _find_first_line(lines, section_name)
        if section_start < 0 or section_start >= body_start:
            continue
        next_points = [body_start]
        for other_name, _ in _FRONT_MATTER_HEADINGS:
            if other_name == section_name:
                continue
            idx = _find_first_line(lines, other_name, start_after=section_start)
            if idx > section_start:
                next_points.append(idx)
        cutoff = min(next_points)
        paragraphs = _paragraphs(lines, section_start + 1, cutoff)
        for start, end, text in paragraphs:
            if not text:
                continue
            rows.append(
                HandbookRow(
                    source_path=payload.source_path,
                    row_type=row_type,
                    topic_key="",
                    anchor=section_name,
                    heading=section_name,
                    text=text,
                    start_line=start + 1,
                    end_line=end + 1,
                )
            )

    pages = _page_line_groups(payload.text)
    body_start_page = -1
    body_end_page = len(pages)
    for page_index, page_rows in enumerate(pages):
        nonblank = [(line_no, text) for line_no, text in page_rows if text]
        if not nonblank:
            continue
        top_lines = [text for _, text in nonblank[:5]]
        if body_start_page < 0 and any(text == "A/an and the 1" for text in top_lines):
            body_start_page = page_index
            continue
        if body_start_page >= 0 and top_lines[0] == "Glossary":
            body_end_page = page_index
            break

    article_buffers: list[tuple[str, str, list[tuple[int, str]]]] = []
    current_heading = ""
    current_topic = ""
    current_rows: list[tuple[int, str]] = []

    def flush_article() -> None:
        nonlocal current_heading, current_topic, current_rows
        if current_heading and current_rows:
            article_buffers.append((current_heading, current_topic, current_rows[:]))
        current_heading = ""
        current_topic = ""
        current_rows = []

    for page_index in range(max(0, body_start_page), min(body_end_page, len(pages))):
        page_rows = pages[page_index]
        nonblank = [(line_no, text) for line_no, text in page_rows if text]
        if not nonblank:
            continue
        heading = ""
        heading_line_no = -1
        for line_no, text in nonblank[:5]:
            match = _article_heading_match(text)
            if match:
                heading = _norm(match.group("title"))
                heading_line_no = line_no
                break
        if heading:
            topic_key = _infer_topic_key(heading)
            if heading != current_heading:
                flush_article()
                current_heading = heading
                current_topic = topic_key
        if not current_heading:
            continue
        skip_heading = True
        for line_no, text in page_rows:
            if skip_heading and heading_line_no > 0 and line_no == heading_line_no:
                skip_heading = False
                continue
            if heading_line_no > 0 and line_no < heading_line_no:
                continue
            if text in {"English Grammar Today", "— 613 Glossary"}:
                continue
            if _PAGE_NUMBER_RE.fullmatch(text) or _ROMAN_PAGE_RE.fullmatch(text):
                continue
            current_rows.append((line_no, text))
        current_rows.append((current_rows[-1][0] if current_rows else 0, ""))
    flush_article()

    for heading, topic_key, article_rows in article_buffers:
        article_lines = [text for _, text in article_rows]
        line_offsets = [line_no for line_no, _ in article_rows]
        paragraphs = _paragraphs(article_lines, 0, len(article_lines))
        adjusted_paragraphs = [
            (
                line_offsets[start] if start < len(line_offsets) else 0,
                line_offsets[end] if end < len(line_offsets) else 0,
                text,
            )
            for start, end, text in paragraphs
        ]
        adjusted_paragraphs = _sanitize_article_paragraphs(adjusted_paragraphs, heading)
        rows.extend(
            _make_windows(
                source_path=payload.source_path,
                heading=heading,
                topic_key=topic_key,
                paragraphs=adjusted_paragraphs,
            )
        )
    return rows
