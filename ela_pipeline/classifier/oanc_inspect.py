"""Inspect OANC zip packages without full extraction."""

from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from typing import Any
import zipfile


OANC_ADVANCED_GENRE_MARKERS: tuple[str, ...] = (
    "written_1/journal",
    "written_2/technical",
    "written_2/non-fiction",
)


def _normalize_zip_path(member: str) -> str:
    return str(PurePosixPath(str(member).replace("\\", "/")))


def _bucket_for_member(member: str) -> str | None:
    normalized = _normalize_zip_path(member)
    parts = PurePosixPath(normalized).parts
    try:
        data_index = parts.index("data")
    except ValueError:
        return None
    if len(parts) <= data_index + 2:
        return None
    return "/".join(parts[data_index + 1 : data_index + 3])


def summarize_oanc_zip(zip_path: str) -> dict[str, Any]:
    txt_files = 0
    anc_files = 0
    xml_files = 0
    top_genre_buckets: Counter[str] = Counter()

    with zipfile.ZipFile(zip_path) as zf:
        for raw_name in zf.namelist():
            member = _normalize_zip_path(raw_name)
            suffix = PurePosixPath(member).suffix.lower()
            if suffix == ".txt":
                txt_files += 1
            elif suffix == ".anc":
                anc_files += 1
            elif suffix == ".xml":
                xml_files += 1

            bucket = _bucket_for_member(member)
            if bucket:
                top_genre_buckets[bucket] += 1

    return {
        "txt_files": txt_files,
        "anc_files": anc_files,
        "xml_files": xml_files,
        "top_genre_buckets": [bucket for bucket, _ in top_genre_buckets.most_common(20)],
    }


def list_oanc_candidate_files(zip_path: str) -> list[str]:
    candidates: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for raw_name in zf.namelist():
            member = _normalize_zip_path(raw_name)
            if not member.lower().endswith(".txt"):
                continue
            if any(marker in member for marker in OANC_ADVANCED_GENRE_MARKERS):
                candidates.append(member)
    return sorted(candidates)


def extract_oanc_text(zip_path: str, member_path: str) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member_path) as handle:
            payload = handle.read()
    return payload.decode("utf-8", errors="replace")
