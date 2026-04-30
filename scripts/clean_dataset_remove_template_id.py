"""Remove template_id from dataset rows and serialized inputs.

This cleans existing JSONL datasets that were built before the prompt payload
stopped carrying template_id in the training input.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FILES = ("all.jsonl", "train.jsonl", "dev.jsonl", "test.jsonl")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _clean_input(text: str) -> tuple[str, bool]:
    marker = "payload: "
    if marker not in text:
        return text, False
    prefix, payload_text = text.split(marker, 1)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return text, False
    if isinstance(payload, dict):
        removed = _strip_template_id(payload)
        if removed:
            return f"{prefix}{marker}{json.dumps(payload, ensure_ascii=False, sort_keys=True)}", True
    return text, False


def _strip_template_id(value: Any) -> bool:
    removed = False
    if isinstance(value, dict):
        if "template_id" in value:
            value.pop("template_id", None)
            removed = True
        for item in value.values():
            removed = _strip_template_id(item) or removed
    elif isinstance(value, list):
        for item in value:
            removed = _strip_template_id(item) or removed
    return removed


def _clean_row(row: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
    cleaned = dict(row)
    removed_row_template_id = "template_id" in cleaned
    cleaned.pop("template_id", None)
    input_text = cleaned.get("input")
    removed_input_template_id = False
    if isinstance(input_text, str) and input_text.strip():
        cleaned_input, removed_input_template_id = _clean_input(input_text)
        cleaned["input"] = cleaned_input
    return cleaned, removed_row_template_id, removed_input_template_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove template_id from dataset rows and inputs.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cleanup_report: dict[str, Any] = {
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "files": {},
    }

    for filename in FILES:
        src = input_dir / filename
        rows = _load_jsonl(src)
        cleaned_rows: list[dict[str, Any]] = []
        removed_row_template_id = 0
        removed_input_template_id = 0
        for row in rows:
            cleaned, removed_row, removed_input = _clean_row(row)
            cleaned_rows.append(cleaned)
            removed_row_template_id += int(removed_row)
            removed_input_template_id += int(removed_input)
        _write_jsonl(output_dir / filename, cleaned_rows)
        cleanup_report["files"][filename] = {
            "rows": len(rows),
            "removed_row_template_id": removed_row_template_id,
            "removed_input_template_id": removed_input_template_id,
        }

    source_stats = input_dir / "stats.json"
    if source_stats.exists():
        try:
            cleanup_report["source_stats"] = json.loads(source_stats.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cleanup_report["source_stats"] = {"error": "invalid_json"}

    (output_dir / "stats.json").write_text(json.dumps(cleanup_report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
