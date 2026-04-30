"""Evaluate a trained tabular note-id classifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib

from .evaluate_deberta_classifier import evaluate_rows
from .train_tabular_cefr_baseline import build_feature_rows
from .infer_tabular_note_classifier import load_label_order


def _map_prediction_to_label(value: Any, *, label_order: list[str]) -> str:
    raw = str(value).strip()
    if raw in label_order:
        return raw
    try:
        idx = int(float(raw))
    except (TypeError, ValueError):
        return raw
    if 0 <= idx < len(label_order):
        return label_order[idx]
    return raw


def evaluate_tabular_note_classifier(
    *,
    dataset_path: str,
    model_path: str,
    summary_path: str,
    feature_profile: str = "runtime_stable",
) -> dict[str, Any]:
    rows = []
    src = Path(dataset_path)
    if not src.is_file():
        raise FileNotFoundError(f"dataset file not found: {dataset_path}")
    with src.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
    model = joblib.load(model_path)
    feature_rows, _ = build_feature_rows(rows, label_field="note_id", feature_profile=feature_profile)
    valid_rows = [row for row in rows if str(row.get("note_id") or "").strip()]
    raw_pred = model.predict(feature_rows)
    label_order = load_label_order(summary_path)
    pred_labels = [_map_prediction_to_label(item, label_order=label_order) for item in list(raw_pred)]

    predictions = {str(row.get("input") or ""): pred for row, pred in zip(valid_rows, pred_labels)}
    metrics = evaluate_rows(valid_rows, lambda text: predictions.get(text, ""), label_field="note_id")
    return {
        "dataset_path": dataset_path,
        "model_path": model_path,
        "summary_path": summary_path,
        "feature_profile": feature_profile,
        "metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate tabular note-id classifier.")
    parser.add_argument("--dataset-path", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--feature-profile", default="runtime_stable", choices=["full", "no_source", "runtime_stable"])
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()
    result = evaluate_tabular_note_classifier(
        dataset_path=args.dataset_path,
        model_path=args.model_path,
        summary_path=args.summary_path,
        feature_profile=args.feature_profile,
    )
    output_path = str(args.output_path or "").strip()
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
