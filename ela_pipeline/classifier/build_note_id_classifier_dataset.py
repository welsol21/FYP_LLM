"""Build note-id classifier dataset from canonical paired-template datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"dataset file not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _note_id(note_text: str) -> str:
    digest = hashlib.sha1(note_text.encode("utf-8")).hexdigest()[:12]
    return f"note_{digest}"


def _build_row(row: dict[str, Any], *, note_id: str, split_name: str, dataset_name: str) -> dict[str, Any]:
    input_text = str(row.get("input") or "").strip()
    note_text = str(row.get("target") or "").strip()
    if not input_text or not note_text:
        raise ValueError("Each row must contain non-empty input and target")
    return {
        "input": input_text,
        "text": input_text,
        "source_text": input_text,
        "note_id": note_id,
        "note_text": note_text,
        "note_type": "template" if "{{" in note_text else "raw",
        "dataset_name": dataset_name,
        "split_name": split_name,
        "grammar_evidence": {},
        "grammar_classes": [],
        "provenance": {
            "dataset_source": "note_id_classifier_v1",
            "treebank": dataset_name,
        },
    }


def _ensure_train_covers_all_note_ids(split_rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    train_ids = {str(row.get("note_id") or "") for row in split_rows["train"]}
    moved_from_dev = 0
    moved_from_test = 0

    for split_name in ("dev", "test"):
        remaining: list[dict[str, Any]] = []
        for row in split_rows[split_name]:
            note_id = str(row.get("note_id") or "")
            if note_id and note_id not in train_ids:
                promoted = dict(row)
                promoted["split_name"] = "train"
                split_rows["train"].append(promoted)
                train_ids.add(note_id)
                if split_name == "dev":
                    moved_from_dev += 1
                else:
                    moved_from_test += 1
                continue
            remaining.append(row)
        split_rows[split_name] = remaining

    return {
        "promoted_note_id_rows_from_dev_to_train": moved_from_dev,
        "promoted_note_id_rows_from_test_to_train": moved_from_test,
    }


def build_note_id_classifier_dataset(
    *,
    template_dataset_dir: str,
    raw_dataset_dir: str,
    output_dir: str,
) -> dict[str, Any]:
    sources = {
        "template_only": Path(template_dataset_dir),
        "raw_only": Path(raw_dataset_dir),
    }
    split_payloads: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "dev": [],
        "test": [],
    }
    all_note_texts: set[str] = set()

    for dataset_name, dataset_dir in sources.items():
        for split_name in ("train", "dev", "test"):
            rows = _load_jsonl(dataset_dir / f"{split_name}.jsonl")
            split_payloads[split_name].extend(
                {"dataset_name": dataset_name, "input": str(row.get("input") or "").strip(), "target": str(row.get("target") or "").strip()}
                for row in rows
            )
            all_note_texts.update(str(row.get("target") or "").strip() for row in rows if str(row.get("target") or "").strip())

    note_text_to_id = {note_text: _note_id(note_text) for note_text in sorted(all_note_texts)}

    split_rows: dict[str, list[dict[str, Any]]] = {}
    for split_name, rows in split_payloads.items():
        built_rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            note_text = str(row.get("target") or "").strip()
            input_text = str(row.get("input") or "").strip()
            if not note_text or not input_text:
                continue
            note_id = note_text_to_id[note_text]
            dedup_key = (input_text, note_id)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            built_rows.append(
                _build_row(
                    row,
                    note_id=note_id,
                    split_name=split_name,
                    dataset_name=str(row.get("dataset_name") or ""),
                )
            )
        split_rows[split_name] = built_rows

    promotion_report = _ensure_train_covers_all_note_ids(split_rows)
    all_rows = split_rows["train"] + split_rows["dev"] + split_rows["test"]
    note_type_counts = Counter(str(row.get("note_type") or "") for row in all_rows)
    dataset_counts = Counter(str(row.get("dataset_name") or "") for row in all_rows)
    label_counts = Counter(str(row.get("note_id") or "") for row in all_rows)

    out_dir = Path(output_dir)
    _write_jsonl(out_dir / "train.jsonl", split_rows["train"])
    _write_jsonl(out_dir / "dev.jsonl", split_rows["dev"])
    _write_jsonl(out_dir / "test.jsonl", split_rows["test"])
    _write_jsonl(out_dir / "all.jsonl", all_rows)
    (out_dir / "note_id_inventory.json").write_text(
        json.dumps(
            [
                {
                    "note_id": note_id,
                    "note_text": note_text,
                    "note_type": "template" if "{{" in note_text else "raw",
                }
                for note_text, note_id in sorted(note_text_to_id.items(), key=lambda item: item[1])
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = {
        "template_dataset_dir": str(Path(template_dataset_dir).resolve()),
        "raw_dataset_dir": str(Path(raw_dataset_dir).resolve()),
        "output_dir": str(out_dir.resolve()),
        "train_samples": len(split_rows["train"]),
        "dev_samples": len(split_rows["dev"]),
        "test_samples": len(split_rows["test"]),
        "all_samples": len(all_rows),
        "unique_note_ids": len(note_text_to_id),
        "note_type_counts": dict(sorted(note_type_counts.items())),
        "dataset_counts": dict(sorted(dataset_counts.items())),
        **promotion_report,
        "top_note_id_support": [
            {"note_id": note_id, "count": count}
            for note_id, count in label_counts.most_common(20)
        ],
    }
    (out_dir / "stats.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build note-id classifier dataset from template/raw paired datasets.")
    parser.add_argument(
        "--template-dataset-dir",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v40_paired_template_canonical_template_only_v1",
    )
    parser.add_argument(
        "--raw-dataset-dir",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v40_paired_template_canonical_raw_only_v1",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/classifier_note_id_v40",
    )
    args = parser.parse_args()
    summary = build_note_id_classifier_dataset(
        template_dataset_dir=args.template_dataset_dir,
        raw_dataset_dir=args.raw_dataset_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
