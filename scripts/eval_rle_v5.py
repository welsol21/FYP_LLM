"""Evaluate rle_v5 model on the test set.

For each node_type (Sentence / Phrase / Word):
  - Run inference on all test examples
  - Compute ROUGE-L against reference target
  - Print worst / median / best examples per node_type
  - Print per-topic breakdown for Sentence and Phrase
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

os.chdir("/home/vlad/Dev/FYP_LLM")
sys.path.insert(0, "/home/vlad/Dev/FYP_LLM")

MODEL_DIR = "artifacts/models/t5_notes_rle_v5/best_model"
TEST_FILE = "data/processed_t5_v25_book_pairs/test.jsonl"
MAX_INPUT = 512
MAX_TARGET = 128


# ── minimal ROUGE-L ──────────────────────────────────────────────────────────

def _lcs_len(a: List[str], b: List[str]) -> int:
    if not a or not b:
        return 0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, wa in enumerate(a, 1):
        for j, wb in enumerate(b, 1):
            dp[i][j] = dp[i-1][j-1] + 1 if wa == wb else max(dp[i-1][j], dp[i][j-1])
    return dp[len(a)][len(b)]


def rouge_l(pred: str, ref: str) -> float:
    p_tok = pred.lower().split()
    r_tok = ref.lower().split()
    if not p_tok or not r_tok:
        return 0.0
    lcs = _lcs_len(p_tok, r_tok)
    prec = lcs / len(p_tok)
    rec  = lcs / len(r_tok)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


# ── inference ────────────────────────────────────────────────────────────────

def load_model(model_dir: str):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tok = T5Tokenizer.from_pretrained(model_dir)
    mdl = T5ForConditionalGeneration.from_pretrained(model_dir).to(device)
    mdl.eval()
    return tok, mdl, device


def generate(tok, mdl, device, input_text: str) -> str:
    enc = tok(input_text, return_tensors="pt", truncation=True, max_length=MAX_INPUT)
    enc = {k: v.to(device) for k, v in enc.items()}
    with torch.no_grad():
        out = mdl.generate(**enc, max_length=MAX_TARGET, num_beams=4)
    return tok.decode(out[0], skip_special_tokens=True).strip()


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Loading model…")
    tok, mdl, device = load_model(MODEL_DIR)

    rows = [json.loads(l) for l in Path(TEST_FILE).read_text().splitlines() if l.strip()]
    print(f"Test examples: {len(rows)}\n")

    by_type: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        by_type[row["node_type"]].append(row)

    for node_type, examples in sorted(by_type.items()):
        print(f"{'='*70}")
        print(f"NODE TYPE: {node_type}  ({len(examples)} examples)")
        print(f"{'='*70}")

        scored: List[dict] = []
        by_topic: Dict[str, List[float]] = defaultdict(list)

        for ex in examples:
            pred = generate(tok, mdl, device, ex["input"])
            score = rouge_l(pred, ex["target"])
            topic = ex.get("topic_key") or ex.get("service_fields", {}).get("part_of_speech", "?")
            scored.append({"score": score, "pred": pred, "ref": ex["target"],
                           "topic": topic, "sentence": ex.get("sentence_text", "")})
            by_topic[topic].append(score)

        scores = [s["score"] for s in scored]
        avg = sum(scores) / len(scores) if scores else 0
        print(f"ROUGE-L  avg={avg:.3f}  min={min(scores):.3f}  max={max(scores):.3f}\n")

        # Per-topic average
        if len(by_topic) > 1:
            print("Per-topic ROUGE-L:")
            for topic, ts in sorted(by_topic.items(), key=lambda x: -sum(x[1])/len(x[1])):
                print(f"  {topic:30s}  avg={sum(ts)/len(ts):.3f}  n={len(ts)}")
            print()

        # Sample: worst 2, median 2, best 2
        scored_sorted = sorted(scored, key=lambda x: x["score"])
        n = len(scored_sorted)
        samples = (
            scored_sorted[:2] +
            scored_sorted[n//2 - 1: n//2 + 1] +
            scored_sorted[-2:]
        )
        labels = ["WORST", "WORST", "MEDIAN", "MEDIAN", "BEST", "BEST"]
        print("Samples (WORST / MEDIAN / BEST):")
        for label, s in zip(labels, samples):
            print(f"  [{label}  ROUGE-L={s['score']:.3f}  topic={s['topic']}]")
            print(f"    REF : {s['ref'][:120]}")
            print(f"    PRED: {s['pred'][:120]}")
            print()


if __name__ == "__main__":
    main()
