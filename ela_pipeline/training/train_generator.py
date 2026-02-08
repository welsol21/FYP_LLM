"""Unified T5 training entrypoint for linguistic notes generation."""

from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List

import numpy as np
from datasets import Dataset
from transformers import (
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    T5ForConditionalGeneration,
    T5Tokenizer,
)


def load_jsonl(path: str) -> List[Dict[str, str]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


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
    args = parser.parse_args()

    train_rows = load_jsonl(args.train)
    dev_rows = load_jsonl(args.dev)

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
    training_args = Seq2SeqTrainingArguments(
        output_dir=os.path.join(args.output_dir, "trainer_output"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
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

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_tok,
        eval_dataset=dev_tok,
        tokenizer=tokenizer,
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model),
        compute_metrics=compute_metrics,
    )
    trainer.train()

    best_model_dir = os.path.join(args.output_dir, "best_model")
    trainer.save_model(best_model_dir)
    tokenizer.save_pretrained(best_model_dir)
    print(f"Saved model to {best_model_dir}")


if __name__ == "__main__":
    main()
