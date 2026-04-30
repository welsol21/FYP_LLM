from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.contract_template_builder import (
    CONTRACT_PROMPT_TEMPLATE_VERSION,
    build_contract_template_payload,
    build_contract_template_training_prompt,
)
from ela_pipeline.dataset.note_patterning import build_note_pattern


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
    context = row.get("context") or {}
    source = row.get("source") or {}
    target = row.get("target") or {}
    note_text = _norm(target.get("note_text"))
    sentence_text = _norm(context.get("sentence_text") or context.get("content"))
    sentence_node = {
        "type": "Sentence",
        "content": sentence_text,
        "part_of_speech": "sentence",
        "grammatical_role": "clause",
        "cefr_level": None,
        "tense": None,
        "aspect": None,
        "mood": None,
        "voice": None,
        "finiteness": None,
        "tam_construction": None,
        "grammar_classes": [],
        "source_span": None,
        "linguistic_elements": [],
    }
    payload = build_contract_template_payload(
        node=sentence_node,
        sentence_node=sentence_node,
        parent=None,
        path_types=["Sentence"],
        depth=0,
        sibling_index=0,
        sibling_count=1,
    )
    prompt = build_contract_template_training_prompt(payload or {}, node_level="Sentence")
    note_pattern = build_note_pattern(
        note_text=note_text,
        sentence_text=sentence_text,
    )
    return {
        "input": prompt,
        "target": note_text,
        "target_rendered": note_text,
        "target_pattern": note_pattern["pattern_text"],
        "target_pattern_slots": note_pattern["slot_values"],
        "target_pattern_source": note_pattern["pattern_source"],
        "level": "Sentence",
        "tam_bucket": "none",
        "prompt_template_version": CONTRACT_PROMPT_TEMPLATE_VERSION,
        "source_document_id": _norm(source.get("document_id")),
        "source_name": _norm(source.get("document_id")),
        "sentence_text": sentence_text,
        "target_content": sentence_text,
        "template_id": (payload or {}).get("template_id"),
        "note_source_book": _norm(source.get("document_id")),
        "note_topic": _norm(source.get("topic")),
        "note_origin_unit": _norm(source.get("origin_unit")),
        "note_match_level": "seed",
        "note_selection_mode": "seed_preserved",
        "note_source_tier": "seed",
        "projection_version": "seed_note_pool_v1",
        "split_group_id": _norm(source.get("document_id")) or f"seed::{sentence_text[:80]}",
        "seed_note_text": note_text,
        "seed_row_id": _norm(row.get("id")),
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
        "seed_note_texts_preserved": sorted({row["target"] for row in seed_rows}),
    }
    return merged, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a seed-preserving sentence dataset.")
    parser.add_argument("--seed-notes-input", required=True)
    parser.add_argument("--delta-input")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    args = parser.parse_args()

    rows, report = build_dataset(args.seed_notes_input, args.delta_input)
    train, dev, test = _split_by_group(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "all.jsonl", rows)
    _write_jsonl(out_dir / "train.jsonl", train)
    _write_jsonl(out_dir / "dev.jsonl", dev)
    _write_jsonl(out_dir / "test.jsonl", test)
    _write_json(out_dir / "stats.json", {
        "builder": "build_seed_preserving_sentence_dataset.py",
        "seed_notes_input": str(Path(args.seed_notes_input).resolve()),
        "delta_input": str(Path(args.delta_input).resolve()) if args.delta_input else None,
        "output_rows": len(rows),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        **report,
    })
    print(json.dumps({"status": "ok", "rows": len(rows), "output_dir": str(out_dir.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
