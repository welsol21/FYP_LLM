"""GPU-only training entrypoint for DeBERTa classifier (CEFR labels)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import inspect
from typing import Any
import numpy as np


CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"dataset file not found: {path}")
    out: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def train_deberta_classifier(
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

    def normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            text = str(row.get("input") or "").strip()
            label = str(row.get("cefr_label") or "").strip().upper()
            if not text:
                continue
            if label not in CEFR_ORDER:
                continue
            out.append({"text": text, "label": label})
        if not out:
            raise ValueError("No valid samples after normalization")
        return out

    train_norm = normalize(train_rows)
    dev_norm = normalize(dev_rows)

    label_space = [cefr for cefr in CEFR_ORDER if any(r["label"] == cefr for r in train_norm + dev_norm)]
    if len(label_space) < 2:
        raise ValueError(f"Need at least 2 CEFR labels in dataset, got: {label_space}")
    cefr_to_id = {label: idx for idx, label in enumerate(label_space)}
    id_to_cefr = {idx: label for label, idx in cefr_to_id.items()}

    for row in train_norm:
        row["label"] = cefr_to_id[row["label"]]
    for row in dev_norm:
        row["label"] = cefr_to_id[row["label"]]

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def tokenize(batch: dict[str, list[Any]]) -> dict[str, Any]:
        return tokenizer(batch["text"], truncation=True, max_length=max_length)

    train_ds = Dataset.from_list(train_norm).map(tokenize, batched=True)
    dev_ds = Dataset.from_list(dev_norm).map(tokenize, batched=True)

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(cefr_to_id),
        id2label=id_to_cefr,
        label2id=cefr_to_id,
    ).to("cuda")

    # transformers<=4.x uses `evaluation_strategy`, transformers>=5.x uses `eval_strategy`.
    ta_kwargs = {
        "output_dir": output_dir,
        "num_train_epochs": epochs,
        "per_device_train_batch_size": batch_size,
        "per_device_eval_batch_size": batch_size,
        "learning_rate": learning_rate,
        "warmup_ratio": warmup_ratio,
        "max_grad_norm": max_grad_norm,
        "seed": seed,
        "save_strategy": "epoch",
        "logging_steps": 50,
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "greater_is_better": False,
        "report_to": "none",
    }
    ta_params = inspect.signature(TrainingArguments.__init__).parameters
    if "eval_strategy" in ta_params:
        ta_kwargs["eval_strategy"] = "epoch"
    else:
        ta_kwargs["evaluation_strategy"] = "epoch"

    args = TrainingArguments(**ta_kwargs)

    def compute_metrics(eval_pred: Any) -> dict[str, float]:
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        labels = np.asarray(labels)
        preds = np.asarray(preds)
        accuracy = float((preds == labels).mean()) if len(labels) else 0.0

        f1_scores: list[float] = []
        for class_id in sorted(set(labels.tolist()) | set(preds.tolist())):
            tp = int(((preds == class_id) & (labels == class_id)).sum())
            fp = int(((preds == class_id) & (labels != class_id)).sum())
            fn = int(((preds != class_id) & (labels == class_id)).sum())
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 0.0 if precision + recall == 0 else (2 * precision * recall / (precision + recall))
            f1_scores.append(f1)
        macro_f1 = float(sum(f1_scores) / len(f1_scores)) if f1_scores else 0.0
        return {"accuracy": accuracy, "macro_f1": macro_f1}

    trainer = Trainer(
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
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    summary = {
        "output_dir": output_dir,
        "model_name": model_name,
        "label_space": label_space,
        "train_samples": len(train_norm),
        "dev_samples": len(dev_norm),
        "metrics": metrics,
    }
    summary_path = Path(output_dir) / "train_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train DeBERTa classifier for CEFR labels (GPU-only).")
    parser.add_argument("--train-path", default="data/processed_classifier/train_classifier.jsonl")
    parser.add_argument("--dev-path", default="data/processed_classifier/dev_classifier.jsonl")
    parser.add_argument("--output-dir", default="artifacts/models/deberta_classifier_cefr")
    parser.add_argument("--model-name", default="microsoft/deberta-v3-base")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--warmup-ratio", type=float, default=0.06)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--device", default="cuda", choices=["cuda"])
    args = parser.parse_args()

    summary = train_deberta_classifier(
        train_path=args.train_path,
        dev_path=args.dev_path,
        output_dir=args.output_dir,
        model_name=args.model_name,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        max_grad_norm=args.max_grad_norm,
        seed=args.seed,
        max_length=args.max_length,
        device=args.device,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
