from __future__ import annotations

import argparse
import json
import random
import sys
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.dataset.note_patterning import normalize_placeholder_name


DEFAULT_SOURCE_JSONL = "data/processed_sentence_seed/seed_preserving_sentence_dataset_v15/all.jsonl"
DEFAULT_OUTPUT_DIR = "data/processed_sentence_seed/seed_preserving_sentence_dataset_v47_signature_depth2_raw_note_v1"
SPACY_SIGNATURE_DEPTH = 2
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
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


def _rawize_note_text(note_text: str) -> str:
    text = _norm(note_text)
    if not text:
        return ""

    def replace(match: re.Match[str]) -> str:
        canonical = normalize_placeholder_name(match.group(1))
        return canonical.lower().replace("_", " ")

    text = PLACEHOLDER_RE.sub(replace, text)
    text = _norm(text)
    return text


def _sort_children(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            int((item.get("source_span") or {}).get("start", 0)),
            int((item.get("source_span") or {}).get("end", 0)),
            0 if str(item.get("type") or "").strip() == "Word" else 1,
        ),
    )


def _signature_label(node: dict[str, Any]) -> str:
    node_type = str(node.get("type") or "").strip()
    if node_type == "Sentence":
        return "ROOT"
    if node_type == "Word":
        return _norm(node.get("dep_label")).lower()
    return ""


def _build_spacy_signature(sentence_node: dict[str, Any], *, depth: int = SPACY_SIGNATURE_DEPTH) -> list[str]:
    labels: list[str] = []

    def walk(node: dict[str, Any], remaining_depth: int) -> None:
        label = _signature_label(node)
        if label:
            labels.append(label)
        if remaining_depth <= 0:
            return
        children = [child for child in (node.get("linguistic_elements") or []) if isinstance(child, dict)]
        for child in _sort_children(children):
            walk(child, remaining_depth - 1)

    walk(sentence_node, depth)
    return labels


def _split_by_group(rows: list[dict[str, Any]], *, seed: int, dev_ratio: float, test_ratio: float):
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("split_group_id") or "unknown")].append(row)

    items = list(grouped.items())
    rng = random.Random(seed)
    rng.shuffle(items)

    total = len(rows)
    target_test = int(total * test_ratio)
    target_dev = int(total * dev_ratio)
    test: list[dict[str, Any]] = []
    dev: list[dict[str, Any]] = []
    train: list[dict[str, Any]] = []

    for _, group_rows in items:
        if len(test) < target_test:
            test.extend(group_rows)
        elif len(dev) < target_dev:
            dev.extend(group_rows)
        else:
            train.extend(group_rows)
    return train, dev, test


def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (_norm(row.get("input")), _norm(row.get("target")))


def build_dataset(source_jsonl: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp("en_core_web_sm")
    rows_in = list(_iter_jsonl(Path(source_jsonl)))

    out: list[dict[str, Any]] = []
    skipped_missing = 0
    skipped_parse = 0
    seen: set[tuple[str, str]] = set()

    signature_counts: Counter[str] = Counter()
    note_counts: Counter[str] = Counter()

    for row in rows_in:
        sentence_text = _norm(row.get("sentence_text") or row.get("target_content") or row.get("sentence"))
        raw_note = _rawize_note_text(
            row.get("seed_note_text")
            or row.get("target_rendered")
            or row.get("target_raw")
            or row.get("target")
            or row.get("note_text")
        )
        if not sentence_text or not raw_note:
            skipped_missing += 1
            continue

        parsed = build_skeleton(sentence_text, nlp)
        if not parsed:
            skipped_parse += 1
            continue
        sentence_node = next(iter(parsed.values()))
        signature_nodes = _build_spacy_signature(sentence_node, depth=SPACY_SIGNATURE_DEPTH)
        signature_text = " -> ".join(signature_nodes).strip()
        if not signature_text:
            skipped_parse += 1
            continue

        pair_key = (signature_text, raw_note)
        if pair_key in seen:
            continue
        seen.add(pair_key)

        split_group_id = _norm(
            row.get("split_group_id")
            or row.get("source_document_id")
            or row.get("source_name")
            or row.get("note_source_book")
            or sentence_text[:80]
        )

        out.append(
            {
                "input": signature_text,
                "target": raw_note,
                "split_group_id": split_group_id,
            }
        )
        signature_counts[signature_text] += 1
        note_counts[raw_note] += 1

    report = {
        "builder": "build_signature_depth2_raw_note_dataset.py",
        "source_jsonl": str(Path(source_jsonl).resolve()),
        "rows_input": len(rows_in),
        "rows_output": len(out),
        "output_rows": len(out),
        "total": len(out),
        "total_after_balance": len(out),
        "rows_skipped_missing": skipped_missing,
        "rows_skipped_parse": skipped_parse,
        "spacy_signature_depth": SPACY_SIGNATURE_DEPTH,
        "unique_input": len({row["input"] for row in out}),
        "unique_target": len({row["target"] for row in out}),
        "input_template_rows": len(out),
        "raw_input_rows": 0,
        "template_target_rows": 0,
        "raw_target_rows": len(out),
        "signature_coverage_min": min(signature_counts.values()) if signature_counts else 0,
        "signature_coverage_max": max(signature_counts.values()) if signature_counts else 0,
        "top_spacy_signatures": [
            {"signature": signature, "count": count}
            for signature, count in signature_counts.most_common(20)
        ],
        "top_targets": [
            {"target": note, "count": count}
            for note, count in note_counts.most_common(20)
        ],
    }
    return out, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a depth-2 signature input with raw note targets.")
    parser.add_argument("--source-jsonl", default=DEFAULT_SOURCE_JSONL)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    args = parser.parse_args()

    rows, report = build_dataset(args.source_jsonl)
    train, dev, test = _split_by_group(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "all.jsonl", [{"input": row["input"], "target": row["target"]} for row in rows])
    _write_jsonl(out_dir / "train.jsonl", [{"input": row["input"], "target": row["target"]} for row in train])
    _write_jsonl(out_dir / "dev.jsonl", [{"input": row["input"], "target": row["target"]} for row in dev])
    _write_jsonl(out_dir / "test.jsonl", [{"input": row["input"], "target": row["target"]} for row in test])
    _write_json(
        out_dir / "stats.json",
        {
            **report,
            "train": len(train),
            "dev": len(dev),
            "test": len(test),
        },
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(rows),
                "train": len(train),
                "dev": len(dev),
                "test": len(test),
                "output_dir": str(out_dir.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
