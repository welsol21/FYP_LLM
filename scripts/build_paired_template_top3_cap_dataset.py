from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_INPUT = "data/processed_sentence_seed/seed_preserving_sentence_dataset_v22_paired_template_v1/all.jsonl"
DEFAULT_OUTPUT_DIR = "data/processed_sentence_seed/seed_preserving_sentence_dataset_v23_paired_template_top3cap400_v1"
DEFAULT_TOP_PLACEHOLDERS = ("SUBJECT", "IF_CLAUSE", "OBJECT")

WS_RE = re.compile(r"\s+")
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def _norm(value: Any) -> str:
    return WS_RE.sub(" ", str(value or "").strip())


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


def _extract_placeholders(text: str) -> list[str]:
    from ela_pipeline.dataset.note_patterning import normalize_placeholder_name

    return sorted(
        {
            normalize_placeholder_name(ph)
            for ph in PLACEHOLDER_RE.findall(text or "")
            if normalize_placeholder_name(ph)
        }
    )


def _split_rows(rows: list[dict[str, Any]], *, seed: int, dev_ratio: float, test_ratio: float):
    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    total = len(shuffled)
    target_test = int(total * test_ratio)
    target_dev = int(total * dev_ratio)
    test = shuffled[:target_test]
    dev = shuffled[target_test : target_test + target_dev]
    train = shuffled[target_test + target_dev :]
    return train, dev, test


def _digest_key(*parts: str) -> str:
    payload = "::".join(parts).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def build_dataset(
    input_path: str,
    *,
    top_placeholders: tuple[str, ...],
    cap: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_rows = list(_iter_jsonl(Path(input_path)))
    target_counts: Counter[str] = Counter()
    row_placeholders: list[list[str]] = []
    row_targets: list[str] = []

    for row in raw_rows:
        target = _norm(row.get("target"))
        placeholders = _extract_placeholders(target)
        row_targets.append(target)
        row_placeholders.append(placeholders)
        target_counts[target] += 1

    keep_rows: list[dict[str, Any]] = []
    cap_counts: Counter[str] = Counter()
    kept_top_rows = 0
    dropped_top_rows = 0
    kept_non_top_rows = 0

    sortable_candidates: list[tuple[tuple[int, int, int, str], int]] = []
    for idx, row in enumerate(raw_rows):
        placeholders = row_placeholders[idx]
        top_hits = [ph for ph in placeholders if ph in top_placeholders]
        if not top_hits:
            keep_rows.append({"input": _norm(row.get("input")), "target": _norm(row.get("target"))})
            kept_non_top_rows += 1
            continue

        rare_count = sum(1 for ph in placeholders if ph not in top_placeholders)
        target_freq = target_counts[row_targets[idx]]
        top_count = len(top_hits)
        key = (
            target_freq,
            -rare_count,
            top_count,
            _digest_key(_norm(row.get("input")), _norm(row.get("target"))),
        )
        sortable_candidates.append((key, idx))

    sortable_candidates.sort(key=lambda item: item[0])
    selected_top_indices: set[int] = set()
    for _, idx in sortable_candidates:
        placeholders = row_placeholders[idx]
        top_hits = [ph for ph in placeholders if ph in top_placeholders]
        if any(cap_counts[ph] >= cap for ph in top_hits):
            dropped_top_rows += 1
            continue
        for ph in top_hits:
            cap_counts[ph] += 1
        selected_top_indices.add(idx)
        keep_rows.append({"input": _norm(raw_rows[idx].get("input")), "target": _norm(raw_rows[idx].get("target"))})
        kept_top_rows += 1

    report = {
        "input_rows": len(raw_rows),
        "output_rows": len(keep_rows),
        "top_placeholders": list(top_placeholders),
        "cap_per_placeholder": cap,
        "kept_non_top_rows": kept_non_top_rows,
        "kept_top_rows": kept_top_rows,
        "dropped_top_rows": dropped_top_rows,
        "placeholder_counts_before": {},
        "placeholder_counts_after": {},
        "unique_targets_before": len(target_counts),
        "unique_targets_after": len({row["target"] for row in keep_rows}),
    }

    before = Counter()
    after = Counter()
    for row, placeholders in zip(raw_rows, row_placeholders):
        for ph in placeholders:
            before[ph] += 1
    for row in keep_rows:
        for ph in _extract_placeholders(row.get("target", "")):
            after[ph] += 1

    report["placeholder_counts_before"] = dict(before.most_common())
    report["placeholder_counts_after"] = dict(after.most_common())
    report["cap_counts"] = dict(cap_counts.most_common())
    return keep_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Cap the most frequent placeholder families in a paired-template dataset.")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--cap", type=int, default=400)
    parser.add_argument("--top-placeholders", nargs="+", default=list(DEFAULT_TOP_PLACEHOLDERS))
    args = parser.parse_args()

    rows, report = build_dataset(
        args.input,
        top_placeholders=tuple(str(item).strip() for item in args.top_placeholders if str(item).strip()),
        cap=args.cap,
    )
    train, dev, test = _split_rows(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "all.jsonl", rows)
    _write_jsonl(out_dir / "train.jsonl", train)
    _write_jsonl(out_dir / "dev.jsonl", dev)
    _write_jsonl(out_dir / "test.jsonl", test)
    _write_json(
        out_dir / "stats.json",
        {
            "builder": "build_paired_template_top3_cap_dataset.py",
            "source_input": str(Path(args.input).resolve()),
            "output_rows": len(rows),
            "train": len(train),
            "dev": len(dev),
            "test": len(test),
            **report,
        },
    )
    print(json.dumps({"status": "ok", "rows": len(rows), "output_dir": str(out_dir.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
