"""Sentence candidate ingest for local Project Gutenberg texts."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import spacy


_GUTENBERG_START_RE = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG", re.IGNORECASE)
_GUTENBERG_END_RE = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG", re.IGNORECASE)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")


@lru_cache(maxsize=1)
def _load_sentencizer():
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def extract_gutenberg_body(text: str) -> str:
    lines = str(text or "").splitlines()
    start = 0
    end = len(lines)
    for idx, line in enumerate(lines):
        if _GUTENBERG_START_RE.search(line):
            start = idx + 1
            break
    for idx in range(len(lines) - 1, -1, -1):
        if _GUTENBERG_END_RE.search(lines[idx]):
            end = idx
            break
    body = "\n".join(lines[start:end]).strip()
    return body


def build_gutenberg_sentence_candidates(
    *,
    text_path: str,
    metadata: dict[str, Any] | None = None,
    min_chars: int = 20,
    max_chars: int = 400,
    text_patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
    src = Path(text_path)
    if not src.is_file():
        raise FileNotFoundError(f"Gutenberg text not found: {text_path}")

    body = extract_gutenberg_body(src.read_text(encoding="utf-8", errors="ignore"))
    nlp = _load_sentencizer()
    patterns = [re.compile(pattern, flags=re.IGNORECASE) for pattern in (text_patterns or []) if str(pattern).strip()]

    rows: list[dict[str, Any]] = []
    sentence_index = 0
    paragraphs = [segment.strip() for segment in _PARAGRAPH_SPLIT_RE.split(body) if segment.strip()]
    for paragraph in paragraphs:
        if len(paragraph) > 200000:
            chunks = [paragraph[i : i + 200000] for i in range(0, len(paragraph), 200000)]
        else:
            chunks = [paragraph]
        for chunk in chunks:
            doc = nlp(chunk)
            for sent in doc.sents:
                text = " ".join(sent.text.split()).strip()
                if len(text) < min_chars or len(text) > max_chars:
                    continue
                if patterns and not any(pattern.search(text) for pattern in patterns):
                    continue
                sentence_index += 1
                provenance = dict(metadata or {})
                provenance.update(
                    {
                        "source": "ProjectGutenberg",
                        "source_path": str(src),
                        "sentence_index": sentence_index,
                    }
                )
                rows.append({"text": text, "provenance": provenance})
    return rows
