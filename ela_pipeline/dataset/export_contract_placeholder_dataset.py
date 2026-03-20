"""Export a flat placeholder-oriented dataset from contract template rows."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def export_contract_placeholder_dataset(
    *,
    input_jsonl: str,
    slot_only: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_rows = list(_iter_jsonl(input_jsonl))
    out_rows: list[dict[str, Any]] = []
    template_counts: Counter[str] = Counter()
    level_counts: Counter[str] = Counter()
    slotful = 0

    for row in source_rows:
        payload = row.get("contract_template_payload") or {}
        if not isinstance(payload, dict):
            continue
        template_text = str(payload.get("template_text") or "").strip()
        allowed_slots = [str(item).strip() for item in (payload.get("allowed_slots") or []) if str(item).strip()]
        slot_values = payload.get("slot_values") or {}
        if slot_only and not allowed_slots:
            continue
        exported = {
            "row_id": row.get("row_id"),
            "source_path": row.get("source_path"),
            "entry_head": row.get("entry_head"),
            "topic_key": row.get("topic_key"),
            "node_level": row.get("node_level"),
            "context_text": row.get("context_text"),
            "notation_text_raw": row.get("notation_text"),
            "pair_method": row.get("pair_method"),
            "template_version": payload.get("note_template_version"),
            "template_id": payload.get("template_id"),
            "template_text": template_text,
            "allowed_slots": allowed_slots,
            "slot_values": {slot: slot_values.get(slot) for slot in allowed_slots},
            "rendered_note_text": payload.get("rendered_note_text"),
            "render_status": payload.get("render_status"),
            "matched_template_id": row.get("matched_template_id"),
            "book_template_id": row.get("book_template_id"),
        }
        out_rows.append(exported)
        template_counts[str(exported.get("template_id") or "")] += 1
        level_counts[str(exported.get("node_level") or "")] += 1
        if allowed_slots:
            slotful += 1

    report = {
        "pipeline_version": "contract_placeholder_export_v1",
        "input_jsonl": str(Path(input_jsonl).resolve()),
        "rows_total": len(out_rows),
        "slot_only": bool(slot_only),
        "slot_bearing_rows": slotful,
        "level_counts": dict(level_counts),
        "template_counts": dict(template_counts.most_common()),
    }
    return out_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a flat placeholder dataset from contract template rows.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--slot-only", action="store_true")
    args = parser.parse_args()

    rows, report = export_contract_placeholder_dataset(
        input_jsonl=args.input_jsonl,
        slot_only=bool(args.slot_only),
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
