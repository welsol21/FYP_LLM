"""Build train-ready advanced classifier rows from local Project Gutenberg texts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .build_ud_phase1_dataset import PHASE1_CLASS_SPECS, _compose_classifier_input
from .gutenberg_ingest import build_gutenberg_sentence_candidates
from .text_parse import enrich_sentence_candidates
from .ud_phase1 import extract_phase1_grammar_signal, validate_phase1_dataset_gates


ADVANCED_LEVELS = {"B2", "C1", "C2"}


def _row_from_gutenberg_sentence(sentence: dict[str, Any], *, row_id: str) -> dict[str, Any] | None:
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


def build_gutenberg_advanced_dataset(
    *,
    text_paths: list[str],
    output_dir: str,
    metadata_by_path: dict[str, dict[str, Any]] | None = None,
    text_patterns: list[str] | None = None,
    min_chars: int = 20,
    max_chars: int = 400,
    parse_row_limit: int | None = None,
    min_examples_per_class: int = 2,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "gutenberg_advanced_classifier.jsonl"
    rejected_path = out_dir / "gutenberg_advanced_rejected.jsonl"
    gate_path = out_dir / "gutenberg_advanced_gate_report.json"
    manifest_path = out_dir / "gutenberg_advanced_manifest.json"

    metadata_by_path = metadata_by_path or {}
    candidates: list[dict[str, Any]] = []
    selected_texts: list[str] = []
    for path in text_paths:
        rows = build_gutenberg_sentence_candidates(
            text_path=path,
            metadata=metadata_by_path.get(path, {}),
            min_chars=min_chars,
            max_chars=max_chars,
            text_patterns=text_patterns,
        )
        if rows:
            selected_texts.append(path)
            candidates.extend(rows)

    if parse_row_limit is not None:
        candidates = candidates[:parse_row_limit]

    parsed_rows = enrich_sentence_candidates(candidates)

    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for idx, sentence in enumerate(parsed_rows, start=1):
        built = _row_from_gutenberg_sentence(sentence, row_id=f"gutenberg-advanced-{idx}")
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

    mapped_cefr_counts = Counter(str(row.get("cefr_level") or "").strip().upper() for row in accepted_rows)
    mapped_class_support = Counter()
    for row in accepted_rows:
        cefr = str(row.get("cefr_level") or "").strip().upper()
        for class_id in row.get("grammar_classes", []):
            mapped_class_support[(cefr, class_id)] += 1

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
    manifest_path.write_text(
        json.dumps(
            {
                "selected_texts": selected_texts,
                "candidate_rows": len(candidates),
                "parsed_rows": len(parsed_rows),
                "text_patterns": list(text_patterns or []),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "dataset_path": str(dataset_path),
        "rejected_path": str(rejected_path),
        "manifest_path": str(manifest_path),
        "gate_report_path": str(gate_path),
        "accepted_rows": len(final_rows),
        "rejected_rows": len(rejected_rows),
        "candidates": len(candidates),
        "mapped_rows_before_gates": len(accepted_rows),
        "mapped_cefr_counts": dict(sorted(mapped_cefr_counts.items())),
        "mapped_class_support": [
            {"cefr_level": cefr, "class_id": class_id, "count": count}
            for (cefr, class_id), count in sorted(mapped_class_support.items())
        ],
        "gate_report": gate_report,
    }

