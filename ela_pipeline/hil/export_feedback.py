"""Human-in-the-Loop feedback export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ela_pipeline.db.repository import PostgresContractRepository

ALLOWED_FIELD_PATHS = {
    "notes",
    "translation",
    "phonetic",
    "synonyms",
    "cefr_level",
    "tense",
    "aspect",
    "mood",
    "voice",
    "finiteness",
    "grammatical_role",
    "tam_construction",
}

VALID_CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}


def _is_valid_row(row: dict[str, Any]) -> bool:
    field_path = str(row.get("field_path", "")).strip()
    if field_path not in ALLOWED_FIELD_PATHS:
        return False
    reviewed_by = str(row.get("reviewed_by", "")).strip()
    if not reviewed_by:
        return False
    if field_path == "cefr_level":
        after_value = row.get("after_value")
        if not isinstance(after_value, str) or after_value not in VALID_CEFR_LEVELS:
            return False
    return True


def apply_feedback_quality_gates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter rows by quality gates and deduplicate rows for retraining export."""
    dedup_seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not _is_valid_row(row):
            continue
        key = (
            str(row.get("sentence_key", "")),
            str(row.get("node_id", "")),
            str(row.get("field_path", "")),
            json.dumps(row.get("after_value"), ensure_ascii=False, sort_keys=True),
        )
        if key in dedup_seen:
            continue
        dedup_seen.add(key)
        out.append(row)
    return out


def export_feedback_to_jsonl(
    *,
    db_url: str,
    output_path: str,
    reviewed_by: str | None = None,
    limit: int | None = None,
) -> int:
    repo = PostgresContractRepository(db_url=db_url)
    rows = repo.export_feedback_rows(reviewed_by=reviewed_by, limit=limit)
    filtered = apply_feedback_quality_gates(rows)
    return write_feedback_rows_to_jsonl(filtered, output_path)


def write_feedback_rows_to_jsonl(rows: list[dict[str, Any]], output_path: str) -> int:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
    return len(rows)
