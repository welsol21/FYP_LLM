"""Short explicit-GPU comparison for fixed v40 T5-small models."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer
from transformers.utils import logging as transformers_logging

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
transformers_logging.set_verbosity_error()

MAX_INPUT = 128
MAX_TARGET = 96
BATCH_SIZE = 8

MODELS = {
    "template_model": "artifacts/models/t5_small_template_only_v40_fix/best_model",
    "raw_model": "artifacts/models/t5_small_raw_only_v40_fix/best_model",
}

TESTS = {
    "template_test": "data/processed_sentence_seed/seed_preserving_sentence_dataset_v40_paired_template_canonical_template_only_v1/test.jsonl",
    "raw_test": "data/processed_sentence_seed/seed_preserving_sentence_dataset_v40_paired_template_canonical_raw_only_v1/test.jsonl",
}

OUTPUT_PATH = Path("artifacts/models/t5_small_v40_fix_comparison.json")


def _lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, wa in enumerate(a, 1):
        for j, wb in enumerate(b, 1):
            dp[i][j] = dp[i - 1][j - 1] + 1 if wa == wb else max(dp[i - 1][j], dp[i][j - 1])
    return dp[-1][-1]


def rouge_l(pred: str, ref: str) -> float:
    p_tok = pred.lower().split()
    r_tok = ref.lower().split()
    if not p_tok or not r_tok:
        return 0.0
    lcs = _lcs_len(p_tok, r_tok)
    prec = lcs / len(p_tok)
    rec = lcs / len(r_tok)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def load_rows(path: str, limit: int) -> list[dict]:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return rows[:limit] if limit > 0 else rows


def batched_predictions(
    rows: list[dict],
    tokenizer: T5Tokenizer,
    model: T5ForConditionalGeneration,
    device: torch.device,
    label: str,
) -> list[str]:
    preds: list[str] = []
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx, start in enumerate(range(0, len(rows), BATCH_SIZE), 1):
        batch = rows[start : start + BATCH_SIZE]
        enc = tokenizer(
            [row["input"] for row in batch],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_INPUT,
        )
        enc = {key: value.to(device) for key, value in enc.items()}
        with torch.no_grad():
            out = model.generate(**enc, max_length=MAX_TARGET, num_beams=4)
        preds.extend(text.strip() for text in tokenizer.batch_decode(out, skip_special_tokens=True))
        print(f"{label}: batch {batch_idx}/{total_batches}", flush=True)
    return preds


def summarize(rows: list[dict], preds: list[str]) -> dict:
    scores = [rouge_l(pred, row["target"]) for pred, row in zip(preds, rows)]
    total = len(rows)
    return {
        "n": total,
        "avg_rouge_l": round(sum(scores) / total, 6),
        "non_empty_rate": round(sum(1 for pred in preds if pred) / total, 6),
        "exact_match": round(sum(1 for pred, row in zip(preds, rows) if pred == row["target"]) / total, 6),
        "samples": [
            {
                "input": rows[i]["input"],
                "target": rows[i]["target"],
                "pred": preds[i],
                "rouge_l": round(scores[i], 6),
            }
            for i in range(min(3, total))
        ],
    }


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(
        json.dumps(
            {
                "cuda_available": torch.cuda.is_available(),
                "device": str(device),
                "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
                "limit_per_split": limit,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    summary: dict[str, dict] = {}
    for model_name, model_dir in MODELS.items():
        print(f"loading_model: {model_name} from {model_dir}", flush=True)
        started = time.time()
        tokenizer = T5Tokenizer.from_pretrained(model_dir)
        model = T5ForConditionalGeneration.from_pretrained(model_dir).to(device)
        model.eval()
        print(f"loaded_model: {model_name} in {time.time() - started:.2f}s", flush=True)
        for test_name, test_path in TESTS.items():
            key = f"{model_name}__{test_name}"
            rows = load_rows(test_path, limit)
            print(f"running: {key} rows={len(rows)}", flush=True)
            started = time.time()
            preds = batched_predictions(rows, tokenizer, model, device, key)
            summary[key] = summarize(rows, preds)
            summary[key]["runtime_sec"] = round(time.time() - started, 3)
            OUTPUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
            print(json.dumps({key: summary[key]}, ensure_ascii=False), flush=True)
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    print(f"saved: {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
