"""Build train/dev datasets for DeBERTa classifier from enriched KB rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random


def _compose_input_text(row: dict) -> str:
    spacy = row.get("spacy") if isinstance(row.get("spacy"), dict) else {}
    derived = spacy.get("derived_features") if isinstance(spacy.get("derived_features"), dict) else {}
    text = str(spacy.get("text") or row.get("blueprint_intermediate") or "").strip()
    band = str(row.get("band") or "").strip()
    class_id = str(row.get("class_id") or "").strip()
    tam_signature = str(derived.get("tam_signature") or "unspecified").strip()
    return (
        f"task: classify_cefr_and_grammar "
        f"band: {band} "
        f"class_id: {class_id} "
        f"tam_signature: {tam_signature} "
        f"text: {text}"
    )


def build_train_dev_from_enriched_kb(
    *,
    input_path: str,
    output_dir: str,
    dev_ratio: float = 0.2,
    seed: int = 42,
) -> dict[str, str]:
    src = Path(input_path)
    if not src.is_file():
        raise FileNotFoundError(f"input_path not found: {input_path}")
    if not (0.0 < dev_ratio < 1.0):
        raise ValueError("dev_ratio must be in range (0,1)")

    rows = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append(
                {
                    "input": _compose_input_text(row),
                    "cefr_label": str(row.get("cefr_level") or "").strip().upper(),
                    "class_id": str(row.get("class_id") or "").strip().lower(),
                    "band": str(row.get("band") or "").strip(),
                }
            )

    rng = random.Random(seed)
    rng.shuffle(rows)
    split = max(1, int(len(rows) * (1.0 - dev_ratio)))
    train_rows = rows[:split]
    dev_rows = rows[split:]
    if not dev_rows:
        dev_rows = train_rows[-1:]
        train_rows = train_rows[:-1]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_path = out_dir / "train_classifier.jsonl"
    dev_path = out_dir / "dev_classifier.jsonl"
    stats_path = out_dir / "classifier_dataset_stats.json"

    with train_path.open("w", encoding="utf-8") as f:
        for row in train_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with dev_path.open("w", encoding="utf-8") as f:
        for row in dev_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    cefr_counts: dict[str, int] = {}
    for row in rows:
        cefr_counts[row["cefr_label"]] = cefr_counts.get(row["cefr_label"], 0) + 1
    stats = {
        "total": len(rows),
        "train": len(train_rows),
        "dev": len(dev_rows),
        "cefr_counts": cefr_counts,
    }
    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return {
        "train": str(train_path),
        "dev": str(dev_path),
        "stats": str(stats_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build train/dev datasets for DeBERTa classifier from enriched KB.")
    parser.add_argument("--input-path", default="artifacts/classifier_kb/kb_spacy_enriched.jsonl")
    parser.add_argument("--output-dir", default="data/processed_classifier")
    parser.add_argument("--dev-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    artifacts = build_train_dev_from_enriched_kb(
        input_path=args.input_path,
        output_dir=args.output_dir,
        dev_ratio=args.dev_ratio,
        seed=args.seed,
    )
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
