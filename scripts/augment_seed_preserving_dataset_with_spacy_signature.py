from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


DEFAULT_INPUT_DIR = "data/processed_sentence_seed/seed_preserving_sentence_dataset_v16_patternized_v2"
DEFAULT_OUTPUT_DIR = "data/processed_sentence_seed/seed_preserving_sentence_dataset_v17_signature_depth2"
SPACY_SIGNATURE_DEPTH = 2


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


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _sort_children(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            int((item.get("source_span") or {}).get("start", 0)),
            int((item.get("source_span") or {}).get("end", 0)),
            0 if str(item.get("type") or "") == "Word" else 1,
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


def _signature_family_id(signature: str) -> str:
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    return f"spacy_sig_{digest}"


def _build_note_id(row: dict[str, Any], target_text: str) -> str:
    candidate = str(row.get("seed_row_id") or row.get("note_id") or "").strip()
    if candidate:
        return candidate
    payload = f"{row.get('sentence_text') or ''}::{target_text}".encode("utf-8")
    return f"note_{hashlib.sha1(payload).hexdigest()[:12]}"


def _augment_rows(rows: list[dict[str, Any]], *, nlp: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    augmented: list[dict[str, Any]] = []
    signature_counts: Counter[str] = Counter()
    empty_signature_rows = 0

    for row in rows:
        sentence_text = _norm(row.get("sentence_text"))
        if not sentence_text:
            continue
        parsed = build_skeleton(sentence_text, nlp)
        if not parsed:
            continue
        sentence_node = next(iter(parsed.values()))
        signature_nodes = _build_spacy_signature(sentence_node, depth=SPACY_SIGNATURE_DEPTH)
        signature_text = " -> ".join(signature_nodes)
        if not signature_text:
            empty_signature_rows += 1
        signature_counts[signature_text] += 1

        target_text = _norm(row.get("target_rendered") or row.get("target") or row.get("target_raw") or row.get("note_text"))
        source_text = _norm(row.get("source_name") or row.get("note_source_book") or row.get("projection_version") or "")
        new_row = dict(row)
        new_row["note_text"] = target_text
        new_row["note_id"] = _build_note_id(row, target_text)
        new_row["source"] = source_text
        new_row["spacy_signature_depth"] = SPACY_SIGNATURE_DEPTH
        new_row["spacy_signature"] = signature_text
        new_row["spacy_signature_nodes"] = signature_nodes
        new_row["spacy_signature_family_id"] = _signature_family_id(signature_text)
        augmented.append(new_row)

    report = {
        "rows_input": len(rows),
        "rows_output": len(augmented),
        "spacy_signature_depth": SPACY_SIGNATURE_DEPTH,
        "unique_spacy_signatures": len(signature_counts),
        "empty_signature_rows": empty_signature_rows,
        "top_spacy_signatures": [
            {"signature": signature, "count": count}
            for signature, count in signature_counts.most_common(20)
        ],
    }
    return augmented, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Add spacy signature fields to the seed-preserving dataset.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    nlp = load_nlp(args.spacy_model)
    all_rows: list[dict[str, Any]] = []
    for split in ("train", "dev", "test"):
        split_rows = list(_iter_jsonl(input_dir / f"{split}.jsonl"))
        augmented, _ = _augment_rows(split_rows, nlp=nlp)
        _write_jsonl(output_dir / f"{split}.jsonl", augmented)
        all_rows.extend(augmented)

    _write_jsonl(output_dir / "all.jsonl", all_rows)

    report_path = output_dir / "stats.json"
    report = {
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "rows_total": len(all_rows),
        "unique_notes": len({str(row.get("note_text") or "").strip() for row in all_rows if str(row.get("note_text") or "").strip()}),
        "unique_spacy_signatures": len({str(row.get("spacy_signature") or "").strip() for row in all_rows if str(row.get("spacy_signature") or "").strip()}),
        "spacy_signature_depth": SPACY_SIGNATURE_DEPTH,
        "note_coverage": dict(sorted(Counter(str(row.get("note_text") or "").strip() for row in all_rows if str(row.get("note_text") or "").strip()).items())),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
