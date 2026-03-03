"""Audit classifier dataset identifiability and ambiguity before training."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"dataset file not found: {path}")
    rows: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
    return rows


def audit_classifier_dataset(*, dataset_path: str) -> dict[str, Any]:
    rows = _load_jsonl(dataset_path)
    combo_to_levels: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    text_to_levels: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        cefr = str(row.get("cefr_label") or row.get("cefr_level") or "").strip().upper()
        grammar = row.get("grammar_classes")
        text = str(row.get("text") or row.get("input") or "").strip()
        if not cefr or not isinstance(grammar, list):
            continue
        combo = tuple(sorted(str(x).strip().lower() for x in grammar if str(x).strip()))
        combo_to_levels[combo][cefr] += 1
        if text:
            text_to_levels[text].add(cefr)

    ambiguous_combos = [
        {
            "grammar_combo": list(combo),
            "counts_by_cefr": dict(levels),
            "sample_count": int(sum(levels.values())),
        }
        for combo, levels in combo_to_levels.items()
        if len(levels) > 1
    ]
    ambiguous_combos.sort(key=lambda x: x["sample_count"], reverse=True)

    exact_text_cross_level = [
        {"text": text, "cefr_levels": sorted(levels)}
        for text, levels in text_to_levels.items()
        if len(levels) > 1
    ]

    unique_combo_count = len(combo_to_levels)
    ambiguous_combo_count = len(ambiguous_combos)
    ambiguous_combo_ratio = (ambiguous_combo_count / unique_combo_count) if unique_combo_count else 0.0

    return {
        "dataset_path": dataset_path,
        "samples": len(rows),
        "unique_grammar_combos": unique_combo_count,
        "ambiguous_grammar_combo_count": ambiguous_combo_count,
        "ambiguous_grammar_combo_ratio": ambiguous_combo_ratio,
        "exact_text_cross_level_count": len(exact_text_cross_level),
        "top_ambiguous_grammar_combos": ambiguous_combos[:25],
        "exact_text_cross_level_examples": exact_text_cross_level[:25],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit classifier dataset ambiguity before DeBERTa training.")
    parser.add_argument("--dataset-path", required=True)
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()

    report = audit_classifier_dataset(dataset_path=args.dataset_path)
    if args.output_path:
        out = Path(args.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
