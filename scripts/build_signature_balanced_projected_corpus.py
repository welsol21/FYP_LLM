from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _signature_value(row: dict[str, Any], signature_level: str) -> str:
    alignment = row.get("sentence_family_alignment") or {}
    if signature_level == "exact":
        return str(alignment.get("contract_exact_family_id") or alignment.get("exact_family_id") or "").strip()
    if signature_level == "sentence_exact":
        return str(alignment.get("exact_family_id") or "").strip()
    if signature_level == "bucketed":
        return str(alignment.get("contract_bucketed_family_id") or alignment.get("bucketed_family_id") or "").strip()
    if signature_level == "sentence_bucketed":
        return str(alignment.get("bucketed_family_id") or "").strip()
    if signature_level == "presence":
        return str(alignment.get("contract_presence_family_id") or alignment.get("presence_family_id") or "").strip()
    if signature_level == "sentence_presence":
        return str(alignment.get("presence_family_id") or "").strip()
    raise ValueError(f"Unsupported signature_level: {signature_level}")


def _candidate_target_count(row: dict[str, Any]) -> int:
    targets = {
        str(candidate.get("note_text") or "").strip().lower()
        for candidate in (row.get("sentence_note_candidates") or [])
        if str(candidate.get("note_text") or "").strip()
    }
    return len(targets)


def _row_priority(row: dict[str, Any]) -> tuple[Any, ...]:
    candidates = row.get("sentence_note_candidates") or []
    source_document = row.get("source_document") or {}
    return (
        -len(candidates),
        -_candidate_target_count(row),
        str(source_document.get("source_name") or ""),
        str(source_document.get("id") or ""),
        str(row.get("sentence_text") or ""),
    )


def build_signature_balanced_projected_corpus(
    *,
    input_jsonl: str,
    output_jsonl: str,
    report_json: str,
    signature_level: str,
    max_rows_per_signature: int,
    require_note_candidates: bool = True,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_rows = 0
    skipped_missing_signature = 0
    skipped_without_candidates = 0

    for row in _iter_jsonl(input_jsonl):
        total_rows += 1
        signature = _signature_value(row, signature_level)
        if not signature:
            skipped_missing_signature += 1
            continue
        if require_note_candidates and not (row.get("sentence_note_candidates") or []):
            skipped_without_candidates += 1
            continue
        grouped[signature].append(row)

    kept_rows: list[dict[str, Any]] = []
    kept_per_signature: Counter[str] = Counter()
    dropped_by_signature_cap = 0
    source_name_counts: Counter[str] = Counter()

    for signature, rows in grouped.items():
        rows_sorted = sorted(rows, key=_row_priority)
        selected = rows_sorted[:max_rows_per_signature] if max_rows_per_signature > 0 else rows_sorted
        kept_rows.extend(selected)
        kept_per_signature[signature] = len(selected)
        dropped_by_signature_cap += max(0, len(rows_sorted) - len(selected))
        for row in selected:
            source_document = row.get("source_document") or {}
            source_name = str(source_document.get("source_name") or "unknown").strip() or "unknown"
            source_name_counts[source_name] += 1

    out_path = Path(output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in kept_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    signature_size_counts = Counter(len(rows) for rows in grouped.values())
    report = {
        "input_jsonl": str(Path(input_jsonl).resolve()),
        "output_jsonl": str(out_path.resolve()),
        "signature_level": signature_level,
        "max_rows_per_signature": max_rows_per_signature,
        "require_note_candidates": require_note_candidates,
        "total_rows_read": total_rows,
        "rows_grouped": sum(len(rows) for rows in grouped.values()),
        "rows_written": len(kept_rows),
        "unique_signatures": len(grouped),
        "skipped_missing_signature": skipped_missing_signature,
        "skipped_without_candidates": skipped_without_candidates,
        "dropped_by_signature_cap": dropped_by_signature_cap,
        "source_name_counts": dict(sorted(source_name_counts.items())),
        "signature_size_distribution": {
            str(size): count for size, count in sorted(signature_size_counts.items())
        },
        "top_signature_counts": [
            {"signature": sig, "count": count}
            for sig, count in Counter({sig: len(rows) for sig, rows in grouped.items()}).most_common(25)
        ],
        "top_written_signature_counts": [
            {"signature": sig, "count": count}
            for sig, count in kept_per_signature.most_common(25)
        ],
    }

    report_path = Path(report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Balance a projected sentence corpus by sentence-family signature.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument(
        "--signature-level",
        choices=["exact", "sentence_exact", "bucketed", "sentence_bucketed", "presence", "sentence_presence"],
        default="exact",
    )
    parser.add_argument("--max-rows-per-signature", type=int, default=5)
    parser.add_argument(
        "--require-note-candidates",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()

    report = build_signature_balanced_projected_corpus(
        input_jsonl=args.input_jsonl,
        output_jsonl=args.output_jsonl,
        report_json=args.report_json,
        signature_level=args.signature_level,
        max_rows_per_signature=int(args.max_rows_per_signature),
        require_note_candidates=bool(args.require_note_candidates),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
