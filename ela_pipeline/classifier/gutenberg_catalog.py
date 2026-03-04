"""Project Gutenberg catalog helpers for bounded C1/C2 corpus harvesting."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def build_gutenberg_text_url(gutenberg_id: str) -> str:
    book_id = str(gutenberg_id or "").strip()
    if not book_id:
        return ""
    return f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"


def load_gutenberg_catalog(csv_path: str) -> list[dict[str, str]]:
    src = Path(csv_path)
    if not src.is_file():
        raise FileNotFoundError(f"Gutenberg catalog not found: {csv_path}")
    with src.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [{str(k): str(v or "") for k, v in row.items()} for row in reader]


def filter_gutenberg_catalog(
    rows: list[dict[str, str]],
    *,
    subject_keywords: list[str] | None = None,
    type_keywords: list[str] | None = None,
    language: str = "en",
    allowed_locc_prefixes: list[str] | None = None,
    exclude_bookshelf_keywords: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    subject_terms = [term.strip().lower() for term in (subject_keywords or []) if term.strip()]
    type_terms = [term.strip().lower() for term in (type_keywords or []) if term.strip()]
    allowed_locc = [term.strip().upper() for term in (allowed_locc_prefixes or []) if term.strip()]
    exclude_bookshelf_terms = [term.strip().lower() for term in (exclude_bookshelf_keywords or []) if term.strip()]

    selected: list[dict[str, Any]] = []
    for row in rows:
        row_language = str(row.get("Language") or row.get("language") or "").strip().lower()
        if language and row_language and row_language != language.lower():
            continue

        subjects = str(row.get("Subjects") or row.get("subjects") or "").strip()
        bookshelf = str(row.get("Bookshelves") or row.get("bookshelves") or "").strip()
        title = str(row.get("Title") or row.get("title") or "").strip()
        gutenberg_id = str(row.get("Text#") or row.get("ID") or "").strip()
        text_url = build_gutenberg_text_url(gutenberg_id)
        if not gutenberg_id or not text_url:
            continue

        haystacks = [subjects.lower(), bookshelf.lower(), title.lower()]
        if subject_terms and not any(any(term in hay for hay in haystacks) for term in subject_terms):
            continue
        if type_terms and not any(any(term in hay for hay in haystacks) for term in type_terms):
            continue
        if exclude_bookshelf_terms and any(term in bookshelf.lower() for term in exclude_bookshelf_terms):
            continue

        locc = str(row.get("LoCC") or row.get("locc") or "").strip()
        if allowed_locc:
            prefixes = [chunk.strip().upper() for chunk in locc.split(";") if chunk.strip()]
            if not any(any(prefix.startswith(allowed) for allowed in allowed_locc) for prefix in prefixes):
                continue

        selected.append(
            {
                "title": title,
                "author": str(row.get("Authors") or row.get("Author") or "").strip(),
                "language": row_language,
                "subjects": subjects,
                "bookshelves": bookshelf,
                "locc": locc,
                "text_url": text_url,
                "gutenberg_id": gutenberg_id,
            }
        )
        if limit is not None and len(selected) >= limit:
            break
    return selected
