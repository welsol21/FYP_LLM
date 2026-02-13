"""Build train/dev/test JSONL pairs for linguistic notes generation."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from typing import Any, Dict, Iterable, List

TELEMETRY_PATTERNS = (
    re.compile(r"\bquality_flags\b", re.IGNORECASE),
    re.compile(r"\breason_codes\b", re.IGNORECASE),
    re.compile(r"\brejected_candidates\b", re.IGNORECASE),
    re.compile(r"\brejected_candidate_stats\b", re.IGNORECASE),
    re.compile(r"\brejected_[a-z_]+\b", re.IGNORECASE),
)

LOW_QUALITY_NOTE_PATTERNS = (
    re.compile(r"^\s*node content\.?\s*(part of speech)?\.?\s*$", re.IGNORECASE),
    re.compile(r"\bpart of speech\b", re.IGNORECASE),
    re.compile(r"\bverb-?centred phrase expressing what happens to or about the subject\b", re.IGNORECASE),
    re.compile(r"^\s*sentence:\s*", re.IGNORECASE),
)


def format_feature_list(features: List[str]) -> str:
    return ", ".join(features).replace("|", ":")


def _sentence_count(text: str) -> int:
    parts = [p.strip() for p in re.split(r"[.!?]+", text) if p.strip()]
    return len(parts)


def _is_style_compliant(text: str) -> bool:
    for pattern in LOW_QUALITY_NOTE_PATTERNS:
        if pattern.search(text):
            return False
    sentence_n = _sentence_count(text)
    return 1 <= sentence_n <= 2


def _sanitize_training_target_text(text: str) -> str | None:
    clean = text.strip()
    if not clean:
        return None
    for pattern in TELEMETRY_PATTERNS:
        if pattern.search(clean):
            return None
    if not _is_style_compliant(clean):
        return None
    return clean


def _extract_model_note(targets: Dict[str, Any]) -> str | None:
    notes = targets.get("notes")
    if not isinstance(notes, list):
        return None
    for note in notes:
        if not isinstance(note, dict):
            continue
        if note.get("source") != "model":
            continue
        text = note.get("text")
        if isinstance(text, str):
            sanitized = _sanitize_training_target_text(text)
            if sanitized:
                return sanitized
    return None


def iter_examples(item: Dict[str, Any]) -> Iterable[Dict[str, str]]:
    sentence = item.get("input", "")
    sent_features = item.get("features", {})
    sent_targets = item.get("targets", {})

    sentence_note = _extract_model_note(sent_targets)
    if sentence_note:
        prompt = (
            f"sentence: {sentence} "
            f"pos: {format_feature_list(sent_features.get('pos', []))} "
            f"dep: {format_feature_list(sent_features.get('dep', []))}"
        )
        yield {"input": prompt, "target": sentence_note, "level": "Sentence"}

    for phrase in item.get("linguistic_elements", []):
        if phrase.get("type") != "Phrase":
            continue
        p_note = _extract_model_note(phrase.get("targets", {}))
        if p_note:
            pf = phrase.get("features", {})
            prompt = (
                f"sentence: {sentence} "
                f"node_type: Phrase "
                f"phrase: {phrase.get('input', '')} "
                f"pos: {format_feature_list(pf.get('pos', []))} "
                f"dep: {format_feature_list(pf.get('dep', []))}"
            )
            yield {"input": prompt, "target": p_note, "level": "Phrase"}

        for word in phrase.get("linguistic_elements", []):
            if word.get("type") != "Word":
                continue
            w_note = _extract_model_note(word.get("targets", {}))
            if not w_note:
                continue
            wf = word.get("features", {})
            prompt = (
                f"sentence: {sentence} "
                f"node_type: Word "
                f"word: {word.get('input', '')} "
                f"pos: {(wf.get('pos', ['UNKNOWN']) or ['UNKNOWN'])[0]} "
                f"tag: {(wf.get('tag', ['UNKNOWN']) or ['UNKNOWN'])[0]} "
                f"dep: {(wf.get('dep', ['UNKNOWN']) or ['UNKNOWN'])[0]} "
                f"morph: {format_feature_list(wf.get('morph', []))}"
            )
            yield {"input": prompt, "target": w_note, "level": "Word"}


def split_data(rows: List[Dict[str, str]], seed: int, dev_ratio: float, test_ratio: float):
    rng = random.Random(seed)
    data = rows[:]
    rng.shuffle(data)

    total = len(data)
    test_n = int(total * test_ratio)
    dev_n = int(total * dev_ratio)

    test = data[:test_n]
    dev = data[test_n : test_n + dev_n]
    train = data[test_n + dev_n :]
    return train, dev, test


def write_jsonl(rows: List[Dict[str, str]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build train/dev/test JSONL from hierarchical dataset")
    parser.add_argument("--input", default="linguistic_hierarchical_3000_v3.json")
    parser.add_argument("--output-dir", default="data/processed")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows: List[Dict[str, str]] = []
    for item in raw:
        rows.extend(iter_examples(item))

    os.makedirs(args.output_dir, exist_ok=True)
    train, dev, test = split_data(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    write_jsonl(train, os.path.join(args.output_dir, "train.jsonl"))
    write_jsonl(dev, os.path.join(args.output_dir, "dev.jsonl"))
    write_jsonl(test, os.path.join(args.output_dir, "test.jsonl"))

    stats = {
        "total": len(rows),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
    }
    with open(os.path.join(args.output_dir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
