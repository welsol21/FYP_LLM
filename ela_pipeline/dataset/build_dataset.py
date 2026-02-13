"""Build train/dev/test JSONL pairs for linguistic notes generation."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from collections import defaultdict
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

PROMPT_TEMPLATE_VERSION = "v1"


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


def _extract_tam_bucket(node: Dict[str, Any]) -> str:
    direct = node.get("tam_construction")
    if isinstance(direct, str) and direct.strip():
        return direct.strip().lower()
    targets = node.get("targets")
    if isinstance(targets, dict):
        nested = targets.get("tam_construction")
        if isinstance(nested, str) and nested.strip():
            return nested.strip().lower()
    return "none"


def _render_sentence_prompt(sentence: str, pos_text: str, dep_text: str, tam_bucket: str) -> str:
    return (
        f"task: write_linguistic_note "
        f"template_version: {PROMPT_TEMPLATE_VERSION} "
        f"node_type: Sentence "
        f"tam_bucket: {tam_bucket} "
        f"sentence: {sentence} "
        f"pos: {pos_text} "
        f"dep: {dep_text}"
    )


def _render_phrase_prompt(sentence: str, phrase_text: str, pos_text: str, dep_text: str, tam_bucket: str) -> str:
    return (
        f"task: write_linguistic_note "
        f"template_version: {PROMPT_TEMPLATE_VERSION} "
        f"node_type: Phrase "
        f"tam_bucket: {tam_bucket} "
        f"sentence: {sentence} "
        f"phrase: {phrase_text} "
        f"pos: {pos_text} "
        f"dep: {dep_text}"
    )


def _render_word_prompt(
    sentence: str,
    word_text: str,
    pos_text: str,
    tag_text: str,
    dep_text: str,
    morph_text: str,
    tam_bucket: str,
) -> str:
    return (
        f"task: write_linguistic_note "
        f"template_version: {PROMPT_TEMPLATE_VERSION} "
        f"node_type: Word "
        f"tam_bucket: {tam_bucket} "
        f"sentence: {sentence} "
        f"word: {word_text} "
        f"pos: {pos_text} "
        f"tag: {tag_text} "
        f"dep: {dep_text} "
        f"morph: {morph_text}"
    )


def iter_examples(item: Dict[str, Any]) -> Iterable[Dict[str, str]]:
    sentence = item.get("input", "")
    sent_features = item.get("features", {})
    sent_targets = item.get("targets", {})

    sentence_note = _extract_model_note(sent_targets)
    if sentence_note:
        sent_tam = _extract_tam_bucket(item)
        prompt = _render_sentence_prompt(
            sentence=sentence,
            pos_text=format_feature_list(sent_features.get("pos", [])),
            dep_text=format_feature_list(sent_features.get("dep", [])),
            tam_bucket=sent_tam,
        )
        yield {
            "input": prompt,
            "target": sentence_note,
            "level": "Sentence",
            "tam_bucket": sent_tam,
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        }

    for phrase in item.get("linguistic_elements", []):
        if phrase.get("type") != "Phrase":
            continue
        p_note = _extract_model_note(phrase.get("targets", {}))
        if p_note:
            phrase_tam = _extract_tam_bucket(phrase)
            pf = phrase.get("features", {})
            prompt = _render_phrase_prompt(
                sentence=sentence,
                phrase_text=phrase.get("input", ""),
                pos_text=format_feature_list(pf.get("pos", [])),
                dep_text=format_feature_list(pf.get("dep", [])),
                tam_bucket=phrase_tam,
            )
            yield {
                "input": prompt,
                "target": p_note,
                "level": "Phrase",
                "tam_bucket": phrase_tam,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            }

        for word in phrase.get("linguistic_elements", []):
            if word.get("type") != "Word":
                continue
            w_note = _extract_model_note(word.get("targets", {}))
            if not w_note:
                continue
            word_tam = _extract_tam_bucket(word)
            wf = word.get("features", {})
            prompt = _render_word_prompt(
                sentence=sentence,
                word_text=word.get("input", ""),
                pos_text=(wf.get("pos", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                tag_text=(wf.get("tag", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                dep_text=(wf.get("dep", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                morph_text=format_feature_list(wf.get("morph", [])),
                tam_bucket=word_tam,
            )
            yield {
                "input": prompt,
                "target": w_note,
                "level": "Word",
                "tam_bucket": word_tam,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            }


def _count_by(rows: List[Dict[str, str]], key_fn) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[key_fn(row)] += 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _count_level_tam(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        level = row.get("level", "Unknown")
        tam = row.get("tam_bucket", "none")
        matrix[level][tam] += 1
    return {
        level: dict(sorted(tam_counts.items(), key=lambda item: item[0]))
        for level, tam_counts in sorted(matrix.items(), key=lambda item: item[0])
    }


def balance_rows_by_level_tam(rows: List[Dict[str, str]], seed: int) -> List[Dict[str, str]]:
    rng = random.Random(seed)
    grouped: Dict[str, Dict[str, List[Dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row.get("level", "Unknown")][row.get("tam_bucket", "none")].append(row)

    balanced: List[Dict[str, str]] = []
    for level in sorted(grouped.keys()):
        buckets = grouped[level]
        if len(buckets) <= 1:
            for bucket_rows in buckets.values():
                balanced.extend(bucket_rows)
            continue

        target_size = min(len(bucket_rows) for bucket_rows in buckets.values())
        for bucket_name in sorted(buckets.keys()):
            bucket_rows = buckets[bucket_name]
            if len(bucket_rows) <= target_size:
                balanced.extend(bucket_rows)
            else:
                balanced.extend(rng.sample(bucket_rows, target_size))

    rng.shuffle(balanced)
    return balanced


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
    parser.add_argument(
        "--balance-level-tam",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Balance examples by (level, tam_bucket) before train/dev/test split",
    )
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows: List[Dict[str, str]] = []
    for item in raw:
        rows.extend(iter_examples(item))
    rows_before_balance = rows[:]
    if args.balance_level_tam:
        rows = balance_rows_by_level_tam(rows, seed=args.seed)

    os.makedirs(args.output_dir, exist_ok=True)
    train, dev, test = split_data(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    write_jsonl(train, os.path.join(args.output_dir, "train.jsonl"))
    write_jsonl(dev, os.path.join(args.output_dir, "dev.jsonl"))
    write_jsonl(test, os.path.join(args.output_dir, "test.jsonl"))

    stats = {
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "total_before_balance": len(rows_before_balance),
        "total_after_balance": len(rows),
        "balance_level_tam": bool(args.balance_level_tam),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "distributions_before_balance": {
            "level": _count_by(rows_before_balance, lambda row: row.get("level", "Unknown")),
            "tam_bucket": _count_by(rows_before_balance, lambda row: row.get("tam_bucket", "none")),
            "level_tam": _count_level_tam(rows_before_balance),
        },
        "distributions_after_balance": {
            "level": _count_by(rows, lambda row: row.get("level", "Unknown")),
            "tam_bucket": _count_by(rows, lambda row: row.get("tam_bucket", "none")),
            "level_tam": _count_level_tam(rows),
        },
    }
    with open(os.path.join(args.output_dir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
