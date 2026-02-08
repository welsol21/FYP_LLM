# filepath: /home/vlad/Dev/FYP_LLM/train_llm_1_linguistic_notes_base_cuda.py
#!/usr/bin/env python3
"""
===========================================================
T5 Training Script — FULL DATA + ROUGE (FIXED & STABLE)
- Compatible with transformers versions around 4.x
- Guaranteed checkpoints even if metrics fail
- Robust ROUGE computation (handles both aggregated float and Score.mid)
- Best model selection by eval_rougeL without crashes
- save BEFORE eval (save_steps <= eval_steps)
===========================================================
"""
import argparse
import json
import os
import sys
import logging
from typing import List, Dict, Any, Optional, Sequence

# =========================
# STEP 1. Config
# =========================
DEBUG_WRITE_TEST = False  # FULL DATA

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, "linguistic_hierarchical_3000_v3.json")

MODEL_NAME = "t5-small"

MAX_INPUT_LENGTH = 512
MAX_TARGET_LENGTH = 128
TRAINING_EPOCHS = 3
BATCH_SIZE = 8
RANDOM_SEED = 42

# Save first, eval later -> checkpoint survives metric crashes
FULL_SAVE_STEPS = 500
FULL_EVAL_STEPS = 500
FULL_LOGGING_STEPS = 500
SAVE_TOTAL_LIMIT = 3

MODEL_TAG = MODEL_NAME.replace("/", "_")
RESULTS_DIR = os.path.join(BASE_DIR, f"results_llm_notes_v3_{MODEL_TAG}_cuda")
TRAINER_OUTPUT_DIR = os.path.join(RESULTS_DIR, "trainer_output")
BEST_MODEL_DIR = os.path.join(RESULTS_DIR, "best_model")
HF_LOG_DIR = os.path.join(RESULTS_DIR, "hf_logs")
LOG_FILE = os.path.join(RESULTS_DIR, "train.log")

os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(TRAINER_OUTPUT_DIR, exist_ok=True)
os.makedirs(BEST_MODEL_DIR, exist_ok=True)
os.makedirs(HF_LOG_DIR, exist_ok=True)

# =========================
# Arg parsing (early so we can set CUDA env before heavy imports)
# =========================
def parse_args():
    parser = argparse.ArgumentParser(description="Train LLM with CUDA/venv helpers")
    parser.add_argument("--cuda-device", type=str, default=None,
                        help="Comma-separated CUDA_VISIBLE_DEVICES (e.g. '0' or '0,1').")
    parser.add_argument("--no-cuda", action="store_true", help="Force CPU (clears CUDA_VISIBLE_DEVICES).")
    parser.add_argument("--verbose-env-check", action="store_true", help="Print venv/CUDA info and exit.")
    parser.add_argument("--venv-exit", action="store_true", help="Exit if not running inside a virtualenv.")
    return parser.parse_args()

args = parse_args()

# Configure CUDA env BEFORE importing torch/transformers
if args.cuda_device is not None:
    os.environ["CUDA_VISIBLE_DEVICES"] = args.cuda_device
if args.no_cuda:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

def ensure_venv(exit_if_missing=False):
    in_venv = ("VIRTUAL_ENV" in os.environ) or (hasattr(sys, "real_prefix")) or (sys.prefix != getattr(sys, "base_prefix", None))
    if not in_venv:
        msg = (
            "Warning: not running inside a virtualenv. Recommended:\n"
            "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        )
        print(msg, file=sys.stderr)
        if exit_if_missing:
            sys.exit(1)
    return in_venv

if args.verbose_env_check:
    print("Python executable:", sys.executable)
    print("VIRTUAL_ENV:", os.environ.get("VIRTUAL_ENV"))
    print("sys.prefix:", sys.prefix)
    print("CUDA_VISIBLE_DEVICES:", os.environ.get("CUDA_VISIBLE_DEVICES"))
    sys.exit(0)

ensure_venv(exit_if_missing=args.venv_exit)

# =========================
# STEP 2. Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")],
    force=True,
)

# heavy imports after env & logging
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
import transformers

