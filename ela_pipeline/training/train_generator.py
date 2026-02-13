"""Unified T5 training entrypoint for linguistic notes generation."""

from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
from typing import Dict, List

import numpy as np
from datasets import Dataset
from transformers import (
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    T5ForConditionalGeneration,
    T5Tokenizer,
    set_seed,
)


def load_jsonl(path: str) -> List[Dict[str, str]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def save_json(path: str, payload: Dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)


def _validate_processed_rows(rows: List[Dict[str, str]], split: str) -> None:
    if not rows:
        raise ValueError(f"{split} dataset is empty")
    required_fields = {"input", "target", "level", "tam_bucket", "prompt_template_version"}
    for idx, row in enumerate(rows[:200]):
        missing = required_fields.difference(row.keys())
        if missing:
            raise ValueError(
                f"{split} dataset is incompatible with current pipeline; "
                f"missing fields {sorted(missing)} in row {idx}"
            )


def _validate_processed_freshness(train_path: str, dev_path: str) -> Dict:
    base_dir = Path(train_path).resolve().parent
    if base_dir != Path(dev_path).resolve().parent:
        raise ValueError("Train/dev JSONL must come from the same processed directory")
    stats_path = base_dir / "stats.json"
    if not stats_path.exists():
        raise ValueError(f"Missing processed stats file: {stats_path}")
    with open(stats_path, "r", encoding="utf-8") as f:
        stats = json.load(f)
    if stats.get("prompt_template_version") != "v1":
        raise ValueError("Incompatible processed stats: unexpected prompt_template_version")
    if int(stats.get("total_after_balance", 0)) <= 0:
        raise ValueError("Processed stats indicate zero training rows")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Train local T5 generator for linguistic notes")
    parser.add_argument("--train", default="data/processed/train.jsonl")
    parser.add_argument("--dev", default="data/processed/dev.jsonl")
    parser.add_argument("--model-name", default="t5-small")
    parser.add_argument("--output-dir", default="artifacts/models/t5_notes")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-input", type=int, default=512)
    parser.add_argument("--max-target", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    set_seed(args.seed)
    train_rows = load_jsonl(args.train)
    dev_rows = load_jsonl(args.dev)
    _validate_processed_rows(train_rows, split="train")
    _validate_processed_rows(dev_rows, split="dev")
    processed_stats = _validate_processed_freshness(args.train, args.dev)

    tokenizer = T5Tokenizer.from_pretrained(args.model_name)
    model = T5ForConditionalGeneration.from_pretrained(args.model_name)

    train_ds = Dataset.from_list(train_rows)
    dev_ds = Dataset.from_list(dev_rows)

    def preprocess(batch):
        inputs = tokenizer(batch["input"], truncation=True, padding="max_length", max_length=args.max_input)
        labels = tokenizer(batch["target"], truncation=True, padding="max_length", max_length=args.max_target)
        inputs["labels"] = labels["input_ids"]
        return inputs

    train_tok = train_ds.map(preprocess, batched=True, remove_columns=train_ds.column_names)
    dev_tok = dev_ds.map(preprocess, batched=True, remove_columns=dev_ds.column_names)

    def compute_metrics(eval_pred):
        preds, labels = eval_pred
        if isinstance(preds, tuple):
            preds = preds[0]
        if preds.ndim == 3:
            preds = np.argmax(preds, axis=-1)

        preds = np.where(preds >= 0, preds, tokenizer.pad_token_id)
        labels = np.where(labels >= 0, labels, tokenizer.pad_token_id)
        decoded_preds = tokenizer.batch_decode(preds, skip_special_tokens=True)
        decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)

        # lightweight exact-match proxy to avoid hard dependency on metric servers
        matches = sum(1 for p, l in zip(decoded_preds, decoded_labels) if p.strip() == l.strip())
        return {"exact_match": round(matches / max(1, len(decoded_preds)), 4)}

    os.makedirs(args.output_dir, exist_ok=True)
    training_config = {
        "model_name": args.model_name,
        "train_path": args.train,
        "dev_path": args.dev,
        "output_dir": args.output_dir,
        "num_train_rows": len(train_rows),
        "num_dev_rows": len(dev_rows),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "max_input": args.max_input,
        "max_target": args.max_target,
        "learning_rate": args.learning_rate,
        "seed": args.seed,
        "processed_stats_path": str((Path(args.train).resolve().parent / "stats.json")),
        "processed_total_after_balance": int(processed_stats.get("total_after_balance", 0)),
    }
    save_json(os.path.join(args.output_dir, "training_config.json"), training_config)

    training_args = Seq2SeqTrainingArguments(
        output_dir=os.path.join(args.output_dir, "trainer_output"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        seed=args.seed,
        data_seed=args.seed,
        eval_strategy="steps",
        eval_steps=200,
        save_strategy="steps",
        save_steps=200,
        logging_steps=100,
        save_total_limit=3,
        predict_with_generate=True,
        generation_max_length=args.max_target,
        report_to="none",
    )

    trainer_kwargs = {
        "model": model,
        "args": training_args,
        "train_dataset": train_tok,
        "eval_dataset": dev_tok,
        "data_collator": DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model),
        "compute_metrics": compute_metrics,
    }
    trainer_sig = inspect.signature(Seq2SeqTrainer.__init__)
    if "tokenizer" in trainer_sig.parameters:
        trainer_kwargs["tokenizer"] = tokenizer
    elif "processing_class" in trainer_sig.parameters:
        trainer_kwargs["processing_class"] = tokenizer

    trainer = Seq2SeqTrainer(**trainer_kwargs)
    train_output = trainer.train()
    eval_metrics = trainer.evaluate()

    best_model_dir = os.path.join(args.output_dir, "best_model")
    trainer.save_model(best_model_dir)
    tokenizer.save_pretrained(best_model_dir)

    evaluation_report = {
        "train_metrics": {k: float(v) for k, v in train_output.metrics.items() if isinstance(v, (int, float))},
        "eval_metrics": {k: float(v) for k, v in eval_metrics.items() if isinstance(v, (int, float))},
        "best_model_dir": best_model_dir,
        "prompt_template_version": "v1",
    }
    save_json(os.path.join(args.output_dir, "evaluation_report.json"), evaluation_report)
    print(f"Saved model to {best_model_dir}")


if __name__ == "__main__":
    main()
