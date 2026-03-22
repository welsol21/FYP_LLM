"""Build T5 train/dev/test dataset v19: v18 + EGIU 5th Edition.

Pipeline:
1. Load v18 all.jsonl as base rows.
2. Run EGIU pairs through build_oxford_dictionary_dataset to get dataset_rows.
3. Convert dataset_rows → T5 training format (input/target).
4. Dedup exact (input, target) pairs against v18.
5. Merge → deduplicate → split train/dev/test.
6. Write v19 output dir + stats.json.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.contract_template_builder import (
    CONTRACT_PROMPT_TEMPLATE_VERSION,
    build_contract_template_training_prompt,
    normalize_template_text,
)
from ela_pipeline.dataset.build_oxford_dictionary_dataset import build_oxford_dictionary_dataset


SOURCE_BOOK_EGIU = "egiu_5th_2019"

# Soft per-target cap: clip over-repeated targets to keep training balanced.
_MAX_PER_TARGET = 60


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _target_key(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _dataset_row_to_t5(row: dict[str, Any], source_book: str) -> dict[str, Any] | None:
    payload = row.get("contract_template_payload")
    if not isinstance(payload, dict):
        return None
    template_text = normalize_template_text(payload.get("template_text") or "")
    if not template_text:
        return None
    node_level = str(row.get("node_level") or "").strip()
    if node_level not in {"Sentence", "Phrase"}:
        return None
    input_text = build_contract_template_training_prompt(payload, node_level=node_level)
    return {
        "input": input_text,
        "target": template_text,
        "level": node_level,
        "tam_bucket": "none",
        "prompt_template_version": CONTRACT_PROMPT_TEMPLATE_VERSION,
        "template_id": payload.get("template_id"),
        "topic_key": row.get("topic_key"),
        "source_book": source_book,
    }


def _dedup_and_cap(rows: list[dict[str, Any]], *, max_per_target: int) -> list[dict[str, Any]]:
    seen_pairs: set[tuple[str, str]] = set()
    target_counts: Counter[str] = Counter()
    kept: list[dict[str, Any]] = []
    for row in rows:
        inp = str(row.get("input") or "")
        tgt = str(row.get("target") or "")
        pair = (inp, _target_key(tgt))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        tgt_key = _target_key(tgt)
        if max_per_target > 0 and target_counts[tgt_key] >= max_per_target:
            continue
        target_counts[tgt_key] += 1
        kept.append(row)
    return kept


def _split(
    rows: list[dict[str, Any]],
    *,
    seed: int,
    dev_ratio: float,
    test_ratio: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_test = int(n * test_ratio)
    n_dev = int(n * dev_ratio)
    test = shuffled[:n_test]
    dev = shuffled[n_test: n_test + n_dev]
    train = shuffled[n_test + n_dev:]
    return train, dev, test


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v19 T5 dataset: v18 + EGIU.")
    parser.add_argument(
        "--v18-all-jsonl",
        default="data/processed_t5_v18_contract_book_farlex/all.jsonl",
    )
    parser.add_argument(
        "--egiu-pairs-jsonl",
        default="data/reports/egiu_5th_2019_pairs.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed_t5_v19_contract_book_farlex_egiu",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--max-per-target", type=int, default=_MAX_PER_TARGET)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    print("=== Step 1: Load v18 base rows ===")
    v18_rows = list(_iter_jsonl(Path(args.v18_all_jsonl)))
    print(f"  v18 rows: {len(v18_rows)}")

    print("=== Step 2: Process EGIU pairs ===")
    egiu_pairs_path = args.egiu_pairs_jsonl
    _, dataset_rows, report = build_oxford_dictionary_dataset(
        pairs_jsonl=egiu_pairs_path,
        spacy_model=args.spacy_model,
    )
    print(f"  EGIU dataset_rows: {len(dataset_rows)} (matched Sentence+Phrase nodes)")
    print(f"  Build stats: {json.dumps(report['stats'], indent=4)}")

    print("=== Step 3: Convert EGIU dataset_rows → T5 format ===")
    egiu_t5_rows: list[dict[str, Any]] = []
    for row in dataset_rows:
        t5_row = _dataset_row_to_t5(row, source_book=SOURCE_BOOK_EGIU)
        if t5_row:
            egiu_t5_rows.append(t5_row)
    print(f"  EGIU T5 rows: {len(egiu_t5_rows)}")

    print("=== Step 4: Merge and deduplicate ===")
    # Remove EGIU rows that are exact duplicates of v18 rows (same input+target pair).
    # Keep ALL v18 rows as-is; only apply per-target cap to new EGIU rows.
    v18_pairs: set[tuple[str, str]] = set()
    for row in v18_rows:
        inp = str(row.get("input") or "")
        tgt = _target_key(str(row.get("target") or ""))
        v18_pairs.add((inp, tgt))

    new_egiu_rows = [
        r for r in egiu_t5_rows
        if (str(r.get("input") or ""), _target_key(str(r.get("target") or ""))) not in v18_pairs
    ]
    print(f"  EGIU rows after dedup against v18: {len(new_egiu_rows)} (was {len(egiu_t5_rows)})")

    # Apply per-target cap only to the new EGIU rows (v18 rows pass through uncapped).
    v18_target_counts: Counter[str] = Counter(
        _target_key(str(r.get("target") or "")) for r in v18_rows
    )
    capped_egiu: list[dict[str, Any]] = []
    egiu_target_counts: Counter[str] = Counter()
    for row in new_egiu_rows:
        tgt_key = _target_key(str(row.get("target") or ""))
        already = v18_target_counts[tgt_key] + egiu_target_counts[tgt_key]
        if args.max_per_target > 0 and already >= args.max_per_target:
            continue
        egiu_target_counts[tgt_key] += 1
        capped_egiu.append(row)
    print(f"  EGIU rows after per-target cap ({args.max_per_target}): {len(capped_egiu)}")

    all_rows = v18_rows + capped_egiu
    # Final exact-pair dedup across merged rows
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in all_rows:
        pair = (str(row.get("input") or ""), _target_key(str(row.get("target") or "")))
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(row)
    all_rows = deduped
    print(f"  Total after merge+dedup: {len(all_rows)}")

    print("=== Step 5: Split ===")
    train, dev, test = _split(
        all_rows,
        seed=args.seed,
        dev_ratio=args.dev_ratio,
        test_ratio=args.test_ratio,
    )
    print(f"  train={len(train)}, dev={len(dev)}, test={len(test)}")

    print("=== Step 6: Write output ===")
    out_dir = Path(args.output_dir)
    _write_jsonl(out_dir / "all.jsonl", all_rows)
    _write_jsonl(out_dir / "train.jsonl", train)
    _write_jsonl(out_dir / "dev.jsonl", dev)
    _write_jsonl(out_dir / "test.jsonl", test)

    source_dist = dict(Counter(
        str(r.get("note_source_book") or r.get("source_book") or "?")
        for r in all_rows
    ).most_common())
    topic_dist = dict(Counter(
        str(r.get("note_topic") or r.get("topic_key") or "?")
        for r in all_rows
    ).most_common())

    stats = {
        "prompt_template_version": CONTRACT_PROMPT_TEMPLATE_VERSION,
        "total_after_balance": len(all_rows),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "total": len(all_rows),
        "note": (
            f"v19: v18 ({len(v18_rows)} rows) + egiu_5th_2019 ({len(new_egiu_rows)} new rows)"
        ),
        "egiu_build_stats": report["stats"],
        "source_distribution": source_dist,
        "topic_distribution": topic_dist,
    }
    (out_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
