"""Generic adapter for chapter-style grammar handbooks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .engine import BookTextPayload


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_CITATION_RE = re.compile(r"\([A-Z][A-Za-z-]+(?: and [A-Z][A-Za-z-]+)? \d{4}[a-z]?(?:: [^)]+)?\)")
_EXAMPLE_INLINE_RE = re.compile(r"\([0-9]{1,3}[a-z]?\)|\b[a-z]\.")
_EXAMPLE_SIGNAL_MARKERS = ("e.g.", "for example", "for instance", "example:", "examples:", "illustrated by")
_META_BLOCK_MARKERS = (
    "contents",
    "references",
    "name index",
    "subject index",
    "list of figures and tables",
    "oup corrected proof",
)
_BIO_MARKERS = (
    "professor of",
    "senior lecturer",
    "department of",
    "university of",
    "research interests",
    "she has published",
    "he has published",
    "is the author of",
    "co-authored papers",
    "co-authored",
    "contributors",
)
_EXPLANATION_HINTS = (
    " is ",
    " are ",
    " refers to ",
    " refers ",
    " is used ",
    " are used ",
    " can be ",
    " may be ",
    " functions as ",
    " expresses ",
    " marks ",
    " introduces ",
    " illustrated by ",
    " examples include ",
    " used in ",
    " in the example",
    " in the examples",
)


@dataclass(slots=True)
class HandbookAdapterConfig:
    name: str
    source_markers: tuple[str, ...]
    topic_patterns: dict[str, tuple[str, ...]]
    max_follow_blocks: int = 2
    min_start_line: int = 0
    require_example_signal: bool = False
    max_block_chars: int = 3200
    topic_min_start_lines: dict[str, int] | None = None


@dataclass(slots=True)
class HandbookRow:
    source_path: str
    row_type: str
    topic_key: str
    anchor: str
    heading: str
    text: str
    start_line: int = 0
    end_line: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(value: Any) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def supports_payload(payload: BookTextPayload, config: HandbookAdapterConfig) -> bool:
    lowered = f"{payload.source_path} {payload.metadata}".lower()
    return any(marker in lowered for marker in config.source_markers)


def _normalize_lines(text: str) -> list[str]:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw_text.split("\n")]


def _blocks(lines: list[str]) -> list[tuple[int, int, list[str]]]:
    out: list[tuple[int, int, list[str]]] = []
    start = -1
    chunk: list[str] = []
    for idx, line in enumerate(lines):
        if line:
            if start < 0:
                start = idx
            chunk.append(line)
            continue
        if chunk:
            out.append((start, idx - 1, chunk[:]))
            chunk = []
            start = -1
    if chunk:
        out.append((start, len(lines) - 1, chunk[:]))
    return out


def _is_meta_block(text: str) -> bool:
    lowered = _norm(text).lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in (_META_BLOCK_MARKERS + _BIO_MARKERS))


def _infer_topic_key(text: str, config: HandbookAdapterConfig) -> tuple[str, str]:
    lowered = _norm(text).lower()
    for topic_key, patterns in config.topic_patterns.items():
        for pattern in patterns:
            if pattern in lowered:
                return topic_key, pattern
    return "", ""


def _looks_explanatory(text: str) -> bool:
    lowered = f" {_norm(text).lower()} "
    if not lowered.strip():
        return False
    if _is_meta_block(lowered):
        return False
    if len(re.findall(r"[A-Za-z]{2,}", lowered)) < 10:
        return False
    if _CITATION_RE.findall(lowered) and len(re.findall(r"[A-Za-z]{2,}", lowered)) < 18:
        return False
    return any(hint in lowered for hint in _EXPLANATION_HINTS)


def _looks_example_block(text: str) -> bool:
    text = _norm(text)
    if not text or _is_meta_block(text):
        return False
    words = re.findall(r"[A-Za-z]{2,}", text)
    if len(words) < 3:
        return False
    if ":" in text and any(char in text for char in ('"', "'", "?", "!")):
        return True
    if _EXAMPLE_INLINE_RE.search(text):
        return True
    if text[:1].isupper() and any(mark in text for mark in (".", "?", "!")) and len(words) <= 25:
        return True
    return False


def _has_example_signal(text: str) -> bool:
    lowered = _norm(text).lower()
    return bool(_EXAMPLE_INLINE_RE.search(lowered) or any(marker in lowered for marker in _EXAMPLE_SIGNAL_MARKERS))


def _looks_headingish(text: str) -> bool:
    text = _norm(text)
    if not text or _is_meta_block(text):
        return False
    if len(text) > 120:
        return False
    if text.endswith((".", ";", ":", "?", "!")):
        return False
    words = text.split()
    return 1 <= len(words) <= 12


def extract_handbook_rows(payload: BookTextPayload, config: HandbookAdapterConfig) -> list[HandbookRow]:
    lines = _normalize_lines(payload.text)
    blocks = _blocks(lines)
    rows: list[HandbookRow] = []
    seen: set[tuple[str, str]] = set()
    current_heading = ""

    for index, (start_line, end_line, block_lines) in enumerate(blocks):
        if start_line + 1 < config.min_start_line:
            continue
        block_text = "\n".join(block_lines)
        compact = _norm(block_text)
        if not compact:
            continue
        if _looks_headingish(compact):
            current_heading = compact
        topic_key, anchor = _infer_topic_key(compact, config)
        if not topic_key or not _looks_explanatory(compact):
            continue
        topic_min = int((config.topic_min_start_lines or {}).get(topic_key, 0))
        if start_line + 1 < topic_min:
            continue

        collected = [block_text]
        final_end = end_line
        for next_index in range(index + 1, min(len(blocks), index + 1 + config.max_follow_blocks)):
            next_start, next_end, next_lines = blocks[next_index]
            next_text = "\n".join(next_lines)
            next_compact = _norm(next_text)
            next_topic, _ = _infer_topic_key(next_compact, config)
            if next_topic and next_topic != topic_key:
                break
            if _looks_explanatory(next_compact) and not _looks_example_block(next_compact):
                break
            if not _looks_example_block(next_compact):
                continue
            collected.append(next_text)
            final_end = next_end

        text = "\n\n".join(collected)
        if len(text) > max(500, int(config.max_block_chars)):
            continue
        if config.require_example_signal and not _has_example_signal(text):
            continue
        dedupe_key = (topic_key, _norm(text).lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        rows.append(
            HandbookRow(
                source_path=payload.source_path,
                row_type="handbook_snippet",
                topic_key=topic_key,
                anchor=anchor,
                heading=current_heading,
                text=text,
                start_line=start_line + 1,
                end_line=final_end + 1,
            )
        )
    return rows
