"""Build sentence candidates from OANC zip packages."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
from collections import Counter, defaultdict
import re

from .oanc_inspect import extract_oanc_text, list_oanc_candidate_files


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_WHITESPACE_RE = re.compile(r"\s+")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n+")
_ABBREVIATIONS = ("Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.", "St.", "vs.", "etc.")


def _normalize_sentence(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "")).strip()


def _genre_bucket(member_path: str) -> str:
    parts = PurePosixPath(member_path).parts
    try:
        data_index = parts.index("data")
    except ValueError:
        return "unknown"
    if len(parts) <= data_index + 2:
        return "unknown"
    return "/".join(parts[data_index + 1 : data_index + 3])


def split_oanc_text_to_sentences(text: str, *, min_chars: int = 20, max_chars: int = 400) -> list[str]:
    pieces: list[str] = []
    paragraphs = [segment.strip() for segment in _PARAGRAPH_SPLIT_RE.split(str(text or "")) if segment.strip()]
    if not paragraphs:
        return []

    for paragraph in paragraphs:
        normalized = _normalize_sentence(paragraph)
        if not normalized:
            continue
        if not re.search(r"[.!?]$", normalized) and len(normalized) <= 80:
            continue

        cursor = 0
        for match in _SENTENCE_SPLIT_RE.finditer(normalized):
            candidate = normalized[cursor : match.start()].strip()
            if any(candidate.endswith(abbrev) for abbrev in _ABBREVIATIONS):
                continue
            if candidate:
                pieces.append(candidate)
            cursor = match.end()
        tail = normalized[cursor:].strip()
        if tail:
            pieces.append(tail)

    out: list[str] = []
    for piece in pieces:
        sentence = _normalize_sentence(piece)
        if len(sentence) < min_chars or len(sentence) > max_chars:
            continue
        out.append(sentence)
    return out


def build_oanc_sentence_candidates(
    zip_path: str,
    *,
    member_paths: list[str] | None = None,
    limit_files: int | None = None,
    min_chars: int = 20,
    max_chars: int = 400,
) -> list[dict[str, Any]]:
    if member_paths is None:
        member_paths = list_oanc_candidate_files(zip_path)
        if limit_files is not None:
            member_paths = member_paths[: max(0, int(limit_files))]

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for member_path in member_paths:
        raw_text = extract_oanc_text(zip_path, member_path)
        sentences = split_oanc_text_to_sentences(raw_text, min_chars=min_chars, max_chars=max_chars)
        bucket = _genre_bucket(member_path)
        for idx, sentence in enumerate(sentences):
            dedup_key = (bucket, sentence.lower())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            rows.append(
                {
                    "text": sentence,
                    "provenance": {
                        "source": "OANC",
                        "member_path": member_path,
                        "genre_bucket": bucket,
                        "sentence_index_in_file": idx,
                    },
                }
            )
    return rows


def build_oanc_candidate_manifest(
    zip_path: str,
    *,
    per_bucket_limit: int | None = None,
    total_limit: int | None = None,
) -> dict[str, Any]:
    member_paths = list_oanc_candidate_files(zip_path)
    selected: list[str] = []
    bucket_counts: Counter[str] = Counter()
    grouped: dict[str, list[str]] = defaultdict(list)
    for member_path in member_paths:
        grouped[_genre_bucket(member_path)].append(member_path)

    for bucket in sorted(grouped):
        items = grouped[bucket]
        if per_bucket_limit is not None:
            items = items[: max(0, int(per_bucket_limit))]
        for item in items:
            if total_limit is not None and len(selected) >= int(total_limit):
                break
            selected.append(item)
            bucket_counts[bucket] += 1
        if total_limit is not None and len(selected) >= int(total_limit):
            break

    return {
        "zip_path": zip_path,
        "selected_files": len(selected),
        "bucket_counts": dict(bucket_counts),
        "member_paths": selected,
    }
