"""Evaluate rle_v7 model on the v29 test set."""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

os.chdir("/home/vlad/Dev/FYP_LLM")
sys.path.insert(0, "/home/vlad/Dev/FYP_LLM")

MODEL_DIR = "artifacts/models/t5_notes_rle_v8_large/best_model"
TEST_FILE = "data/processed_t5_v29_book_pairs/test.jsonl"
MAX_INPUT = 512
MAX_TARGET = 128


def _lcs_len(a, b):
    if not a or not b:
        return 0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, wa in enumerate(a, 1):
        for j, wb in enumerate(b, 1):
            dp[i][j] = dp[i-1][j-1] + 1 if wa == wb else max(dp[i-1][j], dp[i][j-1])
    return dp[len(a)][len(b)]


def rouge_l(pred: str, ref: str) -> float:
    p, r = pred.lower().split(), ref.lower().split()
    if not p or not r:
        return 0.0
    lcs = _lcs_len(p, r)
    prec, rec = lcs / len(p), lcs / len(r)
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def main() -> None:
    print("Loading model…", flush=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tok = T5Tokenizer.from_pretrained(MODEL_DIR)
    mdl = T5ForConditionalGeneration.from_pretrained(MODEL_DIR).to(device)
    mdl.eval()

    rows = [json.loads(l) for l in Path(TEST_FILE).read_text().splitlines() if l.strip()]
    print(f"Test examples: {len(rows)}\n", flush=True)

    by_type = defaultdict(list)
    for row in rows:
        by_type[row["node_type"]].append(row)

    for node_type, examples in sorted(by_type.items()):
        print(f"\n{'='*70}", flush=True)
        print(f"NODE TYPE: {node_type}  ({len(examples)} examples)", flush=True)
        print(f"{'='*70}", flush=True)

        scored = []
        by_topic = defaultdict(list)

        for i, ex in enumerate(examples):
            if i % 20 == 0:
                print(f"  {i}/{len(examples)}…", flush=True)
            enc = tok(ex["input"], return_tensors="pt", truncation=True, max_length=MAX_INPUT)
            enc = {k: v.to(device) for k, v in enc.items()}
            with torch.no_grad():
                out = mdl.generate(**enc, max_length=MAX_TARGET, num_beams=4)
            pred = tok.decode(out[0], skip_special_tokens=True).strip()
            score = rouge_l(pred, ex["target"])
            topic = ex.get("topic_key") or ex.get("service_fields", {}).get("part_of_speech", "?")
            scored.append({"score": score, "pred": pred, "ref": ex["target"], "topic": topic})
            by_topic[topic].append(score)

        scores = [s["score"] for s in scored]
        avg = sum(scores) / len(scores) if scores else 0
        print(f"\nROUGE-L  avg={avg:.3f}  min={min(scores):.3f}  max={max(scores):.3f}", flush=True)

        if len(by_topic) > 1:
            print("Per-topic ROUGE-L:")
            for t, ts in sorted(by_topic.items(), key=lambda x: -sum(x[1]) / len(x[1])):
                print(f"  {t:35s} avg={sum(ts)/len(ts):.3f}  n={len(ts)}")

        ss = sorted(scored, key=lambda x: x["score"])
        n = len(ss)
        samples = ss[:2] + ss[n//2 - 1: n//2 + 1] + ss[-2:]
        labels = ["WORST", "WORST", "MEDIAN", "MEDIAN", "BEST", "BEST"]
        print("\nSamples (WORST / MEDIAN / BEST):", flush=True)
        for lbl, s in zip(labels, samples):
            print(f"  [{lbl}  {s['score']:.3f}  topic={s['topic']}]")
            print(f"    REF : {s['ref'][:115]}")
            print(f"    PRED: {s['pred'][:115]}")
            print()


if __name__ == "__main__":
    main()
