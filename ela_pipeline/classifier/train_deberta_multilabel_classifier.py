"""GPU-only training entrypoint for DeBERTa multi-label classifier."""

from __future__ import annotations

import argparse
from collections import Counter
import inspect
import json
from pathlib import Path
from typing import Any

import numpy as np


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


def _normalize_rows(rows: list[dict[str, Any]], *, label_field: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("input") or "").strip()
        labels = row.get(label_field)
        if not text or not isinstance(labels, list):
            continue
        normalized = sorted({str(label).strip() for label in labels if str(label).strip()})
        if not normalized:
            continue
        out.append({"text": text, "labels": normalized})
    if not out:
        raise ValueError(f"No valid samples after normalization for label_field={label_field}")
    return out


def _build_label_space(rows: list[dict[str, Any]]) -> list[str]:
    labels: set[str] = set()
    for row in rows:
        labels.update(str(label) for label in row.get("labels") or [])
    return sorted(labels)


def _encode_rows(rows: list[dict[str, Any]], *, label_to_id: dict[str, int]) -> list[dict[str, Any]]:
    encoded: list[dict[str, Any]] = []
    for row in rows:
        vector = [0.0] * len(label_to_id)
        for label in row.get("labels") or []:
            idx = label_to_id.get(str(label))
            if idx is not None:
                vector[idx] = 1.0
        encoded.append({"text": row["text"], "labels": vector})
    return encoded


def _compute_pos_weight(encoded_rows: list[dict[str, Any]], *, num_labels: int, strategy: str) -> list[float]:
    if strategy == "none":
        return [1.0] * num_labels
    if strategy != "balanced":
        raise ValueError(f"Unsupported loss weighting strategy: {strategy}")
    positives = np.zeros(num_labels, dtype=np.float64)
    total = float(len(encoded_rows))
    for row in encoded_rows:
        positives += np.asarray(row["labels"], dtype=np.float64)
    weights: list[float] = []
    for pos in positives.tolist():
        if pos <= 0.0:
            weights.append(1.0)
            continue
        neg = max(total - pos, 0.0)
        # Mild clipping keeps training numerically stable.
        weights.append(float(min(max(neg / pos, 1.0), 20.0)))
    return weights


def _multilabel_metrics(
    logits: np.ndarray,
    labels: np.ndarray,
    *,
    threshold: float,
) -> dict[str, float]:
    probs = 1.0 / (1.0 + np.exp(-logits))
    preds = (probs >= threshold).astype(np.int32)
    if preds.ndim != 2 or labels.ndim != 2:
        return {
            "exact_match": 0.0,
            "micro_f1": 0.0,
            "macro_f1": 0.0,
            "avg_predicted_labels": 0.0,
        }

    # Guarantee at least one label per sample.
    empty_mask = preds.sum(axis=1) == 0
    if np.any(empty_mask):
        top_idx = np.argmax(probs[empty_mask], axis=1)
        preds[empty_mask] = 0
        preds[np.where(empty_mask)[0], top_idx] = 1

    exact_match = float(np.all(preds == labels, axis=1).mean()) if len(labels) else 0.0

    tp = float(np.logical_and(preds == 1, labels == 1).sum())
    fp = float(np.logical_and(preds == 1, labels == 0).sum())
    fn = float(np.logical_and(preds == 0, labels == 1).sum())
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    micro_f1 = 0.0 if precision + recall == 0 else (2 * precision * recall / (precision + recall))

    f1_scores: list[float] = []
    for class_id in range(labels.shape[1]):
        c_tp = float(np.logical_and(preds[:, class_id] == 1, labels[:, class_id] == 1).sum())
        c_fp = float(np.logical_and(preds[:, class_id] == 1, labels[:, class_id] == 0).sum())
        c_fn = float(np.logical_and(preds[:, class_id] == 0, labels[:, class_id] == 1).sum())
        c_precision = c_tp / (c_tp + c_fp) if (c_tp + c_fp) > 0 else 0.0
        c_recall = c_tp / (c_tp + c_fn) if (c_tp + c_fn) > 0 else 0.0
        c_f1 = 0.0 if c_precision + c_recall == 0 else (2 * c_precision * c_recall / (c_precision + c_recall))
        f1_scores.append(c_f1)
    macro_f1 = float(sum(f1_scores) / len(f1_scores)) if f1_scores else 0.0

    return {
        "exact_match": exact_match,
        "micro_f1": micro_f1,
        "macro_f1": macro_f1,
        "avg_predicted_labels": float(preds.sum(axis=1).mean()) if len(preds) else 0.0,
    }


