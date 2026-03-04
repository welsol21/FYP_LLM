"""Build validation/control advanced classifier rows from MASC CoNLL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .build_ud_phase1_dataset import PHASE1_CLASS_SPECS, _compose_classifier_input
from .masc_ingest import load_masc_conll_sentences
from .text_parse import enrich_sentence_candidates
from .ud_phase1 import extract_phase1_grammar_signal, validate_phase1_dataset_gates


ADVANCED_LEVELS = {"B2", "C1", "C2"}


def _row_from_masc_sentence(sentence: dict[str, Any], *, row_id: str) -> dict[str, Any] | None:
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


def build_masc_advanced_dataset(
    *,
    zip_path: str,
    output_dir: str,
    member_paths: list[str] | None = None,
    limit_files: int | None = None,
    min_chars: int = 40,
    max_chars: int = 320,
    min_examples_per_class: int = 2,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "masc_advanced_classifier.jsonl"
    rejected_path = out_dir / "masc_advanced_rejected.jsonl"
    gate_path = out_dir / "masc_advanced_gate_report.json"

    candidates = load_masc_conll_sentences(
        zip_path,
        member_paths=member_paths,
        limit_files=limit_files,
        min_chars=min_chars,
        max_chars=max_chars,
    )
    parsed_rows = enrich_sentence_candidates(candidates)

    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for idx, sentence in enumerate(parsed_rows, start=1):
        built = _row_from_masc_sentence(sentence, row_id=f"masc-advanced-{idx}")
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
    return {
        "dataset_path": str(dataset_path),
        "rejected_path": str(rejected_path),
        "gate_report_path": str(gate_path),
        "accepted_rows": len(final_rows),
        "rejected_rows": len(rejected_rows),
        "candidates": len(candidates),
        "gate_report": gate_report,
    }
