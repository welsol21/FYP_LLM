"""Build T5 train/dev/test dataset v21: v20 + LGSWE 1999 + COBUILD Advanced Dict 2018.

Pipeline:
1. Load v20 all.jsonl as base rows.
2. Load lgswe_1999_dataset_rows.jsonl and cobuild_advanced_2018_dataset_rows.jsonl.
3. Convert dataset_rows → T5 training format (input/target).
4. Dedup exact (input, target) pairs against v20.
5. Apply per-target cap only to new rows.
6. Merge → deduplicate → split train/dev/test.
7. Write v21 output dir + stats.json.
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


def _convert_new_source(
    rows_path: Path,
    source_book: str,
    base_pairs: set[tuple[str, str]],
    base_target_counts: Counter[str],
    *,
    max_per_target: int,
) -> list[dict[str, Any]]:
    """Convert a dataset_rows jsonl to T5 rows, dedup against base, apply cap."""
    raw = list(_iter_jsonl(rows_path))
    t5_rows = [r for row in raw if (r := _dataset_row_to_t5(row, source_book)) is not None]
    # Dedup against base
    new_rows = [
        r for r in t5_rows
        if (str(r.get("input") or ""), _target_key(str(r.get("target") or ""))) not in base_pairs
    ]
    # Apply per-target cap
    src_target_counts: Counter[str] = Counter()
    capped: list[dict[str, Any]] = []
    for row in new_rows:
        tgt_key = _target_key(str(row.get("target") or ""))
        already = base_target_counts[tgt_key] + src_target_counts[tgt_key]
        if max_per_target > 0 and already >= max_per_target:
            continue
        src_target_counts[tgt_key] += 1
        capped.append(row)
    return capped


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
    parser = argparse.ArgumentParser(description="Build v21 T5 dataset: v20 + LGSWE 1999 + COBUILD 2018.")
    parser.add_argument("--v20-all-jsonl", default="data/processed_t5_v20_contract_book_farlex_egiu_gswe/all.jsonl")
    parser.add_argument("--lgswe-1999-jsonl", default="data/reports/lgswe_1999_dataset_rows.jsonl")
    parser.add_argument("--cobuild-2018-jsonl", default="data/reports/cobuild_advanced_2018_dataset_rows.jsonl")
    parser.add_argument("--output-dir", default="data/processed_t5_v21_contract_book_farlex_egiu_gswe_lgswe_cobuild")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--max-per-target", type=int, default=_MAX_PER_TARGET)
    args = parser.parse_args()

    print("=== Step 1: Load v20 base rows ===")
    v20_rows = list(_iter_jsonl(Path(args.v20_all_jsonl)))
    print(f"  v20 rows: {len(v20_rows)}")

    base_pairs: set[tuple[str, str]] = set()
    for row in v20_rows:
        inp = str(row.get("input") or "")
        tgt = _target_key(str(row.get("target") or ""))
        base_pairs.add((inp, tgt))
    base_target_counts: Counter[str] = Counter(
        _target_key(str(r.get("target") or "")) for r in v20_rows
    )

    print("=== Step 2: Convert LGSWE 1999 ===")
    lgswe_rows = _convert_new_source(
        Path(args.lgswe_1999_jsonl), "lgswe_1999",
        base_pairs, base_target_counts, max_per_target=args.max_per_target,
    )
    print(f"  LGSWE 1999 new rows: {len(lgswe_rows)}")

    # Update base for COBUILD dedup (include LGSWE rows already accepted)
    lgswe_target_counts = Counter(_target_key(str(r.get("target") or "")) for r in lgswe_rows)
    combined_target_counts = base_target_counts + lgswe_target_counts

    print("=== Step 3: Convert COBUILD 2018 ===")
    cobuild_rows = _convert_new_source(
        Path(args.cobuild_2018_jsonl), "cobuild_advanced_2018",
        base_pairs, combined_target_counts, max_per_target=args.max_per_target,
    )
    print(f"  COBUILD 2018 new rows: {len(cobuild_rows)}")

    all_rows = v20_rows + lgswe_rows + cobuild_rows
    # Final exact-pair dedup
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

    print("=== Step 4: Split ===")
    train, dev, test = _split(all_rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)
    print(f"  train={len(train)}, dev={len(dev)}, test={len(test)}")

    print("=== Step 5: Write output ===")
    out_dir = Path(args.output_dir)
    _write_jsonl(out_dir / "all.jsonl", all_rows)
    _write_jsonl(out_dir / "train.jsonl", train)
    _write_jsonl(out_dir / "dev.jsonl", dev)
    _write_jsonl(out_dir / "test.jsonl", test)

    source_dist = dict(Counter(
        str(r.get("note_source_book") or r.get("source_book") or "?")
        for r in all_rows
    ).most_common())

    stats = {
        "prompt_template_version": CONTRACT_PROMPT_TEMPLATE_VERSION,
        "total": len(all_rows),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "note": (
            f"v21: v20 ({len(v20_rows)} rows)"
            f" + lgswe_1999 ({len(lgswe_rows)} rows)"
            f" + cobuild_advanced_2018 ({len(cobuild_rows)} rows)"
        ),
        "source_distribution": source_dist,
    }
    (out_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
