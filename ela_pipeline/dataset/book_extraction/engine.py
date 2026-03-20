"""Universal engine for extracting explanatory snippets from grammar books."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_GRAMMAR_ANCHORS: dict[str, list[str]] = {
    "question_tags": ["question tags", "question tag"],
    "relative_clauses": ["relative clauses", "relative clause"],
    "prepositional_phrases": ["prepositional phrases", "prepositional phrase"],
    "conditional_sentences": ["conditional sentences", "conditional sentence"],
    "questions_and_negatives": ["questions and negatives", "negative interrogative sentences"],
    "passive_voice": ["passive voice", "the passive", "passive"],
    "that_clause": ["that-clause", "that clause"],
    "wh_clause": ["wh-clause", "wh clause"],
    "wh_question": ["wh-question", "wh question"],
    "existential_there": ["existential there"],
    "prepositions": ["prepositions", "preposition"],
}

_WHITESPACE_RE = re.compile(r"\s+")
_NON_HEADING_TAIL_RE = re.compile(r"[.!?;:]$")
_DOT_LEADER_RE = re.compile(r"\.{5,}")
_CONTROL_GLYPH_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_SECTION_REF_RE = re.compile(r"(?:^|\s)\d+(?:\.\d+){1,}(?:\s|$)")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")


@dataclass(slots=True)
class BookTextPayload:
    source_path: str
    parser_name: str
    format: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BookSnippet:
    source_path: str
    parser_name: str
    format: str
    topic_key: str
    anchor: str
    heading: str
    snippet_text: str
    start_line: int
    end_line: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "").strip())


def _normalize_lines(text: str) -> list[str]:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    out: list[str] = []
    for raw in text.split("\n"):
        raw = _CONTROL_GLYPH_RE.sub(" ", raw)
        line = _norm(raw)
        out.append(line)
    return out


def _looks_like_toc_line(line: str) -> bool:
    line = _norm(line)
    if not line:
        return False
    if _DOT_LEADER_RE.search(line):
        return True
    if _PAGE_NUMBER_RE.fullmatch(line):
        return True
    if len(_SECTION_REF_RE.findall(line)) >= 2:
        return True
    punctuation = sum(1 for ch in line if not ch.isalnum() and not ch.isspace())
    letters = sum(1 for ch in line if ch.isalpha())
    if punctuation >= max(6, letters // 2 + 2):
        return True
    return False


def _looks_like_heading(line: str) -> bool:
    line = _norm(line)
    if not line:
        return False
    if _looks_like_toc_line(line):
        return False
    if len(line) > 120:
        return False
    if _NON_HEADING_TAIL_RE.search(line):
        return False
    letters = sum(1 for ch in line if ch.isalpha())
    if letters < 4:
        return False
    words = line.split()
    if len(words) > 14:
        return False
    return True


def _is_stop_line(line: str) -> bool:
    lowered = _norm(line).lower()
    if not lowered:
        return True
    if _looks_like_toc_line(lowered):
        return True
    stop_markers = (
        "quiz",
        "exercises",
        "exercise",
        "answers",
        "study guide",
        "unit ",
        "contents",
    )
    return any(marker in lowered for marker in stop_markers)


def _looks_like_usable_snippet(text: str) -> bool:
    text = _norm(text)
    if not text:
        return False
    if _looks_like_toc_line(text):
        return False
    words = re.findall(r"[A-Za-z]{2,}", text)
    if len(words) < 5:
        return False
    if len(set(words)) < 3:
        return False
    return True


class UniversalBookExtractionEngine:
    def __init__(
        self,
        *,
        parsers: list[Any],
        topic_anchors: dict[str, list[str]] | None = None,
        max_snippet_lines: int = 18,
        cache_dir: str | None = None,
    ) -> None:
        self.parsers = list(parsers)
        self.topic_anchors = topic_anchors or DEFAULT_GRAMMAR_ANCHORS
        self.max_snippet_lines = max(4, int(max_snippet_lines))
        self.cache_dir = str(cache_dir) if cache_dir else None

    def resolve_parser(self, source_path: str):
        for parser in self.parsers:
            if parser.supports(source_path):
                return parser
        raise ValueError(f"No parser registered for: {source_path}")

    def parse_book(self, source_path: str) -> BookTextPayload:
        cached = load_cached_payload(source_path, self.cache_dir)
        if cached is not None:
            cached.metadata = dict(cached.metadata)
            cached.metadata["cache_status"] = "hit"
            return cached
        parser = self.resolve_parser(source_path)
        payload = parser.parse(source_path)
        payload.metadata = dict(payload.metadata)
        payload.metadata["cache_status"] = "miss"
        save_payload_cache(payload, self.cache_dir)
        return payload

    def extract_from_payload(self, payload: BookTextPayload) -> list[BookSnippet]:
        lines = _normalize_lines(payload.text)
        snippets: list[BookSnippet] = []
        seen: set[tuple[str, str, str]] = set()
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if not _looks_like_heading(line):
                continue
            for topic_key, anchors in self.topic_anchors.items():
                matched_anchor = next((anchor for anchor in anchors if anchor in lowered), "")
                if not matched_anchor:
                    continue
                snippet_text, end_line = self._collect_snippet(lines, idx)
                if not _looks_like_usable_snippet(snippet_text):
                    continue
                dedupe_key = (topic_key, _norm(line).lower(), _norm(snippet_text).lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                snippets.append(
                    BookSnippet(
                        source_path=payload.source_path,
                        parser_name=payload.parser_name,
                        format=payload.format,
                        topic_key=topic_key,
                        anchor=matched_anchor,
                        heading=line,
                        snippet_text=snippet_text,
                        start_line=idx + 1,
                        end_line=end_line + 1,
                    )
                )
                break
        return snippets

    def _collect_snippet(self, lines: list[str], start_index: int) -> tuple[str, int]:
        chunks: list[str] = []
        end_index = start_index
        for idx in range(start_index + 1, min(len(lines), start_index + 1 + self.max_snippet_lines)):
            line = lines[idx]
            if not line:
                if chunks:
                    break
                continue
            if idx > start_index + 1 and _looks_like_heading(line):
                break
            if _is_stop_line(line):
                break
            chunks.append(line)
            end_index = idx
        snippet_text = _norm(" ".join(chunks))
        return snippet_text, end_index

    def extract_from_path(self, source_path: str) -> list[BookSnippet]:
        return self.extract_from_payload(self.parse_book(source_path))

    def extract_many(self, paths: list[str]) -> list[BookSnippet]:
        snippets: list[BookSnippet] = []
        for path in paths:
            snippets.extend(self.extract_from_path(path))
        return snippets


def discover_supported_book_paths(input_path: str, engine: UniversalBookExtractionEngine) -> list[str]:
    root = Path(input_path)
    if root.is_file():
        return [str(root)]
    out: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            engine.resolve_parser(str(path))
        except ValueError:
            continue
        out.append(str(path))
    return out


def _cache_entry_name(source_path: str) -> str:
    source = Path(source_path)
    digest = hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:12]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("._") or "book"
    return f"{stem}__{digest}"


def load_cached_payload(source_path: str, cache_dir: str | None) -> BookTextPayload | None:
    if not cache_dir:
        return None
    source = Path(source_path)
    cache_root = Path(cache_dir)
    entry_dir = cache_root / _cache_entry_name(str(source))
    meta_path = entry_dir / "payload.json"
    text_path = entry_dir / "payload.txt"
    if not meta_path.exists() or not text_path.exists() or not source.exists():
        return None

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    stat = source.stat()
    if payload.get("source_mtime_ns") != stat.st_mtime_ns or payload.get("source_size") != stat.st_size:
        return None

    return BookTextPayload(
        source_path=payload["source_path"],
        parser_name=payload["parser_name"],
        format=payload["format"],
        text=text_path.read_text(encoding="utf-8", errors="ignore"),
        metadata=dict(payload.get("metadata") or {}),
    )


def save_payload_cache(payload: BookTextPayload, cache_dir: str | None) -> None:
    if not cache_dir:
        return
    source = Path(payload.source_path)
    if not source.exists():
        return
    cache_root = Path(cache_dir)
    entry_dir = cache_root / _cache_entry_name(payload.source_path)
    entry_dir.mkdir(parents=True, exist_ok=True)

    stat = source.stat()
    text_path = entry_dir / "payload.txt"
    meta_path = entry_dir / "payload.json"

    text_path.write_text(payload.text, encoding="utf-8")
    meta = {
        "source_path": payload.source_path,
        "parser_name": payload.parser_name,
        "format": payload.format,
        "metadata": dict(payload.metadata),
        "source_mtime_ns": stat.st_mtime_ns,
        "source_size": stat.st_size,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