def _find_best_threshold(logits: np.ndarray, labels: np.ndarray) -> tuple[float, dict[str, float]]:
    best_threshold = 0.5
    best_metrics = _multilabel_metrics(logits, labels, threshold=best_threshold)
    best_score = best_metrics["micro_f1"]
    for threshold in [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]:
        metrics = _multilabel_metrics(logits, labels, threshold=threshold)
        score = metrics["micro_f1"]
        if score > best_score:
            best_score = score
            best_threshold = threshold
            best_metrics = metrics
    return best_threshold, best_metrics


def train_deberta_multilabel_classifier(
    *,
    train_path: str,
    dev_path: str,
    output_dir: str,
    model_name: str = "microsoft/deberta-v3-base",
    epochs: int = 3,
    batch_size: int = 8,
    learning_rate: float = 2e-5,
    warmup_ratio: float = 0.06,
    max_grad_norm: float = 1.0,
    weight_decay: float = 0.01,
    loss_weighting: str = "none",
    label_field: str = "template_ids",
    seed: int = 42,
    max_length: int = 256,
    device: str = "cuda",
) -> dict[str, Any]:
    if str(device).strip().lower() != "cuda":
        raise RuntimeError("GPU-only policy: DeBERTa training supports only device='cuda'")

    try:
        import torch
    except Exception as exc:  # pragma: no cover
        raise ImportError("torch is required for DeBERTa training") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("GPU-only policy: CUDA is required for DeBERTa training")

    try:
        from datasets import Dataset
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            DataCollatorWithPadding,
            Trainer,
            TrainingArguments,
        )
    except Exception as exc:  # pragma: no cover
        raise ImportError("transformers + datasets are required for DeBERTa training") from exc

    train_rows = _load_jsonl(train_path)
    dev_rows = _load_jsonl(dev_path)
    if len(train_rows) == 0 or len(dev_rows) == 0:
        raise ValueError("train/dev datasets must be non-empty")

    train_norm = _normalize_rows(train_rows, label_field=label_field)
    dev_norm = _normalize_rows(dev_rows, label_field=label_field)
    label_space = _build_label_space(train_norm + dev_norm)
    if len(label_space) < 2:
        raise ValueError(f"Need at least 2 labels in dataset for {label_field}, got: {label_space}")

    label_to_id = {label: idx for idx, label in enumerate(label_space)}
    id_to_label = {idx: label for label, idx in label_to_id.items()}

    train_encoded = _encode_rows(train_norm, label_to_id=label_to_id)
    dev_encoded = _encode_rows(dev_norm, label_to_id=label_to_id)
    pos_weight = _compute_pos_weight(train_encoded, num_labels=len(label_space), strategy=loss_weighting)

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def tokenize(batch: dict[str, list[Any]]) -> dict[str, Any]:
        return tokenizer(batch["text"], truncation=True, max_length=max_length)

    train_ds = Dataset.from_list(train_encoded).map(tokenize, batched=True)
    dev_ds = Dataset.from_list(dev_encoded).map(tokenize, batched=True)

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(label_to_id),
        id2label=id_to_label,
        label2id=label_to_id,
        problem_type="multi_label_classification",
    ).to("cuda")

    ta_kwargs = {
        "output_dir": output_dir,
        "num_train_epochs": epochs,
        "per_device_train_batch_size": batch_size,
        "per_device_eval_batch_size": batch_size,
        "learning_rate": learning_rate,
        "warmup_ratio": warmup_ratio,
        "max_grad_norm": max_grad_norm,
        "weight_decay": weight_decay,
        "seed": seed,
        "save_strategy": "epoch",
        "logging_steps": 50,
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_micro_f1",
        "greater_is_better": True,
        "report_to": "none",
    }
    ta_params = inspect.signature(TrainingArguments.__init__).parameters
    if "eval_strategy" in ta_params:
        ta_kwargs["eval_strategy"] = "epoch"
    else:
        ta_kwargs["evaluation_strategy"] = "epoch"

    args = TrainingArguments(**ta_kwargs)

    class MultiLabelTrainer(Trainer):
        def compute_loss(
            self,
            model: Any,
            inputs: dict[str, Any],
            return_outputs: bool = False,
            **kwargs: Any,
        ) -> Any:
            labels = inputs.get("labels")
            model_inputs = {key: value for key, value in inputs.items() if key != "labels"}
            outputs = model(**model_inputs)
            logits = outputs.get("logits")
            if labels is None or logits is None:
                loss = outputs.get("loss")
                return (loss, outputs) if return_outputs else loss
            labels = labels.float()
            weight_tensor = torch.tensor(pos_weight, dtype=logits.dtype, device=logits.device)
            loss_fct = torch.nn.BCEWithLogitsLoss(pos_weight=weight_tensor)
            loss = loss_fct(logits, labels)
            return (loss, outputs) if return_outputs else loss

    def compute_metrics(eval_pred: Any) -> dict[str, float]:
        logits, labels = eval_pred
        labels = np.asarray(labels, dtype=np.int32)
        logits = np.asarray(logits, dtype=np.float32)
        return _multilabel_metrics(logits, labels, threshold=0.5)

    trainer = MultiLabelTrainer(
        **(
            {
                "model": model,
                "args": args,
                "train_dataset": train_ds,
                "eval_dataset": dev_ds,
                "data_collator": DataCollatorWithPadding(tokenizer=tokenizer),
                "compute_metrics": compute_metrics,
            }
            | (
                {"processing_class": tokenizer}
                if "processing_class" in inspect.signature(Trainer.__init__).parameters
                else {"tokenizer": tokenizer}
            )
        )
    )
    trainer.train()
    metrics = trainer.evaluate()
    dev_pred = trainer.predict(dev_ds)
    best_threshold, best_threshold_metrics = _find_best_threshold(
        np.asarray(dev_pred.predictions, dtype=np.float32),
        np.asarray(dev_pred.label_ids, dtype=np.int32),
    )
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    metadata = {
        "task": "template_multilabel_classification",
        "label_field": label_field,
        "label_space": label_space,
        "label_to_id": label_to_id,
        "recommended_threshold": best_threshold,
        "dev_threshold_metrics": best_threshold_metrics,
    }
    (Path(output_dir) / "multilabel_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "output_dir": output_dir,
        "model_name": model_name,
        "label_field": label_field,
        "label_space": label_space,
        "pos_weight": pos_weight,
        "loss_weighting": loss_weighting,
        "train_samples": len(train_encoded),
        "dev_samples": len(dev_encoded),
        "metrics": metrics,
        "recommended_threshold": best_threshold,
        "dev_threshold_metrics": best_threshold_metrics,
    }
    summary_path = Path(output_dir) / "train_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train DeBERTa multi-label classifier (GPU-only).")
    parser.add_argument("--train-path", required=True)
    parser.add_argument("--dev-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-name", default="microsoft/deberta-v3-base")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--warmup-ratio", type=float, default=0.06)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--loss-weighting", choices=["none", "balanced"], default="none")
    parser.add_argument("--label-field", default="template_ids")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--device", default="cuda", choices=["cuda"])
    args = parser.parse_args()

    summary = train_deberta_multilabel_classifier(
        train_path=args.train_path,
        dev_path=args.dev_path,
        output_dir=args.output_dir,
        model_name=args.model_name,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        max_grad_norm=args.max_grad_norm,
        weight_decay=args.weight_decay,
        loss_weighting=args.loss_weighting,
        label_field=args.label_field,
        seed=args.seed,
        max_length=args.max_length,
        device=args.device,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
