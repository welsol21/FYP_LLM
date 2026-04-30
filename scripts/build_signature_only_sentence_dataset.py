from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ela_pipeline.annotate.signature_note_prompt import (
    SIGNATURE_ONLY_PROMPT_TEMPLATE_VERSION,
    build_signature_note_training_prompt,
)


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _seed_row_to_training_row(row: dict[str, Any]) -> dict[str, Any]:
    note_text = _norm(row.get("note_text") or row.get("target_rendered") or row.get("target"))
    sentence_text = _norm(row.get("sentence_text") or row.get("target_content") or row.get("sentence"))
    signature_text = _norm(row.get("spacy_signature"))
    if not note_text or not signature_text or not sentence_text:
        raise ValueError("seed row missing note_text, sentence_text, or spacy_signature")

    depth = int(row.get("spacy_signature_depth") or 2)
    family_id = _norm(row.get("spacy_signature_family_id"))
    prompt = build_signature_note_training_prompt(
        signature_text=signature_text,
        node_level="Sentence",
        audience_level="intermediate",
        depth=depth,
        family_id=family_id,
    )

    source_name = _norm(row.get("source") or row.get("note_source_book") or row.get("source_name"))
    split_group_id = _norm(row.get("split_group_id") or row.get("source_document_id") or source_name or sentence_text[:80])

    return {
        "input": prompt,
        "target": note_text,
        "split_group_id": split_group_id,
    }


def _split_by_group(rows: list[dict[str, Any]], *, seed: int, dev_ratio: float, test_ratio: float):
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("split_group_id") or "unknown")].append(row)

    group_items = list(grouped.items())
    rng = random.Random(seed)
    rng.shuffle(group_items)

    total = len(rows)
    target_test = int(total * test_ratio)
    target_dev = int(total * dev_ratio)

    test: list[dict[str, Any]] = []
    dev: list[dict[str, Any]] = []
    train: list[dict[str, Any]] = []
    for _, group_rows in group_items:
        if len(test) < target_test:
            test.extend(group_rows)
        elif len(dev) < target_dev:
            dev.extend(group_rows)
        else:
            train.extend(group_rows)
    return train, dev, test


def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (_norm(row.get("input")), _norm(row.get("target")))


def build_dataset(seed_notes_input: str, delta_input: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    seed_rows_raw = list(_iter_jsonl(Path(seed_notes_input)))
    seed_rows = [_seed_row_to_training_row(row) for row in seed_rows_raw]

    delta_rows: list[dict[str, Any]] = []
    if delta_input:
        for row in _iter_jsonl(Path(delta_input)):
            delta_rows.append(row)

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for row in seed_rows + delta_rows:
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)

    report = {
        "seed_rows_input": len(seed_rows_raw),
        "seed_rows_converted": len(seed_rows),
        "delta_rows_input": len(delta_rows),
        "merged_rows": len(merged),
        "unique_seed_notes": len({row["target"] for row in seed_rows}),
        "unique_targets_merged": len({row["target"] for row in merged}),
        "unique_spacy_signatures": len({row["spacy_signature"] for row in merged if row.get("spacy_signature")}),
        "seed_note_texts_preserved": sorted({row["target"] for row in seed_rows}),
    }
    return merged, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a signature-only seed-preserving sentence dataset.")
    parser.add_argument("--seed-notes-input", required=True)
    parser.add_argument("--delta-input")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    args = parser.parse_args()

    rows, report = build_dataset(args.seed_notes_input, args.delta_input)
    train, dev, test = _split_by_group(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    clean_rows = [{"input": row["input"], "target": row["target"]} for row in rows]
    clean_train = [{"input": row["input"], "target": row["target"]} for row in train]
    clean_dev = [{"input": row["input"], "target": row["target"]} for row in dev]
    clean_test = [{"input": row["input"], "target": row["target"]} for row in test]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "all.jsonl", clean_rows)
    _write_jsonl(out_dir / "train.jsonl", clean_train)
    _write_jsonl(out_dir / "dev.jsonl", clean_dev)
    _write_jsonl(out_dir / "test.jsonl", clean_test)
    _write_json(out_dir / "stats.json", {
        "builder": "build_signature_only_sentence_dataset.py",
        "seed_notes_input": str(Path(args.seed_notes_input).resolve()),
        "delta_input": str(Path(args.delta_input).resolve()) if args.delta_input else None,
        "output_rows": len(clean_rows),
        "train": len(clean_train),
        "dev": len(clean_dev),
        "test": len(clean_test),
        "prompt_template_version": SIGNATURE_ONLY_PROMPT_TEMPLATE_VERSION,
        **report,
    })
    print(json.dumps({"status": "ok", "rows": len(clean_rows), "output_dir": str(out_dir.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
