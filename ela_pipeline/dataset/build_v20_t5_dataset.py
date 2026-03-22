"""Build T5 train/dev/test dataset v20: v19 + GSWE (Biber et al. Grammar of Spoken and Written English).

Pipeline:
1. Load v19 all.jsonl as base rows.
2. Load gswe_dataset_rows.jsonl (pre-built, has contract_template_payload).
3. Convert dataset_rows → T5 training format (input/target).
4. Dedup exact (input, target) pairs against v19.
5. Apply per-target cap only to new GSWE rows.
6. Merge → deduplicate → split train/dev/test.
7. Write v20 output dir + stats.json.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.contract_template_builder import (
    CONTRACT_PROMPT_TEMPLATE_VERSION,
    build_contract_template_training_prompt,
    normalize_template_text,
)


SOURCE_BOOK_GSWE = "gswe_2021"

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
    parser = argparse.ArgumentParser(description="Build v20 T5 dataset: v19 + GSWE.")
    parser.add_argument(
        "--v19-all-jsonl",
        default="data/processed_t5_v19_contract_book_farlex_egiu/all.jsonl",
    )
    parser.add_argument(
        "--gswe-dataset-rows-jsonl",
        default="data/reports/gswe_dataset_rows.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed_t5_v20_contract_book_farlex_egiu_gswe",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--max-per-target", type=int, default=_MAX_PER_TARGET)
    args = parser.parse_args()

    print("=== Step 1: Load v19 base rows ===")
    v19_rows = list(_iter_jsonl(Path(args.v19_all_jsonl)))
    print(f"  v19 rows: {len(v19_rows)}")

    print("=== Step 2: Convert GSWE dataset_rows → T5 format ===")
    gswe_raw = list(_iter_jsonl(Path(args.gswe_dataset_rows_jsonl)))
    print(f"  GSWE raw dataset_rows: {len(gswe_raw)}")
    gswe_t5_rows: list[dict[str, Any]] = []
    for row in gswe_raw:
        t5_row = _dataset_row_to_t5(row, source_book=SOURCE_BOOK_GSWE)
        if t5_row:
            gswe_t5_rows.append(t5_row)
    print(f"  GSWE T5 rows: {len(gswe_t5_rows)}")

    print("=== Step 3: Dedup GSWE against v19 ===")
    v19_pairs: set[tuple[str, str]] = set()
    for row in v19_rows:
        inp = str(row.get("input") or "")
        tgt = _target_key(str(row.get("target") or ""))
        v19_pairs.add((inp, tgt))

    new_gswe_rows = [
        r for r in gswe_t5_rows
        if (str(r.get("input") or ""), _target_key(str(r.get("target") or ""))) not in v19_pairs
    ]
    print(f"  GSWE rows after dedup against v19: {len(new_gswe_rows)} (was {len(gswe_t5_rows)})")

    print("=== Step 4: Apply per-target cap to new GSWE rows ===")
    v19_target_counts: Counter[str] = Counter(
        _target_key(str(r.get("target") or "")) for r in v19_rows
    )
    capped_gswe: list[dict[str, Any]] = []
    gswe_target_counts: Counter[str] = Counter()
    for row in new_gswe_rows:
        tgt_key = _target_key(str(row.get("target") or ""))
        already = v19_target_counts[tgt_key] + gswe_target_counts[tgt_key]
        if args.max_per_target > 0 and already >= args.max_per_target:
            continue
        gswe_target_counts[tgt_key] += 1
        capped_gswe.append(row)
    print(f"  GSWE rows after per-target cap ({args.max_per_target}): {len(capped_gswe)}")

    all_rows = v19_rows + capped_gswe
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
            f"v20: v19 ({len(v19_rows)} rows) + gswe_2021 ({len(capped_gswe)} new rows)"
        ),
        "source_distribution": source_dist,
        "topic_distribution": topic_dist,
    }
    (out_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
