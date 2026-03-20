"""Evaluate DeBERTa multi-label classifier and show rendered template-note inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from ela_pipeline.annotate.template_registry import TEMPLATE_VARIANTS


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


def _load_metadata(model_path: str) -> dict[str, Any]:
    path = Path(model_path) / "multilabel_metadata.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    config_path = Path(model_path) / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"Missing metadata file: {path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    id2label = config.get("id2label") or {}
    label_space = [str(id2label[str(i)]) for i in sorted(int(key) for key in id2label.keys())] if id2label else []
    if not label_space:
        raise FileNotFoundError(f"Missing metadata file: {path}")
    return {
        "label_space": label_space,
        "recommended_threshold": 0.5,
    }


def _render_template_preview(template_id: str) -> str:
    variants = TEMPLATE_VARIANTS.get(template_id) or []
    if not variants:
        return ""
    text = str(variants[0]).replace("{content}", "this phrase")
    return " ".join(text.split())


def _predict_rows(
    rows: list[dict[str, Any]],
    *,
    model_path: str,
    threshold: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        import torch
    except Exception as exc:  # pragma: no cover
        raise ImportError("torch is required for multi-label evaluation") from exc
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except Exception as exc:  # pragma: no cover
        raise ImportError("transformers is required for multi-label evaluation") from exc

    if not torch.cuda.is_available():
        raise RuntimeError("GPU-only policy: CUDA is required for multi-label evaluation")

    metadata = _load_metadata(model_path)
    label_space = [str(x) for x in metadata.get("label_space") or []]
    label_to_id = {label: idx for idx, label in enumerate(label_space)}
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path).to("cuda")
    model.eval()

    exact_match = 0
    total = 0
    tp = fp = fn = 0
    label_tp = {label: 0 for label in label_space}
    label_fp = {label: 0 for label in label_space}
    label_fn = {label: 0 for label in label_space}
    sample_predictions: list[dict[str, Any]] = []

    for row in rows:
        text = str(row.get("input") or "").strip()
        gold = sorted({str(x).strip() for x in row.get("template_ids") or [] if str(x).strip()})
        if not text or not gold:
            continue

        enc = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
        enc = {k: v.to("cuda") for k, v in enc.items()}
        with torch.no_grad():
            logits = model(**enc).logits[0].detach().cpu().numpy()
        probs = 1.0 / (1.0 + np.exp(-logits))
        pred = [label_space[i] for i, p in enumerate(probs.tolist()) if p >= threshold]
        if not pred:
            pred = [label_space[int(np.argmax(probs))]]
        pred = sorted(set(pred))

        gold_set = set(gold)
        pred_set = set(pred)
        if gold_set == pred_set:
            exact_match += 1
        total += 1

        for label in label_space:
            in_gold = label in gold_set
            in_pred = label in pred_set
            if in_gold and in_pred:
                tp += 1
                label_tp[label] += 1
            elif in_pred and not in_gold:
                fp += 1
                label_fp[label] += 1
            elif in_gold and not in_pred:
                fn += 1
                label_fn[label] += 1

        if len(sample_predictions) < 20:
            top_scores = sorted(
                [
                    {"template_id": label_space[i], "score": float(probs[i])}
                    for i in range(len(label_space))
                ],
                key=lambda item: item["score"],
                reverse=True,
            )[:8]
            sample_predictions.append(
                {
                    "sentence_text": row.get("sentence_text"),
                    "gold_template_ids": gold,
                    "pred_template_ids": pred,
                    "gold_sentence_template_ids": row.get("sentence_template_ids") or [],
                    "gold_phrase_template_ids": row.get("phrase_template_ids") or [],
                    "pred_rendered_notes": [
                        {"template_id": tid, "note": _render_template_preview(tid)}
                        for tid in pred
                    ],
                    "top_scores": top_scores,
                }
            )

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    micro_f1 = 0.0 if precision + recall == 0 else (2 * precision * recall / (precision + recall))

    macro_scores: list[float] = []
    per_label: dict[str, dict[str, float]] = {}
    for label in label_space:
        l_tp = label_tp[label]
        l_fp = label_fp[label]
        l_fn = label_fn[label]
        l_precision = l_tp / (l_tp + l_fp) if (l_tp + l_fp) > 0 else 0.0
        l_recall = l_tp / (l_tp + l_fn) if (l_tp + l_fn) > 0 else 0.0
        l_f1 = 0.0 if l_precision + l_recall == 0 else (2 * l_precision * l_recall / (l_precision + l_recall))
        per_label[label] = {
            "precision": l_precision,
            "recall": l_recall,
            "f1": l_f1,
            "support": float(l_tp + l_fn),
        }
        macro_scores.append(l_f1)

    result = {
        "dataset_path": str(Path(rows[0].get("_dataset_path", "")).resolve()) if rows and rows[0].get("_dataset_path") else "",
        "model_path": model_path,
        "threshold": threshold,
        "metrics": {
            "samples": total,
            "exact_match": (exact_match / total) if total else 0.0,
            "micro_precision": precision,
            "micro_recall": recall,
            "micro_f1": micro_f1,
            "macro_f1": (sum(macro_scores) / len(macro_scores)) if macro_scores else 0.0,
        },
        "per_label": per_label,
        "sample_predictions": sample_predictions,
    }
    return sample_predictions, result


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate DeBERTa multi-label classifier.")
    parser.add_argument("--dataset-path", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--threshold", type=float, default=-1.0)
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()

    rows = _load_jsonl(args.dataset_path)
    for row in rows:
        row["_dataset_path"] = args.dataset_path
    metadata = _load_metadata(args.model_path)
    threshold = float(args.threshold)
    if threshold <= 0.0:
        threshold = float(metadata.get("recommended_threshold") or 0.5)
    _, result = _predict_rows(rows, model_path=args.model_path, threshold=threshold)

    if args.output_path:
        out = Path(args.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
