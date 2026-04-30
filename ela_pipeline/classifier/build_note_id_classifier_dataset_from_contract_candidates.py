"""Build contract-input raw note-id dataset from the full projected sentence candidate pool."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.contract_template_builder import build_contract_template_payload, build_contract_template_training_prompt
from ela_pipeline.dataset.build_t5_dataset_from_projected_corpus import BOOK_WHITELIST, _build_sentence_stub, _document_id, _sentence_candidate_ok


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


def _note_id(note_text: str) -> str:
    digest = hashlib.sha1(note_text.encode("utf-8")).hexdigest()[:12]
    return f"note_{digest}"


def _raw_note_text(candidate: dict[str, Any]) -> str:
    return str(candidate.get("slot_rendered_note") or candidate.get("note_text") or "").strip()


def _make_input_prompt(item: dict[str, Any]) -> str:
    sentence_stub = _build_sentence_stub(item)
    payload = build_contract_template_payload(
        node=sentence_stub,
        sentence_node=sentence_stub,
        parent=None,
        path_types=["Sentence"],
        depth=0,
        sibling_index=0,
        sibling_count=1,
    )
    return build_contract_template_training_prompt(payload or {}, node_level="Sentence")


def _build_candidate_rows(projected_path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _iter_jsonl(projected_path):
        sentence_text = str(item.get("sentence_text") or "").strip()
        if not sentence_text:
            continue
        input_prompt = _make_input_prompt(item)
        source_document = item.get("source_document") or {}
        split_group_id = _document_id(item)
        for candidate in item.get("sentence_note_candidates") or []:
            source_book = str(candidate.get("source_book") or "")
            if source_book not in BOOK_WHITELIST:
                continue
            if not _sentence_candidate_ok(candidate, sentence_text):
                continue
            note_text = _raw_note_text(candidate)
            if not note_text:
                continue
            out.append(
                {
                    "input": input_prompt,
                    "text": input_prompt,
                    "source_text": input_prompt,
                    "sentence_text": sentence_text,
                    "note_text": note_text,
                    "note_id": _note_id(note_text),
                    "note_type": "raw",
                    "dataset_name": "contract_candidate_raw_sentence",
                    "prompt_template_version": "contract_template_v2",
                    "template_id": str(candidate.get("topic") or "").strip(),
                    "note_source_book": source_book,
                    "note_topic": str(candidate.get("topic") or "").strip(),
                    "projection_version": str(item.get("projection_version") or "").strip(),
                    "grammar_evidence": {},
                    "grammar_classes": [],
                    "provenance": {
                        "dataset_source": "note_id_classifier_contract_candidates_v1",
                        "treebank": str(source_document.get("source_name") or "").strip() or "contract_sentence",
                        "source_document_id": str(source_document.get("id") or "").strip(),
                        "split_group_id": split_group_id,
                    },
                    "split_group_id": split_group_id,
                }
            )
    return out


def _dedup_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("input") or ""), str(row.get("note_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _drop_ambiguous_inputs(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    input_to_note_ids: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        input_to_note_ids[str(row.get("input") or "")].add(str(row.get("note_id") or ""))
    kept = [row for row in rows if len(input_to_note_ids[str(row.get("input") or "")]) == 1]
    return kept, {
        "inputs_total": len(input_to_note_ids),
        "inputs_unambiguous": sum(1 for note_ids in input_to_note_ids.values() if len(note_ids) == 1),
        "inputs_ambiguous": sum(1 for note_ids in input_to_note_ids.values() if len(note_ids) > 1),
        "rows_dropped_for_ambiguity": len(rows) - len(kept),
    }


def _split_by_group(rows: list[dict[str, Any]], *, seed: int, dev_ratio: float, test_ratio: float):
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("split_group_id") or "unknown")].append(row)
    items = list(grouped.items())
    random.Random(seed).shuffle(items)
    total = len(rows)
    target_dev = int(total * dev_ratio)
    target_test = int(total * test_ratio)
    train: list[dict[str, Any]] = []
    dev: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    for _, group_rows in items:
        if len(test) < target_test:
            test.extend(group_rows)
        elif len(dev) < target_dev:
            dev.extend(group_rows)
        else:
            train.extend(group_rows)
    return train, dev, test


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


def build_dataset(*, input_path: str, output_dir: str, seed: int = 42, dev_ratio: float = 0.1, test_ratio: float = 0.1) -> dict[str, Any]:
    projected_path = Path(input_path)
    candidate_rows = _build_candidate_rows(projected_path)
    deduped = _dedup_rows(candidate_rows)
    unambiguous, ambiguity_report = _drop_ambiguous_inputs(deduped)
    train, dev, test = _split_by_group(unambiguous, seed=seed, dev_ratio=dev_ratio, test_ratio=test_ratio)
    split_rows = {"train": train, "dev": dev, "test": test}
    coverage_report = _ensure_train_covers_all_note_ids(split_rows)
    all_rows = split_rows["train"] + split_rows["dev"] + split_rows["test"]

    out_dir = Path(output_dir)
    for split_name, rows in split_rows.items():
        _write_jsonl(out_dir / f"{split_name}.jsonl", rows)
    _write_jsonl(out_dir / "all.jsonl", all_rows)

    inventory = sorted(
        {
            (str(row.get("note_id") or ""), str(row.get("note_text") or ""))
            for row in all_rows
            if str(row.get("note_id") or "") and str(row.get("note_text") or "")
        }
    )
    (out_dir / "note_id_inventory.json").write_text(
        json.dumps(
            [{"note_id": note_id, "note_text": note_text, "note_type": "raw"} for note_id, note_text in inventory],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "input_path": str(projected_path.resolve()),
        "output_dir": str(out_dir.resolve()),
        "candidate_rows": len(candidate_rows),
        "deduped_rows": len(deduped),
        "unambiguous_rows": len(unambiguous),
        "train_samples": len(split_rows["train"]),
        "dev_samples": len(split_rows["dev"]),
        "test_samples": len(split_rows["test"]),
        "all_samples": len(all_rows),
        "unique_note_ids": len(inventory),
        "prompt_template_version": "contract_template_v2",
        **ambiguity_report,
        **coverage_report,
        "top_note_id_support": [
            {"note_id": note_id, "count": count}
            for note_id, count in Counter(str(row.get("note_id") or "") for row in all_rows).most_common(25)
        ],
    }
    (out_dir / "stats.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unambiguous contract-input raw note-id dataset from projected sentence candidates.")
    parser.add_argument(
        "--input-path",
        default="data/processed_corpus_book_projection_v16/ingested_corpus_book_projection_v16.covered_only.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/classifier_note_id_contract_candidates_v1",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    args = parser.parse_args()
    summary = build_dataset(
        input_path=args.input_path,
        output_dir=args.output_dir,
        seed=args.seed,
        dev_ratio=args.dev_ratio,
        test_ratio=args.test_ratio,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
