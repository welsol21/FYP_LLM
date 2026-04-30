"""Inference helper for tabular note-id classifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from .train_tabular_cefr_baseline import extract_tabular_features, project_feature_profile


def load_note_inventory(inventory_path: str) -> dict[str, dict[str, str]]:
    src = Path(inventory_path)
    if not src.is_file():
        raise FileNotFoundError(f"note inventory not found: {inventory_path}")
    payload = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("note_id_inventory.json must be a list")
    out: dict[str, dict[str, str]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        note_id = str(row.get("note_id") or "").strip()
        if not note_id:
            continue
        out[note_id] = {
            "note_text": str(row.get("note_text") or "").strip(),
            "note_type": str(row.get("note_type") or "").strip(),
        }
    return out


def load_label_order(summary_path: str) -> list[str]:
    src = Path(summary_path)
    if not src.is_file():
        raise FileNotFoundError(f"training summary not found: {summary_path}")
    payload = json.loads(src.read_text(encoding="utf-8"))
    explicit_order = payload.get("label_order")
    if isinstance(explicit_order, list) and explicit_order:
        return [str(item).strip() for item in explicit_order if str(item).strip()]
    label_counts = payload.get("train_label_counts")
    if not isinstance(label_counts, dict) or not label_counts:
        raise ValueError("train_label_counts missing in summary")
    return list(label_counts.keys())


def _resolve_note_id(class_label: Any, *, label_order: list[str]) -> str:
    raw = str(class_label).strip()
    if raw in label_order:
        return raw
    try:
        idx = int(float(raw))
    except (TypeError, ValueError):
        return raw
    if 0 <= idx < len(label_order):
        return label_order[idx]
    return raw


def build_runtime_feature_row(input_text: str, *, feature_profile: str) -> dict[str, Any]:
    base_row = {
        "input": input_text,
        "text": input_text,
        "source_text": input_text,
        "grammar_evidence": {},
        "grammar_classes": [],
        "provenance": {
            "dataset_source": "runtime_note_id_inference",
            "treebank": "runtime_note_id_inference",
        },
    }
    return project_feature_profile(extract_tabular_features(base_row), profile=feature_profile)


def infer_top_k_note_ids(
    *,
    model_path: str,
    summary_path: str,
    inventory_path: str,
    input_text: str,
    top_k: int = 5,
) -> dict[str, Any]:
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    feature_profile = str(summary.get("feature_profile") or "runtime_stable").strip().lower()
    label_order = load_label_order(summary_path)
    inventory = load_note_inventory(inventory_path)
    model = joblib.load(model_path)
    features = build_runtime_feature_row(input_text, feature_profile=feature_profile)
    if not hasattr(model, "predict_proba"):
        raise ValueError("Loaded model does not support predict_proba")
    vectorizer = model.named_steps.get("vectorizer") if hasattr(model, "named_steps") else None
    classifier = model.named_steps.get("classifier", model) if hasattr(model, "named_steps") else model
    classes = list(getattr(classifier, "classes_", []))

    proba = None
    inference_backend = "sklearn_predict_proba"
    if vectorizer is not None and hasattr(classifier, "get_booster"):
        try:
            import cupy as cp

            dense = vectorizer.transform([features]).astype(np.float32, copy=False)
            gpu_dense = cp.asarray(dense)
            raw = classifier.get_booster().inplace_predict(gpu_dense)
            proba = cp.asnumpy(raw)
            inference_backend = "xgboost_inplace_predict_cupy"
        except Exception:
            proba = None
    if proba is None:
        proba = model.predict_proba([features])
    if isinstance(proba, list):
        proba = np.asarray(proba)
    if getattr(proba, "ndim", 0) != 2 or proba.shape[0] != 1:
        raise ValueError("Unexpected predict_proba output shape")
    scores = proba[0]
    ranked_indices = list(np.argsort(scores)[::-1][:top_k])
    predictions: list[dict[str, Any]] = []
    for idx in ranked_indices:
        class_label = classes[int(idx)] if int(idx) < len(classes) else int(idx)
        note_id = _resolve_note_id(class_label, label_order=label_order)
        meta = inventory.get(note_id, {})
        predictions.append(
            {
                "rank": len(predictions) + 1,
                "note_id": note_id,
                "score": float(scores[int(idx)]),
                "note_text": str(meta.get("note_text") or ""),
                "note_type": str(meta.get("note_type") or ""),
            }
        )
    return {
        "input": input_text,
        "feature_profile": feature_profile,
        "inference_backend": inference_backend,
        "top_k": top_k,
        "predictions": predictions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Infer top-k note_ids with tabular note classifier.")
    parser.add_argument("--model-path", default="artifacts/models/tabular_note_classifier_v40/best_tabular_note_classifier.joblib")
    parser.add_argument("--summary-path", default="artifacts/models/tabular_note_classifier_v40/tabular_note_classifier_summary.json")
    parser.add_argument("--inventory-path", default="artifacts/classifier_note_id_v40/note_id_inventory.json")
    parser.add_argument("--input-text", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()

    result = infer_top_k_note_ids(
        model_path=args.model_path,
        summary_path=args.summary_path,
        inventory_path=args.inventory_path,
        input_text=args.input_text,
        top_k=args.top_k,
    )
    output_path = str(args.output_path or "").strip()
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
