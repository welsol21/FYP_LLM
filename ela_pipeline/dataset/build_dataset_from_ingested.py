"""Build train/dev/test JSONL pairs from ingested node datasets.

Input format:
- nodes_dir/sentences.jsonl
- nodes_dir/phrases.jsonl
- nodes_dir/words.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from ela_pipeline.dataset.build_dataset import (
    PROMPT_TEMPLATE_VERSION,
    _build_template_target,
    _count_by,
    _count_level_tam,
    _extract_template_id,
    _target_key,
    balance_rows_by_level_tam,
    dedup_and_cap_rows,
    evaluate_quality_gates,
    format_feature_list,
    split_data,
    write_jsonl,
)


WORD_POS_TO_UD = {
    "noun": "NOUN",
    "proper noun": "PROPN",
    "pronoun": "PRON",
    "verb": "VERB",
    "auxiliary verb": "AUX",
    "adjective": "ADJ",
    "adverb": "ADV",
    "preposition": "ADP",
    "article": "DET",
    "determiner": "DET",
    "coordinating conjunction": "CCONJ",
    "subordinating conjunction": "SCONJ",
    "particle": "PART",
    "numeral": "NUM",
    "interjection": "INTJ",
}


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _tam_bucket(row: Dict[str, Any]) -> str:
    if str(row.get("mood", "")).lower() == "modal" and str(row.get("aspect", "")).lower() == "perfect":
        return "modal_perfect"
    return "none"


def _features_for_level(row: Dict[str, Any], level: str) -> Dict[str, List[str]]:
    content = str(row.get("content", "")).strip()
    pos_name = str(row.get("part_of_speech", "")).strip().lower()
    dep = str(row.get("dep_label", "")).strip()

    if level == "Word":
        pos = WORD_POS_TO_UD.get(pos_name, "X")
        feats = row.get("features") or {}
        morph = [f"{k}={v}" for k, v in sorted(feats.items()) if v not in (None, "", "null")]
        return {
            "pos": [pos],
            "tag": [pos],
            "dep": [dep or "dep"],
            "morph": morph,
        }

    # Phrase/Sentence coarse fallback features for prompt/template functions.
    pos_list: List[str] = []
    if level == "Sentence":
        pos_list = ["SENT"]
    elif "prepositional phrase" in pos_name:
        pos_list = ["ADP", "NOUN"]
    elif "verb phrase" in pos_name:
        pos_list = ["AUX", "VERB"]
    elif "noun phrase" in pos_name:
        pos_list = ["DET", "NOUN"]
    elif "adjectival phrase" in pos_name:
        pos_list = ["ADJ"]
    elif "adverbial phrase" in pos_name:
        pos_list = ["ADV"]
    else:
        # light lexical fallback
        if content.lower().startswith(("before ", "after ", "in ", "on ", "at ", "with ", "from ", "to ")):
            pos_list = ["ADP", "NOUN"]
        else:
            pos_list = ["X"]
    return {
        "pos": pos_list,
        "tag": pos_list[:1],
        "dep": [dep or "dep"],
        "morph": [],
    }


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


def _make_rows(nodes_dir: Path) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    rows: List[Dict[str, str]] = []
    counters: Dict[str, int] = defaultdict(int)

    for level, fname in [("Sentence", "sentences.jsonl"), ("Phrase", "phrases.jsonl"), ("Word", "words.jsonl")]:
        for node in _iter_jsonl(nodes_dir / fname):
            content = str(node.get("content", "")).strip()
            sentence = str(node.get("sentence_text", "")).strip() or content
            if not content:
                continue
            features = _features_for_level(node, level)
            tam = _tam_bucket(node)
            target, reason = _build_template_target(level, content, features, tam)
            if not target:
                if reason:
                    counters[f"template_filtered_{reason.lower()}"] += 1
                continue

            if level == "Sentence":
                prompt = _render_sentence_prompt(
                    sentence=sentence,
                    pos_text=format_feature_list(features.get("pos", [])),
                    dep_text=format_feature_list(features.get("dep", [])),
                    tam_bucket=tam,
                )
            elif level == "Phrase":
                prompt = _render_phrase_prompt(
                    sentence=sentence,
                    phrase_text=content,
                    pos_text=format_feature_list(features.get("pos", [])),
                    dep_text=format_feature_list(features.get("dep", [])),
                    tam_bucket=tam,
                )
            else:
                prompt = _render_word_prompt(
                    sentence=sentence,
                    word_text=content,
                    pos_text=(features.get("pos", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                    tag_text=(features.get("tag", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                    dep_text=(features.get("dep", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                    morph_text=format_feature_list(features.get("morph", [])),
                    tam_bucket=tam,
                )

            rows.append(
                {
                    "input": prompt,
                    "target": target,
                    "level": level,
                    "tam_bucket": tam,
                    "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                }
            )
            counters["rows_emitted"] += 1
            counters["template_targets_used"] += 1

    return rows, counters


def _target_stats(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    counts = defaultdict(int)
    for row in rows:
        counts[_target_key(row.get("target", ""))] += 1
    total = len(rows)
    unique_targets = len(counts)
    repeated = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
    return {
        "total": total,
        "unique_targets": unique_targets,
        "duplicate_ratio": 1 - (unique_targets / total) if total else 0.0,
        "top_repeated_targets": [{"target": k, "count": v} for k, v in repeated],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dataset from ingested node JSONL files")
    parser.add_argument("--nodes-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--max-per-target", type=int, default=0)
    parser.add_argument(
        "--dedup-exact-input-target",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--balance-level-tam",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--min-unique-targets", type=int, default=0)
    parser.add_argument("--max-top1-share", type=float, default=1.0)
    parser.add_argument("--min-active-template-ids", type=int, default=0)
    args = parser.parse_args()

    rows_before_dedup, counters = _make_rows(Path(args.nodes_dir))
    rows_after_dedup, dedup_report = dedup_and_cap_rows(
        rows_before_dedup,
        max_per_target=int(args.max_per_target),
        dedup_exact_input_target=bool(args.dedup_exact_input_target),
    )

    if args.balance_level_tam:
        rows_after_balance = balance_rows_by_level_tam(rows_after_dedup, seed=int(args.seed))
    else:
        rows_after_balance = rows_after_dedup

    train, dev, test = split_data(
        rows_after_balance,
        seed=int(args.seed),
        dev_ratio=float(args.dev_ratio),
        test_ratio=float(args.test_ratio),
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(train, str(out_dir / "train.jsonl"))
    write_jsonl(dev, str(out_dir / "dev.jsonl"))
    write_jsonl(test, str(out_dir / "test.jsonl"))

    stats = {
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "input_nodes_dir": str(args.nodes_dir),
        "total_before_dedup": len(rows_before_dedup),
        "total_after_dedup": len(rows_after_dedup),
        "total_after_balance": len(rows_after_balance),
        "balance_level_tam": bool(args.balance_level_tam),
        "max_per_target": int(args.max_per_target),
        "dedup_exact_input_target": bool(args.dedup_exact_input_target),
        "dedup_report": dedup_report,
        "quality_counters": dict(counters),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "target_stats": {
            "before_dedup": _target_stats(rows_before_dedup),
            "after_dedup": _target_stats(rows_after_dedup),
            "after_balance": _target_stats(rows_after_balance),
        },
        "distributions": {
            "before_dedup": {
                "level": _count_by(rows_before_dedup, lambda row: row.get("level", "Unknown")),
                "tam_bucket": _count_by(rows_before_dedup, lambda row: row.get("tam_bucket", "none")),
                "template_id": _count_by(rows_before_dedup, lambda row: _extract_template_id(row.get("target", ""))),
                "level_tam": _count_level_tam(rows_before_dedup),
            },
            "after_dedup": {
                "level": _count_by(rows_after_dedup, lambda row: row.get("level", "Unknown")),
                "tam_bucket": _count_by(rows_after_dedup, lambda row: row.get("tam_bucket", "none")),
                "template_id": _count_by(rows_after_dedup, lambda row: _extract_template_id(row.get("target", ""))),
                "level_tam": _count_level_tam(rows_after_dedup),
            },
            "after_balance": {
                "level": _count_by(rows_after_balance, lambda row: row.get("level", "Unknown")),
                "tam_bucket": _count_by(rows_after_balance, lambda row: row.get("tam_bucket", "none")),
                "template_id": _count_by(rows_after_balance, lambda row: _extract_template_id(row.get("target", ""))),
                "level_tam": _count_level_tam(rows_after_balance),
            },
        },
    }

    failures = evaluate_quality_gates(
        target_stats_after_balance=stats["target_stats"]["after_balance"],
        template_id_distribution_after_balance=stats["distributions"]["after_balance"]["template_id"],
        min_unique_targets=int(args.min_unique_targets),
        max_top1_share=float(args.max_top1_share),
        min_active_template_ids=int(args.min_active_template_ids),
    )
    stats["quality_gates"] = {
        "min_unique_targets": int(args.min_unique_targets),
        "max_top1_share": float(args.max_top1_share),
        "min_active_template_ids": int(args.min_active_template_ids),
        "failures": failures,
        "passed": not failures,
    }

    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit("Dataset quality gates failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
