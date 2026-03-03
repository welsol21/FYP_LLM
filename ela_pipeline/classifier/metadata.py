"""Build runtime classifier metadata from grammar KB artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .curriculum import CEFR_LADDER


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"kb file not found: {path}")
    rows: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
    return rows


def build_classifier_metadata_from_kb(*, kb_raw_path: str, output_dir: str) -> dict[str, Any]:
    rows = _load_jsonl(kb_raw_path)
    if not rows:
        raise ValueError("kb_raw rows are empty")

    grammar_classes_by_cefr: dict[str, list[str]] = {lvl: [] for lvl in CEFR_LADDER}
    note_blueprints_by_cefr: dict[str, dict[str, str]] = {}
    per_class_cefr_ladder: dict[str, list[str]] = {}

    normalized_rows = sorted(
        rows,
        key=lambda r: (
            str(r.get("cefr_level") or ""),
            str(r.get("class_id") or ""),
        ),
    )
    for row in normalized_rows:
        cefr = str(row.get("cefr_level") or "").strip().upper()
        class_id = str(row.get("class_id") or "").strip().lower()
        if cefr not in grammar_classes_by_cefr or not class_id:
            continue
        if class_id not in grammar_classes_by_cefr[cefr]:
            grammar_classes_by_cefr[cefr].append(class_id)

        # Runtime validator expects full ladder presence for each class_id.
        per_class_cefr_ladder.setdefault(class_id, list(CEFR_LADDER))

        if cefr not in note_blueprints_by_cefr:
            note_blueprints_by_cefr[cefr] = {
                "elementary_text": str(row.get("blueprint_elementary") or "").strip() or f"[{cefr}] elementary note",
                "intermediate_text": str(row.get("blueprint_intermediate") or "").strip() or f"[{cefr}] intermediate note",
                "advanced_text": str(row.get("blueprint_advanced") or "").strip() or f"[{cefr}] advanced note",
            }

    for cefr in CEFR_LADDER:
        note_blueprints_by_cefr.setdefault(
            cefr,
            {
                "elementary_text": f"[{cefr}] elementary note",
                "intermediate_text": f"[{cefr}] intermediate note",
                "advanced_text": f"[{cefr}] advanced note",
            },
        )

    metadata = {
        "per_class_cefr_ladder": per_class_cefr_ladder,
        "grammar_classes_by_cefr": grammar_classes_by_cefr,
        "note_blueprints_by_cefr": note_blueprints_by_cefr,
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = out_dir / "classifier_metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return {
        "metadata_path": str(metadata_path),
        "class_count": len(per_class_cefr_ladder),
        "cefr_levels": list(CEFR_LADDER),
    }


def build_classifier_metadata_from_dataset(*, classifier_jsonl_path: str, output_dir: str) -> dict[str, Any]:
    rows = _load_jsonl(classifier_jsonl_path)
    if not rows:
        raise ValueError("classifier dataset rows are empty")

    grammar_classes_by_cefr: dict[str, list[str]] = {lvl: [] for lvl in CEFR_LADDER}
    note_blueprints_by_cefr: dict[str, dict[str, str]] = {}
    per_class_cefr_ladder: dict[str, list[str]] = {}

    for row in rows:
        cefr = str(row.get("cefr_label") or row.get("cefr_level") or "").strip().upper()
        if cefr not in grammar_classes_by_cefr:
            continue

        grammar_classes = row.get("grammar_classes")
        if isinstance(grammar_classes, list):
            for item in grammar_classes:
                class_id = str(item).strip().lower()
                if not class_id:
                    continue
                if class_id not in grammar_classes_by_cefr[cefr]:
                    grammar_classes_by_cefr[cefr].append(class_id)
                per_class_cefr_ladder.setdefault(class_id, list(CEFR_LADDER))

        if cefr not in note_blueprints_by_cefr:
            blueprints = row.get("note_blueprints") if isinstance(row.get("note_blueprints"), dict) else {}
            note_blueprints_by_cefr[cefr] = {
                "elementary_text": str(blueprints.get("elementary_text") or f"[{cefr}] elementary note").strip(),
                "intermediate_text": str(blueprints.get("intermediate_text") or f"[{cefr}] intermediate note").strip(),
                "advanced_text": str(blueprints.get("advanced_text") or f"[{cefr}] advanced note").strip(),
            }

    for cefr in CEFR_LADDER:
        note_blueprints_by_cefr.setdefault(
            cefr,
            {
                "elementary_text": f"[{cefr}] elementary note",
                "intermediate_text": f"[{cefr}] intermediate note",
                "advanced_text": f"[{cefr}] advanced note",
            },
        )

    metadata = {
        "per_class_cefr_ladder": per_class_cefr_ladder,
        "grammar_classes_by_cefr": grammar_classes_by_cefr,
        "note_blueprints_by_cefr": note_blueprints_by_cefr,
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = out_dir / "classifier_metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return {
        "metadata_path": str(metadata_path),
        "class_count": len(per_class_cefr_ladder),
        "cefr_levels": list(CEFR_LADDER),
    }
