from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any


REQUIRED_TOP = ("id", "text", "cefr_level", "grammar_classes", "note_blueprints")
REQUIRED_NB = ("elementary_text", "intermediate_text", "advanced_text")
ALLOWED_CEFR = {"A1", "A2", "B1"}


def _load_label_inventory(path: Path) -> set[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {str(k) for k in raw.keys()}
    if isinstance(raw, list):
        out: set[str] = set()
        for item in raw:
            if isinstance(item, str):
                out.add(item)
            elif isinstance(item, dict):
                class_id = item.get("class_id") or item.get("id")
                if class_id:
                    out.add(str(class_id))
        return out
    raise ValueError(f"Unsupported label inventory format: {path}")


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
            yield line_no, row


def _validate_row(row: dict[str, Any], *, where: str, valid_classes: set[str]) -> None:
    for key in REQUIRED_TOP:
        if key not in row:
            raise ValueError(f"{where}: missing field '{key}'")

    text = str(row.get("text") or "").strip()
    if not text:
        raise ValueError(f"{where}: empty text")

    cefr = str(row.get("cefr_level") or "").strip().upper()
    if cefr not in ALLOWED_CEFR:
        raise ValueError(f"{where}: invalid cefr_level '{cefr}'")

    grammar = row.get("grammar_classes")
    if not isinstance(grammar, list) or not grammar:
        raise ValueError(f"{where}: grammar_classes must be non-empty list")
    for cls in grammar:
        cls_str = str(cls)
        if cls_str not in valid_classes:
            raise ValueError(f"{where}: unknown grammar class '{cls_str}'")

    nb = row.get("note_blueprints")
    if not isinstance(nb, dict):
        raise ValueError(f"{where}: note_blueprints must be object")
    for key in REQUIRED_NB:
        val = nb.get(key)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{where}: note_blueprints.{key} must be non-empty string")


def _compose_classifier_input(text: str) -> str:
    return f"task: classify_cefr_and_grammar text: {text.strip()}"


def _convert_split_to_classifier(src_path: Path, dst_path: Path, valid_classes: set[str]) -> int:
    count = 0
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with dst_path.open("w", encoding="utf-8") as out:
        for line_no, row in _iter_jsonl(src_path):
            _validate_row(row, where=f"{src_path.name}:{line_no}", valid_classes=valid_classes)
            payload = {
                "id": row["id"],
                "input": _compose_classifier_input(str(row["text"])),
                "cefr_label": str(row["cefr_level"]).upper(),
                "grammar_classes": [str(x) for x in row["grammar_classes"]],
                "note_blueprints": row["note_blueprints"],
                "source_text": str(row["text"]),
            }
            out.write(json.dumps(payload, ensure_ascii=False) + "\n")
            count += 1
    return count


def _extract_zip(src_zip: Path, dst_dir: Path) -> None:
    if not src_zip.is_file():
        raise FileNotFoundError(f"Zip not found: {src_zip}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src_zip, "r") as zf:
        zf.extractall(dst_dir)


def import_phase1_datasets(
    *,
    training_zip_path: str,
    validation_zip_path: str,
    archive_dir: str = "data/external_datasets/phase1",
    extracted_dir: str = "data/external_datasets/phase1/unpacked",
    output_dir: str = "data/processed_classifier/phase1",
) -> dict[str, Any]:
    training_zip = Path(training_zip_path)
    validation_zip = Path(validation_zip_path)

    archive_root = Path(archive_dir)
    archive_root.mkdir(parents=True, exist_ok=True)
    archived_training_zip = archive_root / training_zip.name
    archived_validation_zip = archive_root / validation_zip.name
    shutil.copy2(training_zip, archived_training_zip)
    shutil.copy2(validation_zip, archived_validation_zip)

    extracted_root = Path(extracted_dir)
    training_dir = extracted_root / "training"
    validation_dir = extracted_root / "validation"
    if training_dir.exists():
        shutil.rmtree(training_dir)
    if validation_dir.exists():
        shutil.rmtree(validation_dir)

    _extract_zip(archived_training_zip, training_dir)
    _extract_zip(archived_validation_zip, validation_dir)

    train_inv = _load_label_inventory(training_dir / "label_inventory.json")
    val_inv = _load_label_inventory(validation_dir / "label_inventory.json")
    if train_inv != val_inv:
        missing_in_val = sorted(train_inv - val_inv)
        missing_in_train = sorted(val_inv - train_inv)
        raise ValueError(
            "Training/validation label inventories differ: "
            f"missing_in_validation={missing_in_val[:5]} missing_in_training={missing_in_train[:5]}"
        )

    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    counts = {
        "train": _convert_split_to_classifier(training_dir / "train.jsonl", out_root / "train_classifier.jsonl", train_inv),
        "dev": _convert_split_to_classifier(training_dir / "dev.jsonl", out_root / "dev_classifier.jsonl", train_inv),
        "test": _convert_split_to_classifier(training_dir / "test.jsonl", out_root / "test_classifier.jsonl", train_inv),
        "validation_core": _convert_split_to_classifier(
            validation_dir / "validation_core.jsonl", out_root / "validation_core_classifier.jsonl", train_inv
        ),
        "validation_challenge": _convert_split_to_classifier(
            validation_dir / "validation_challenge.jsonl", out_root / "validation_challenge_classifier.jsonl", train_inv
        ),
    }

    manifest = {
        "training_zip": str(archived_training_zip),
        "validation_zip": str(archived_validation_zip),
        "extracted_training": str(training_dir),
        "extracted_validation": str(validation_dir),
        "output_dir": str(out_root),
        "label_count": len(train_inv),
        "counts": counts,
        "output_files": {
            k: str(v)
            for k, v in {
                "train": out_root / "train_classifier.jsonl",
                "dev": out_root / "dev_classifier.jsonl",
                "test": out_root / "test_classifier.jsonl",
                "validation_core": out_root / "validation_core_classifier.jsonl",
                "validation_challenge": out_root / "validation_challenge_classifier.jsonl",
            }.items()
        },
    }

    manifest_path = out_root / "phase1_import_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Import external Phase-1 datasets into classifier working format.")
    parser.add_argument("--training-zip-path", required=True)
    parser.add_argument("--validation-zip-path", required=True)
    parser.add_argument("--archive-dir", default="data/external_datasets/phase1")
    parser.add_argument("--extracted-dir", default="data/external_datasets/phase1/unpacked")
    parser.add_argument("--output-dir", default="data/processed_classifier/phase1")
    args = parser.parse_args()

    summary = import_phase1_datasets(
        training_zip_path=args.training_zip_path,
        validation_zip_path=args.validation_zip_path,
        archive_dir=args.archive_dir,
        extracted_dir=args.extracted_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
