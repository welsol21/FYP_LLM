"""Evaluate DeBERTa CEFR classifier on JSONL datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable


CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"dataset file not found: {path}")
    out: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
    return out


def _normalize_label(value: str) -> str:
    label = str(value or "").strip().upper()
    if label in CEFR_ORDER:
        return label
    if label.startswith("LABEL_"):
        idx = label.replace("LABEL_", "")
        if idx.isdigit():
            i = int(idx)
            if 0 <= i < len(CEFR_ORDER):
                return CEFR_ORDER[i]
    return ""


def _macro_f1(confusion: dict[str, dict[str, int]], labels: list[str]) -> float:
    f1_values: list[float] = []
    for label in labels:
        tp = confusion[label].get(label, 0)
        fp = sum(confusion[p].get(label, 0) for p in labels if p != label)
        fn = sum(confusion[label].get(p, 0) for p in labels if p != label)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        f1_values.append(f1)
    return sum(f1_values) / max(1, len(f1_values))


def evaluate_rows(
    rows: list[dict[str, Any]],
    predict_fn: Callable[[str], str],
) -> dict[str, Any]:
    y_true: list[str] = []
    y_pred: list[str] = []
    for row in rows:
        text = str(row.get("input") or row.get("text") or "").strip()
        true_label = _normalize_label(str(row.get("cefr_label") or row.get("cefr_level") or ""))
        if not text or not true_label:
            continue
        pred_label = _normalize_label(predict_fn(text))
        if not pred_label:
            continue
        y_true.append(true_label)
        y_pred.append(pred_label)

    labels = [x for x in CEFR_ORDER if x in set(y_true + y_pred)]
    confusion: dict[str, dict[str, int]] = {x: {y: 0 for y in labels} for x in labels}
    correct = 0
    for t, p in zip(y_true, y_pred):
        if t == p:
            correct += 1
        confusion[t][p] += 1

    total = len(y_true)
    accuracy = correct / total if total > 0 else 0.0
    macro_f1 = _macro_f1(confusion, labels) if labels else 0.0

    return {
        "samples": total,
        "labels": labels,
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "confusion": confusion,
    }


def evaluate_deberta(*, dataset_path: str, model_path: str, device: str = "cuda") -> dict[str, Any]:
    try:
        from transformers import pipeline
    except Exception as exc:  # pragma: no cover
        raise ImportError("transformers is required for classifier evaluation") from exc

    if str(device).strip().lower() != "cuda":
        raise RuntimeError("GPU-only policy: evaluation supports only device='cuda'")
    try:
        import torch
    except Exception as exc:  # pragma: no cover
        raise ImportError("torch is required for classifier evaluation") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("GPU-only policy: CUDA is required for classifier evaluation")

    rows = _load_jsonl(dataset_path)
    clf = pipeline("text-classification", model=model_path, tokenizer=model_path, device=0, truncation=True)

    def predict(text: str) -> str:
        out = clf(text)
        if isinstance(out, list) and out and isinstance(out[0], dict):
            return str(out[0].get("label") or "")
        return ""

    metrics = evaluate_rows(rows, predict)
    return {
        "dataset_path": dataset_path,
        "model_path": model_path,
        "device": "cuda",
        "metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CEFR DeBERTa classifier on JSONL dataset.")
    parser.add_argument("--dataset-path", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output-path", default="")
    parser.add_argument("--device", default="cuda", choices=["cuda"])
    args = parser.parse_args()

    result = evaluate_deberta(dataset_path=args.dataset_path, model_path=args.model_path, device=args.device)
    output_path = str(args.output_path or "").strip()
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
