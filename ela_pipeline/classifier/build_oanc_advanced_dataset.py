"""Build train-ready advanced classifier rows from OANC sentence candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .build_ud_phase1_dataset import PHASE1_CLASS_SPECS, _compose_classifier_input
from .oanc_ingest import build_oanc_candidate_manifest, build_oanc_sentence_candidates
from .oanc_parse import enrich_oanc_sentence_candidates
from .ud_phase1 import extract_phase1_grammar_signal, validate_phase1_dataset_gates


ADVANCED_LEVELS = {"B2", "C1", "C2"}


def _row_from_oanc_sentence(sentence: dict[str, Any], *, row_id: str) -> dict[str, Any] | None:
    signal = extract_phase1_grammar_signal(sentence)
    grammar_classes = signal.get("grammar_classes")
    if not isinstance(grammar_classes, list) or not grammar_classes:
        return None

    accepted = [
        class_id
        for class_id in grammar_classes
        if class_id in PHASE1_CLASS_SPECS and PHASE1_CLASS_SPECS[class_id]["cefr_level"] in ADVANCED_LEVELS
    ]
    if not accepted:
        return None

    class_id = accepted[0]
    spec = PHASE1_CLASS_SPECS[class_id]
    return {
        "id": row_id,
        "text": str(sentence.get("text") or "").strip(),
        "cefr_level": spec["cefr_level"],
        "grammar_classes": accepted,
        "tam_profile": signal.get("tam_profile"),
        "grammar_evidence": signal.get("grammar_evidence"),
        "note_blueprints": {
            "elementary_text": spec["elementary_text"],
            "intermediate_text": spec["intermediate_text"],
            "advanced_text": spec["advanced_text"],
        },
        "provenance": sentence.get("provenance") if isinstance(sentence.get("provenance"), dict) else {},
    }


def build_oanc_advanced_dataset(
    *,
    zip_path: str,
    output_dir: str,
    member_paths: list[str] | None = None,
    per_bucket_limit: int = 250,
    total_limit: int = 600,
    min_chars: int = 40,
    max_chars: int = 320,
    min_examples_per_class: int = 2,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "oanc_advanced_classifier.jsonl"
    rejected_path = out_dir / "oanc_advanced_rejected.jsonl"
    gate_path = out_dir / "oanc_advanced_gate_report.json"
    manifest_path = out_dir / "oanc_advanced_manifest.json"

    if member_paths is None:
        manifest = build_oanc_candidate_manifest(
            zip_path,
            per_bucket_limit=per_bucket_limit,
            total_limit=total_limit,
        )
        selected_member_paths = manifest["member_paths"]
    else:
        selected_member_paths = list(member_paths)
        manifest = {
            "zip_path": zip_path,
            "selected_files": len(selected_member_paths),
            "bucket_counts": {},
            "member_paths": selected_member_paths,
        }
    candidates = build_oanc_sentence_candidates(
        zip_path,
        member_paths=selected_member_paths,
        min_chars=min_chars,
        max_chars=max_chars,
    )
    parsed_rows = enrich_oanc_sentence_candidates(candidates)

    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for idx, sentence in enumerate(parsed_rows, start=1):
        built = _row_from_oanc_sentence(sentence, row_id=f"oanc-advanced-{idx}")
        if built is None:
            rejected_rows.append(
                {
                    "text": sentence.get("text"),
                    "provenance": sentence.get("provenance"),
                    "reason": "not_advanced_or_no_mapping",
                }
            )
            continue
        accepted_rows.append(built)

    gate_report = validate_phase1_dataset_gates(
        accepted_rows,
        min_examples_per_class=min_examples_per_class,
    )
    final_rows = accepted_rows if gate_report["passed"] else []
    if not gate_report["passed"]:
        for row in accepted_rows:
            rejected_rows.append(
                {
                    "text": row.get("text"),
                    "provenance": row.get("provenance"),
                    "reason": "failed_dataset_gates",
                }
            )

    with dataset_path.open("w", encoding="utf-8") as f:
        for row in final_rows:
            payload = {
                **row,
                "input": _compose_classifier_input(row),
                "cefr_label": row["cefr_level"],
                "source_text": row["text"],
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    with rejected_path.open("w", encoding="utf-8") as f:
        for row in rejected_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    gate_path.write_text(json.dumps(gate_report, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "dataset_path": str(dataset_path),
        "rejected_path": str(rejected_path),
        "manifest_path": str(manifest_path),
        "gate_report_path": str(gate_path),
        "accepted_rows": len(final_rows),
        "rejected_rows": len(rejected_rows),
        "gate_report": gate_report,
    }
