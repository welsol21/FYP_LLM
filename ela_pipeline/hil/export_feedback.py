"""Human-in-the-Loop feedback export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ela_pipeline.db.repository import PostgresContractRepository
from ela_pipeline.hil.review_schema import is_allowed_review_field_path, review_field_root

VALID_CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}
ALLOWED_LICENSE_VALUES = {
    "public_domain",
    "project_owned",
    "cc_by",
    "cc_by_sa",
    "mit",
    "apache_2_0",
    "internal_review",
}
EXTERNAL_ATTRIBUTED_LICENSES = {"public_domain", "cc_by", "cc_by_sa", "mit", "apache_2_0"}
SOURCE_LICENSE_POLICY = {
    "manual_review": {"internal_review", "project_owned"},
    "trusted_corpus": {"public_domain", "cc_by", "cc_by_sa", "mit", "apache_2_0"},
    "public_reference": {"public_domain", "cc_by", "cc_by_sa"},
    "project_asset": {"project_owned", "mit", "apache_2_0"},
}


def _is_valid_row(row: dict[str, Any]) -> bool:
    field_path = str(row.get("field_path", "")).strip()
    if not is_allowed_review_field_path(field_path):
        return False
    reviewed_by = str(row.get("reviewed_by", "")).strip()
    if not reviewed_by:
        return False
    meta = row.get("review_metadata")
    if not isinstance(meta, dict):
        return False
    provenance = meta.get("provenance")
    if not isinstance(provenance, dict):
        return False
    source = str(provenance.get("source", "")).strip()
    license_value = str(provenance.get("license", "")).strip().lower()
    source_url = str(provenance.get("source_url", "")).strip()
    if not source:
        return False
    if license_value not in ALLOWED_LICENSE_VALUES:
        return False
    allowed_for_source = SOURCE_LICENSE_POLICY.get(source)
    if allowed_for_source is None or license_value not in allowed_for_source:
        return False
    if license_value in EXTERNAL_ATTRIBUTED_LICENSES:
        if not (source_url.startswith("http://") or source_url.startswith("https://")):
            return False
    if review_field_root(field_path) == "cefr_level":
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
