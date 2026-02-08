#!/usr/bin/env python3
"""
T5 Training Script — Sentence + Phrase + Word levels
Compatible with transformers 5.x
"""

import argparse
import json
import os
import sys
import logging
from typing import List, Dict, Any, Optional, Sequence

import torch
import pandas as pd
import numpy as np
from datasets import Dataset
from evaluate import load
from transformers import (
    T5Tokenizer,
    T5ForConditionalGeneration,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    TrainerCallback,
)
from transformers.trainer_utils import get_last_checkpoint


# =========================
# CONFIG
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, "linguistic_hierarchical_3000_v3.json")

MODEL_NAME = "t5-small"
MAX_INPUT_LENGTH = 512
MAX_TARGET_LENGTH = 128
TRAINING_EPOCHS = 3
BATCH_SIZE = 8
RANDOM_SEED = 42

RESULTS_DIR = os.path.join(BASE_DIR, "results_llm_notes_v3_t5-small_phrase")
TRAINER_OUTPUT_DIR = os.path.join(RESULTS_DIR, "trainer_output")
BEST_MODEL_DIR = os.path.join(RESULTS_DIR, "best_model")
HF_LOG_DIR = os.path.join(RESULTS_DIR, "hf_logs")
LOG_FILE = os.path.join(RESULTS_DIR, "train.log")

os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(TRAINER_OUTPUT_DIR, exist_ok=True)
os.makedirs(BEST_MODEL_DIR, exist_ok=True)
os.makedirs(HF_LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")],
    force=True,
)

metric = load("rouge")


# =========================
# HELPERS
# =========================
def format_feature_list(features: List[str]) -> str:
    return ", ".join(features).replace("|", ":")


def extract_llm_data(data: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Extract Sentence, Phrase, Word levels.
    """
    records = []

    for sent_data in data:
        features = sent_data.get("features", {})
        targets = sent_data.get("targets", {})

        # Sentence-level
        if targets.get("linguistic_notes"):
            pos_list = format_feature_list(features.get("pos", []))
            dep_list = format_feature_list(features.get("dep", []))
            llm_input = f"pos: {pos_list} dep: {dep_list} sentence: {sent_data.get('input','')}"
            records.append({"input": llm_input, "target": targets["linguistic_notes"], "level": "Sentence"})

        # Phrase-level
        for phrase in sent_data.get("linguistic_elements", []):
            if phrase.get("type") != "Phrase":
                continue
            p_targets = phrase.get("targets", {})
            if not p_targets.get("linguistic_notes"):
                continue

            pf = phrase.get("features", {})
            pos_list = format_feature_list(pf.get("pos", []))
            dep_list = format_feature_list(pf.get("dep", []))
            chunk = (pf.get("chunk", ["UNKNOWN"]) or ["UNKNOWN"])[0]
            phrase_text = phrase.get("input", "")

            llm_input = (
                f"pos: {pos_list} dep: {dep_list} chunk: {chunk} phrase: {phrase_text}"
            )
            records.append({"input": llm_input, "target": p_targets["linguistic_notes"], "level": "Phrase"})

        # Word-level
        for word in sent_data.get("linguistic_elements", []):
            if word.get("type") != "Word":
                continue
            w_targets = word.get("targets", {})
            if not w_targets.get("linguistic_notes"):
                continue

            wf = word.get("features", {})
            pos = (wf.get("pos", ["UNKNOWN"]) or ["UNKNOWN"])[0]
            tag = (wf.get("tag", ["UNKNOWN"]) or ["UNKNOWN"])[0]
            dep = (wf.get("dep", ["UNKNOWN"]) or ["UNKNOWN"])[0]
            morph = format_feature_list(wf.get("morph", []))
            word_text = word.get("input", "")

            llm_input = (
                f"pos: {pos} tag: {tag} dep: {dep} morph: {morph} word: {word_text}"
            )
            records.append({"input": llm_input, "target": w_targets["linguistic_notes"], "level": "Word"})

    return pd.DataFrame(records)


# =========================
# METRICS
# =========================
def compute_metrics(eval_pred):
    preds, labels = eval_pred

    # Convert logits → token IDs
    if preds.ndim == 3:  # (batch, seq, vocab)
        preds = np.argmax(preds, axis=-1)

    # Sanitize token IDs
    preds = np.where((preds >= 0) & (preds < tokenizer.vocab_size), preds, tokenizer.pad_token_id)
    labels = np.where((labels >= 0) & (labels < tokenizer.vocab_size), labels, tokenizer.pad_token_id)

    decoded_preds = tokenizer.batch_decode(preds, skip_special_tokens=True)
    decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)

    decoded_preds = [" ".join(p.split()) for p in decoded_preds]
    decoded_labels = [" ".join(l.split()) for l in decoded_labels]

    result = metric.compute(
        predictions=decoded_preds,
        references=decoded_labels,
        use_stemmer=True,
    )

    return {k: round(v * 100, 4) for k, v in result.items()}


# =========================
# MAIN
# =========================
def main():
    global tokenizer

    logging.info("Loading dataset...")
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    df = extract_llm_data(data)
    logging.info(f"Extracted: {len(df)} examples")
    logging.info(df["level"].value_counts())

    dataset = Dataset.from_pandas(df)
    split = dataset.train_test_split(test_size=0.2, seed=RANDOM_SEED)
    train_dataset = split["train"]
    eval_dataset = split["test"]

    tokenizer = T5Tokenizer.from_pretrained(MODEL_NAME)
    model = T5ForConditionalGeneration.from_pretrained(MODEL_NAME)

    def tokenize_fn(ex):
        model_inputs = tokenizer(
            ex["input"], truncation=True, padding="max_length", max_length=MAX_INPUT_LENGTH
        )
        labels = tokenizer(
            ex["target"], truncation=True, padding="max_length", max_length=MAX_TARGET_LENGTH
        )
        model_inputs["labels"] = labels["input_ids"]
        return model_inputs

    tokenized_train = train_dataset.map( 
        tokenize_fn, 
        batched=True, 
        remove_columns=["input", "target", "level"] 
    )
    tokenized_eval = eval_dataset.map( 
        tokenize_fn,
        batched=True,
        remove_columns=["input", "target", "level"] 
    )

    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)

    args = Seq2SeqTrainingArguments(
        output_dir=TRAINER_OUTPUT_DIR,
        num_train_epochs=TRAINING_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        save_strategy="steps",
        save_steps=500,
        eval_strategy="steps",
        eval_steps=500,
        logging_steps=500,
        save_total_limit=3,
        predict_with_generate=True,
        generation_max_length=MAX_TARGET_LENGTH,
        report_to="none",
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_eval,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    last_ckpt = get_last_checkpoint(TRAINER_OUTPUT_DIR)
    trainer.train(resume_from_checkpoint=last_ckpt)

    trainer.save_model(BEST_MODEL_DIR)
    tokenizer.save_pretrained(BEST_MODEL_DIR)

    logging.info("DONE")


if __name__ == "__main__":
    main()
