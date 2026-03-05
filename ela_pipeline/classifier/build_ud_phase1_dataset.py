"""Build Phase 1 classifier dataset from UD CoNLL-U sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .dataset_protocol import normalize_classifier_row
from .grammar_blueprints import PEDAGOGICAL_CLASS_SPECS
from .ud_phase1 import extract_phase1_grammar_signal, load_ud_conllu, validate_phase1_dataset_gates

PHASE1_CLASS_SPECS = PEDAGOGICAL_CLASS_SPECS


def resolve_ud_split_map(treebank_dir: str) -> dict[str, Path]:
    root = Path(treebank_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"treebank_dir not found: {treebank_dir}")
    split_map: dict[str, Path] = {}
    for split in ("train", "dev", "test"):
        matches = sorted(root.glob(f"*-ud-{split}.conllu"))
        if not matches:
            raise FileNotFoundError(f"Missing UD split file '*-ud-{split}.conllu' in {treebank_dir}")
        split_map[split] = matches[0]
    return split_map


def _compose_classifier_input(row: dict[str, Any]) -> str:
    evidence = row.get("grammar_evidence") if isinstance(row.get("grammar_evidence"), dict) else {}
    dep_signature = ",".join(str(v) for v in evidence.get("dep_signature", [])[:12])
    pos_signature = ",".join(str(v) for v in evidence.get("pos_signature", [])[:12])
    tam_profile = str(row.get("tam_profile") or "unknown").strip()
    text = str(row.get("text") or "").strip()
    return (
        "task: classify_cefr_and_grammar "
        f"tam_profile: {tam_profile} "
        f"dep_signature: {dep_signature} "
        f"pos_signature: {pos_signature} "
        f"text: {text}"
    )


def _to_classifier_payload(row: dict[str, Any]) -> dict[str, Any]:
    return normalize_classifier_row(
        {
            **row,
            "input": _compose_classifier_input(row),
            "cefr_label": row.get("cefr_level"),
            "source_text": row.get("text"),
        }
    )


def _row_from_ud_sentence(sentence: dict[str, Any], *, row_id: str) -> dict[str, Any] | None:
    signal = extract_phase1_grammar_signal(sentence)
    grammar_classes = signal.get("grammar_classes")
    if not isinstance(grammar_classes, list) or not grammar_classes:
        return None

    accepted = [class_id for class_id in grammar_classes if class_id in PHASE1_CLASS_SPECS]
    if not accepted:
        return None

    class_id = accepted[0]
    spec = PHASE1_CLASS_SPECS[class_id]
    return {
        "id": row_id,
        "text": str(sentence.get("text") or "").strip(),
        "cefr_level": spec["cefr_level"],
        "grammar_classes": accepted,
        "tam_profile": signal.get("tam_profile"),
        "grammar_evidence": signal.get("grammar_evidence"),
        "note_blueprints": {
            "elementary_text": spec["elementary_text"],
            "intermediate_text": spec["intermediate_text"],
            "advanced_text": spec["advanced_text"],
        },
        "provenance": sentence.get("provenance") if isinstance(sentence.get("provenance"), dict) else {},
    }


def build_phase1_dataset_from_ud(
    *,
    input_paths: list[str],
    output_dir: str,
    treebank: str,
    split: str,
    allowed_genres: list[str] | None = None,
    prebuilt_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / f"{split}_ud_phase1_classifier.jsonl"
    rejected_path = out_dir / f"{split}_ud_phase1_rejected.jsonl"
    gate_path = out_dir / f"{split}_ud_phase1_gate_report.json"

    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    filtered_out_rows = 0
    allowed_genre_set = {str(value).strip().lower() for value in (allowed_genres or []) if str(value).strip()}

    if prebuilt_rows is not None:
        for row in prebuilt_rows:
            provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
            genre = str(provenance.get("genre") or "").strip().lower()
            if allowed_genre_set and genre not in allowed_genre_set:
                filtered_out_rows += 1
                continue
            rows.append(row)
    else:
        idx = 0
        for input_path in input_paths:
            sentences = load_ud_conllu(input_path=input_path, treebank=treebank, split=split)
            for sentence in sentences:
                provenance = sentence.get("provenance") if isinstance(sentence.get("provenance"), dict) else {}
                genre = str(provenance.get("genre") or "").strip().lower()
                if allowed_genre_set and genre not in allowed_genre_set:
                    filtered_out_rows += 1
                    continue
                idx += 1
                built = _row_from_ud_sentence(sentence, row_id=f"{split}-{idx}")
                if built is None:
                    rejected.append(
                        {
                            "text": str(sentence.get("text") or "").strip(),
                            "provenance": sentence.get("provenance"),
                            "reason": "no_phase1_mapping",
                        }
                    )
                    continue
                rows.append(built)

    gate_report = validate_phase1_dataset_gates(rows)
    accepted_rows = rows if gate_report["passed"] else []
    if not gate_report["passed"]:
        for row in rows:
            rejected.append(
                {
                    "text": row.get("text"),
                    "provenance": row.get("provenance"),
                    "reason": "failed_dataset_gates",
                }
            )

    with dataset_path.open("w", encoding="utf-8") as f:
        for row in accepted_rows:
            payload = _to_classifier_payload(row)
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    with rejected_path.open("w", encoding="utf-8") as f:
        for row in rejected:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    gate_path.write_text(json.dumps(gate_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "dataset_path": str(dataset_path),
        "rejected_path": str(rejected_path),
        "gate_report_path": str(gate_path),
        "gate_report": gate_report,
        "accepted_rows": len(accepted_rows),
        "rejected_rows": len(rejected),
        "filtered_out_rows": filtered_out_rows,
        "allowed_genres": sorted(allowed_genre_set),
    }


def build_merged_ud_dataset(
    *,
    input_paths: list[str],
    output_dir: str,
    split: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    deduplicated_rows = 0

    for input_path in input_paths:
        src = Path(input_path)
        if not src.is_file():
            raise FileNotFoundError(f"merged dataset source not found: {input_path}")
        for line in src.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            text_key = str(row.get("text") or "").strip().lower()
            if text_key and text_key in seen_texts:
                deduplicated_rows += 1
                continue
            if text_key:
                seen_texts.add(text_key)
            rows.append(row)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / f"{split}_ud_merged_classifier.jsonl"
    gate_path = out_dir / f"{split}_ud_merged_gate_report.json"

    gate_report = validate_phase1_dataset_gates(rows)
    accepted_rows = rows if gate_report["passed"] else []

    with dataset_path.open("w", encoding="utf-8") as f:
        for row in accepted_rows:
            payload = _to_classifier_payload(row)
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    gate_path.write_text(json.dumps(gate_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "dataset_path": str(dataset_path),
        "gate_report_path": str(gate_path),
        "gate_report": gate_report,
        "accepted_rows": len(accepted_rows),
        "deduplicated_rows": deduplicated_rows,
    }


def build_phase1_treebank_dataset(
    *,
    treebank_dir: str,
    output_dir: str,
    treebank_name: str = "UD_English-EWT",
) -> dict[str, Any]:
    root = Path(treebank_dir)
    split_map = resolve_ud_split_map(treebank_dir)
    summary: dict[str, Any] = {
        "treebank": treebank_name,
        "treebank_dir": str(root),
        "splits": {},
    }
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    for split, path in split_map.items():
        result = build_phase1_dataset_from_ud(
            input_paths=[str(path)],
            output_dir=str(out_root / split),
            treebank=treebank_name,
            split=split,
        )
        summary["splits"][split] = result

    summary_path = out_root / "phase1_ud_treebank_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 1 classifier dataset from UD CoNLL-U sources.")
    parser.add_argument("--input-path", action="append", default=[])
    parser.add_argument("--output-dir", default="data/processed_classifier/ud_phase1")
    parser.add_argument("--treebank", default="UD_English-EWT")
    parser.add_argument("--split", default="train")
    parser.add_argument("--treebank-dir", default="")
    args = parser.parse_args()

    if str(args.treebank_dir or "").strip():
        summary = build_phase1_treebank_dataset(
            treebank_dir=args.treebank_dir,
            output_dir=args.output_dir,
            treebank_name=args.treebank,
        )
    else:
        if not args.input_path:
            parser.error("either --treebank-dir or at least one --input-path must be provided")
        summary = build_phase1_dataset_from_ud(
            input_paths=args.input_path,
            output_dir=args.output_dir,
            treebank=args.treebank,
            split=args.split,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