SCRIPT_VERSION = "2026-01-26_fixed_rouge_checkpoint"
logging.info("=== START TRAINING SCRIPT ===")
logging.info(f"SCRIPT_VERSION = {SCRIPT_VERSION}")
logging.info(f"transformers.__version__ = {transformers.__version__}")
logging.info(f"DEBUG_WRITE_TEST = {DEBUG_WRITE_TEST}")
logging.info(f"__file__ = {os.path.abspath(__file__)}")
logging.info(f"BASE_DIR = {BASE_DIR}")
logging.info(f"CWD = {os.getcwd()}")
logging.info(f"RESULTS_DIR = {RESULTS_DIR}")
logging.info(f"TRAINER_OUTPUT_DIR = {TRAINER_OUTPUT_DIR}")
logging.info(f"BEST_MODEL_DIR = {BEST_MODEL_DIR}")
logging.info(f"LOG_FILE = {LOG_FILE}")
logging.info(
    f"FULL_SAVE_STEPS = {FULL_SAVE_STEPS}, FULL_EVAL_STEPS = {FULL_EVAL_STEPS}"
)

# =========================
# STEP 3. CUDA / device selection
# =========================
gpu_available = torch.cuda.is_available() and (not args.no_cuda)
device = torch.device("cuda" if gpu_available else "cpu")
logging.info(f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')}, gpu_available={gpu_available}, device={device}")

# =========================
# STEP 4. Data extraction (без изменений)
# =========================
def format_feature_list(features: List[str]) -> str:
    return ", ".join(features).replace("|", ":")


def extract_llm_data(data: List[Dict[str, Any]]) -> pd.DataFrame:
    records: List[Dict[str, str]] = []

    for sent_data in data:
        features = sent_data.get("features", {})
        targets = sent_data.get("targets", {})
        if targets.get("linguistic_notes"):
            input_text = sent_data.get("input", "")
            notes = targets["linguistic_notes"]
            pos_list = format_feature_list(features.get("pos", []))
            dep_list = format_feature_list(features.get("dep", []))
            llm_input = f"pos: {pos_list} dep: {dep_list} sentence: {input_text}"
            records.append({"input": llm_input, "target": notes, "level": "Sentence"})

        for word_data in sent_data.get("linguistic_elements", []):
            if word_data.get("type") != "Word":
                continue
            w_targets = word_data.get("targets", {})
            if not w_targets.get("linguistic_notes"):
                continue
            wf = word_data.get("features", {})
            word_input = word_data.get("input", "")
            notes = w_targets["linguistic_notes"]
            pos = (wf.get("pos", ["UNKNOWN"]) or ["UNKNOWN"])[0]
            tag = (wf.get("tag", ["UNKNOWN"]) or ["UNKNOWN"])[0]
            dep = (wf.get("dep", ["UNKNOWN"]) or ["UNKNOWN"])[0]
            morph = format_feature_list(wf.get("morph", []))
            llm_input = (
                f"pos: {pos} tag: {tag} dep: {dep} morph: {morph} word: {word_input}"
            )
            records.append({"input": llm_input, "target": notes, "level": "Word"})

    return pd.DataFrame(records)


# =========================
# STEP 5. Tokenizer + tokenization (без изменений)
# =========================
tokenizer = T5Tokenizer.from_pretrained(MODEL_NAME)
logging.info(f"Tokenizer loaded: {MODEL_NAME}")

model = T5ForConditionalGeneration.from_pretrained(MODEL_NAME).to(device) 
logging.info(f"Model loaded: {MODEL_NAME}")


def _tokenizer_vocab_size() -> int:
    sp = getattr(tokenizer, "sp_model", None)
    if sp is not None:
        if hasattr(sp, "GetPieceSize"):
            return int(sp.GetPieceSize())
        if hasattr(sp, "get_piece_size"):
            return int(sp.get_piece_size())
    return int(tokenizer.vocab_size)


TOKENIZER_VOCAB = _tokenizer_vocab_size()
PAD_ID = int(tokenizer.pad_token_id)
logging.info(f"Tokenizer vocab size = {TOKENIZER_VOCAB}, pad_token_id = {PAD_ID}")


def tokenize_function(examples: Dict[str, List[str]]) -> Dict[str, Any]:
    model_inputs = tokenizer(
        examples["input"],
        max_length=MAX_INPUT_LENGTH,
        truncation=True,
        padding="max_length",
    )
    labels = tokenizer(
        examples["target"],
        max_length=MAX_TARGET_LENGTH,
        truncation=True,
        padding="max_length",
    )
    model_inputs["labels"] = labels["input_ids"]
    return model_inputs


# =========================
# STEP 6. Metrics (ROUGE) — FIXED VERSION
# =========================
metric = load("rouge")
logging.info("ROUGE metric loaded")


def _pad_2d(seqs: Sequence[Sequence[int]], pad_value: int) -> np.ndarray:
    max_len = max((len(s) for s in seqs), default=0)
    out = np.full((len(seqs), max_len), pad_value, dtype=np.int64)
    for i, s in enumerate(seqs):
        if not s:
            continue
        out[i, : len(s)] = np.asarray(s, dtype=np.int64)
    return out


def _normalize_pred_ids(preds: Any) -> np.ndarray:
    if isinstance(preds, tuple):
        preds = preds[0]

    arr = np.array(preds)

    if arr.ndim == 3 and arr.shape[-1] == TOKENIZER_VOCAB:
        arr = np.argmax(arr, axis=-1)

    if arr.ndim == 3:
        arr = arr[:, 0, :]

    if arr.ndim == 1 and len(arr) > 0 and isinstance(arr[0], (list, tuple, np.ndarray)):
        seqs = [list(map(int, x)) for x in arr]
        arr = _pad_2d(seqs, PAD_ID)

    if arr.dtype == object:
        seqs = []
        for row in arr:
            if isinstance(row, (list, tuple, np.ndarray)):
                seqs.append([int(t) for t in row])
            else:
                seqs.append([int(row)])
        arr = _pad_2d(seqs, PAD_ID)

    return arr.astype(np.int64, copy=False)


def _sanitize_ids(ids_2d: np.ndarray) -> np.ndarray:
    return np.where((ids_2d >= 0) & (ids_2d < TOKENIZER_VOCAB), ids_2d, PAD_ID)


def compute_metrics(eval_pred):
    """
    Fail-safe ROUGE computation:
    - Handles both dict[str, float] (new evaluate) and dict[str, Score] (old)
    - Never crashes training
    """
    try:
        preds, labels = eval_pred

        pred_ids = _normalize_pred_ids(preds)
        pred_ids = _sanitize_ids(pred_ids)

        lab_ids = _normalize_pred_ids(labels)
        lab_ids = _sanitize_ids(lab_ids)

        decoded_preds = tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
        decoded_labels = tokenizer.batch_decode(lab_ids, skip_special_tokens=True)

        # Best practice for ROUGE: join words with space, no extra newlines
        decoded_preds = [" ".join(p.strip().split()) for p in decoded_preds]
        decoded_labels = [" ".join(l.strip().split()) for l in decoded_labels]

        result = metric.compute(
            predictions=decoded_preds,
            references=decoded_labels,
            use_stemmer=True,
        )

        scores = {}
        for k, v in result.items():
            if hasattr(v, "mid"):  # old style: rouge_score.Score
                scores[k] = v.mid.fmeasure * 100
            elif isinstance(v, (float, np.float64)):  # new style: aggregated mid f1
                scores[k] = float(v) * 100
            elif isinstance(v, np.ndarray):  # rare case
                scores[k] = float(v.mean()) * 100
            else:
                scores[k] = 0.0
                logging.warning(f"Unexpected ROUGE value for {k}: {type(v)}")

        # gen_len on words (more accurate than token count)
        pred_lens = [len(p.split()) for p in decoded_preds]
        scores["gen_len"] = float(np.mean(pred_lens)) if pred_lens else 0.0

        return {k: round(v, 4) for k, v in scores.items()}

    except Exception:
        logging.exception("compute_metrics crashed; continuing WITHOUT metrics.")
        return {}


# =========================
# STEP 6.2 Callback for diagnostics
# =========================
class LogCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs:
            logging.info(
                f"Trainer log | step={state.global_step} | epoch={state.epoch:.3f} | {logs}"
            )

    def on_save(self, args, state, control, **kwargs):
        logging.info(
            f"CHECKPOINT SAVED | step={state.global_step} | dir={args.output_dir}"
        )

    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        if metrics:
            logging.info(f"EVAL DONE | step={state.global_step} | metrics={metrics}")


# =========================
# STEP 7. Main
# =========================
def main() -> None:
    try:
        logging.info(f"Loading dataset from: {FILE_PATH}")
        if not os.path.exists(FILE_PATH):
            logging.error(f"Dataset NOT FOUND: {FILE_PATH}")
            return

        with open(FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        logging.info(f"JSON loaded. Items: {len(data)}")

        df = extract_llm_data(data)
        logging.info(f"Extracted examples: {len(df)}")
        logging.info(f"Level distribution: {df['level'].value_counts().to_dict()}")

        full_dataset = Dataset.from_pandas(df)
        split = full_dataset.train_test_split(test_size=0.2, seed=RANDOM_SEED)
        train_dataset = split["train"]
        eval_dataset = split["test"]
        logging.info(f"Split: train={len(train_dataset)}, eval={len(eval_dataset)}")

        tokenized_train = train_dataset.map(
            tokenize_function,
            batched=True,
            remove_columns=[
                c
                for c in ["input", "target", "level"]
                if c in train_dataset.column_names
            ],
        )
        tokenized_eval = eval_dataset.map(
            tokenize_function,
            batched=True,
            remove_columns=[
                c
                for c in ["input", "target", "level"]
                if c in eval_dataset.column_names
            ],
        )
        logging.info(
            f"Tokenized: train={len(tokenized_train)}, eval={len(tokenized_eval)}"
        )

        data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)

        training_args_kwargs = dict(
            output_dir=TRAINER_OUTPUT_DIR,
            num_train_epochs=TRAINING_EPOCHS,
            per_device_train_batch_size=BATCH_SIZE,
            per_device_eval_batch_size=BATCH_SIZE,
            logging_dir=HF_LOG_DIR,
            logging_steps=FULL_LOGGING_STEPS,
            save_strategy="steps",
            save_steps=FULL_SAVE_STEPS,
            save_total_limit=SAVE_TOTAL_LIMIT,
            eval_strategy="steps",
            eval_steps=FULL_EVAL_STEPS,
            predict_with_generate=True,
            generation_max_length=MAX_TARGET_LENGTH,
            generation_num_beams=1,
            report_to="none",
            use_cpu=(not gpu_available),
        )

        def make_seq2seq_args_safe(kwargs: dict) -> Seq2SeqTrainingArguments:
            import re as _re
            while True:
                try:
                    return Seq2SeqTrainingArguments(**kwargs)
                except TypeError as e:
                    msg = str(e)
                    m = _re.search(r"unexpected keyword argument '?([a-zA-Z0-9_]+)'?", msg)
                    if not m:
                        raise
                    bad = m.group(1)
                    if bad in kwargs:
                        logging.warning(f"Removing unsupported TrainingArguments kwarg: {bad}")
                        kwargs.pop(bad)
                        continue
                    raise

        args_tf = make_seq2seq_args_safe(training_args_kwargs)

        logging.info("FULL mode: eval + ROUGE enabled with generate()")
        logging.info(f"ARGS CHECK: output_dir={args_tf.output_dir}")
        logging.info(
            f"ARGS CHECK: eval_strategy={args_tf.eval_strategy}, eval_steps={args_tf.eval_steps}"
        )
        logging.info(
            f"ARGS CHECK: save_strategy={args_tf.save_strategy}, save_steps={args_tf.save_steps}"
        )

        trainer = Seq2SeqTrainer(
            model=model,
            args=args_tf,
            train_dataset=tokenized_train,
            eval_dataset=tokenized_eval,
            data_collator=data_collator,
            compute_metrics=compute_metrics,
            callbacks=[LogCallback()],
        )

        # Safe resume
        last_ckpt: Optional[str] = get_last_checkpoint(TRAINER_OUTPUT_DIR)
        if last_ckpt:
            logging.info(f"Resume from checkpoint: {last_ckpt}")
            trainer.train(resume_from_checkpoint=last_ckpt)
        else:
            logging.info("No checkpoint found. Start from scratch.")
            trainer.train()

        ckpts = sorted(
            [d for d in os.listdir(TRAINER_OUTPUT_DIR) if d.startswith("checkpoint-")]
        )
        logging.info(f"Checkpoints present: {ckpts}")

        logging.info("Final evaluation")
        final_metrics = trainer.evaluate()
        logging.info(json.dumps(final_metrics, indent=4, ensure_ascii=False))

        logging.info(f"Saving best model to: {BEST_MODEL_DIR}")
        trainer.save_model(BEST_MODEL_DIR)
        tokenizer.save_pretrained(BEST_MODEL_DIR)

        logging.info("=== DONE ===")

    except Exception:
        logging.exception("FATAL: Training script crashed with exception.")
        raise


# =========================
# STEP 8. Entry
# =========================
if __name__ == "__main__":
    main()