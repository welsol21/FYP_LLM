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

from ela_pipeline.annotate.note_context import build_note_context_prompt
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


def _make_rows(nodes_dir: Path) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    rows: List[Dict[str, str]] = []
    counters: Dict[str, int] = defaultdict(int)

    for level, fname in [("Sentence", "sentences.jsonl"), ("Phrase", "phrases.jsonl"), ("Word", "words.jsonl")]:
        for node in _iter_jsonl(nodes_dir / fname):
            src = node
            content = str(src.get("content", "")).strip()
            sentence = str(src.get("sentence_text", "")).strip() or content
            if not content:
                continue
            features = _features_for_level(src, level)
            tam = _tam_bucket(src)
            target, reason = _build_template_target(level, content, features, tam)
            if not target:
                if reason:
                    counters[f"template_filtered_{reason.lower()}"] += 1
                continue

            if level == "Sentence":
                sentence_node = {
                    "type": "Sentence",
                    "content": content,
                    "part_of_speech": "sentence",
                    "grammatical_role": "root",
                    "cefr_level": src.get("cefr_level"),
                    "tense": src.get("tense"),
                    "aspect": src.get("aspect"),
                    "mood": src.get("mood"),
                    "voice": src.get("voice"),
                    "finiteness": src.get("finiteness"),
                    "tam_construction": src.get("tam_construction") or tam,
                    "grammar_classes": src.get("grammar_classes"),
                    "source_span": src.get("source_span"),
                    "linguistic_elements": [],
                }
                prompt = build_note_context_prompt(
                    node=sentence_node,
                    parent=None,
                    sentence_node=sentence_node,
                    path_types=["Sentence"],
                    depth=0,
                    sibling_index=0,
                    sibling_count=1,
                    template_version=PROMPT_TEMPLATE_VERSION,
                )
            elif level == "Phrase":
                phrase_node = {
                    "type": "Phrase",
                    "content": content,
                    "part_of_speech": src.get("part_of_speech"),
                    "grammatical_role": src.get("grammatical_role"),
                    "cefr_level": src.get("cefr_level"),
                    "tense": src.get("tense"),
                    "aspect": src.get("aspect"),
                    "mood": src.get("mood"),
                    "voice": src.get("voice"),
                    "finiteness": src.get("finiteness"),
                    "tam_construction": src.get("tam_construction") or tam,
                    "grammar_classes": src.get("grammar_classes"),
                    "source_span": src.get("source_span"),
                    "linguistic_elements": [],
                }
                sentence_stub = {
                    "type": "Sentence",
                    "content": sentence,
                    "part_of_speech": "sentence",
                    "grammatical_role": "clause",
                    "cefr_level": src.get("sentence_cefr_level") or src.get("cefr_level"),
                    "tense": src.get("sentence_tense"),
                    "aspect": src.get("sentence_aspect"),
                    "mood": src.get("sentence_mood"),
                    "voice": src.get("sentence_voice"),
                    "finiteness": src.get("sentence_finiteness"),
                    "tam_construction": src.get("sentence_tam_construction"),
                    "grammar_classes": src.get("sentence_grammar_classes"),
                    "source_span": None,
                    "linguistic_elements": [],
                }
                prompt = build_note_context_prompt(
                    node=phrase_node,
                    parent=sentence_stub,
                    sentence_node=sentence_stub,
                    path_types=["Sentence", "Phrase"],
                    depth=1,
                    sibling_index=0,
                    sibling_count=1,
                    template_version=PROMPT_TEMPLATE_VERSION,
                )
            else:
                word_node = {
                    "type": "Word",
                    "content": content,
                    "part_of_speech": src.get("part_of_speech"),
                    "grammatical_role": src.get("grammatical_role"),
                    "cefr_level": src.get("cefr_level"),
                    "tense": src.get("tense"),
                    "aspect": src.get("aspect"),
                    "mood": src.get("mood"),
                    "voice": src.get("voice"),
                    "finiteness": src.get("finiteness"),
                    "tam_construction": src.get("tam_construction") or tam,
                    "grammar_classes": src.get("grammar_classes"),
                    "source_span": src.get("source_span"),
                    "dep_label": src.get("dep_label"),
                    "head_id": src.get("head_id"),
                    "linguistic_elements": [],
                }
                parent_stub = {
                    "type": "Phrase",
                    "content": src.get("parent_content"),
                    "part_of_speech": src.get("parent_part_of_speech"),
                    "grammatical_role": src.get("parent_grammatical_role"),
                    "cefr_level": src.get("parent_cefr_level"),
                    "tense": src.get("parent_tense"),
                    "aspect": src.get("parent_aspect"),
                    "mood": src.get("parent_mood"),
                    "voice": src.get("parent_voice"),
                    "finiteness": src.get("parent_finiteness"),
                    "tam_construction": src.get("parent_tam_construction"),
                    "grammar_classes": src.get("parent_grammar_classes"),
                    "source_span": None,
                    "linguistic_elements": [],
                }
                sentence_stub = {
                    "type": "Sentence",
                    "content": sentence,
                    "part_of_speech": "sentence",
                    "grammatical_role": "clause",
                    "cefr_level": src.get("sentence_cefr_level") or src.get("cefr_level"),
                    "tense": src.get("sentence_tense"),
                    "aspect": src.get("sentence_aspect"),
                    "mood": src.get("sentence_mood"),
                    "voice": src.get("sentence_voice"),
                    "finiteness": src.get("sentence_finiteness"),
                    "tam_construction": src.get("sentence_tam_construction"),
                    "grammar_classes": src.get("sentence_grammar_classes"),
                    "source_span": None,
                    "linguistic_elements": [],
                }
                prompt = build_note_context_prompt(
                    node=word_node,
                    parent=parent_stub,
                    sentence_node=sentence_stub,
                    path_types=["Sentence", "Phrase", "Word"],
                    depth=2,
                    sibling_index=0,
                    sibling_count=1,
                    template_version=PROMPT_TEMPLATE_VERSION,
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
