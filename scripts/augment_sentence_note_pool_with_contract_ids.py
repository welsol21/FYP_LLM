from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ela_pipeline.dataset.contract_signatures import (
    contract_bucketed_signature,
    contract_exact_signature,
    contract_presence_signature,
)
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _family_id(prefix: str, signature: Any) -> str:
    digest = hashlib.sha1(repr(signature).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sentence_contract_ids(sentence_text: str, nlp: Any) -> dict[str, str] | None:
    skeleton = build_skeleton(sentence_text, nlp)
    for parsed_sentence, sentence_node in skeleton.items():
        if _norm(parsed_sentence) != _norm(sentence_text):
            continue
        exact = contract_exact_signature(sentence_node)
        return {
            "contract_exact_family_id": _family_id("sent_contract_exact", exact),
            "contract_bucketed_family_id": _family_id("sent_contract_bucket", contract_bucketed_signature(exact)),
            "contract_presence_family_id": _family_id("sent_contract_presence", contract_presence_signature(exact)),
        }
    first_node = next(iter(skeleton.values()), None)
    if first_node is None:
        return None
    exact = contract_exact_signature(first_node)
    return {
        "contract_exact_family_id": _family_id("sent_contract_exact", exact),
        "contract_bucketed_family_id": _family_id("sent_contract_bucket", contract_bucketed_signature(exact)),
        "contract_presence_family_id": _family_id("sent_contract_presence", contract_presence_signature(exact)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Add contract-based family ids to sentence note pool rows.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    nlp = load_nlp(args.spacy_model)
    rows_out: list[dict[str, Any]] = []
    updated = 0
    skipped = 0

    for row in _iter_jsonl(Path(args.input_jsonl)):
        context = row.get("context") or {}
        sentence_text = _norm(context.get("sentence_text") or context.get("content"))
        if not sentence_text:
            skipped += 1
            rows_out.append(row)
            continue
        contract_ids = _sentence_contract_ids(sentence_text, nlp)
        if contract_ids is None:
            skipped += 1
            rows_out.append(row)
            continue
        sentence_alignment = ((row.get("family_alignment") or {}).get("sentence") or {}).copy()
        sentence_alignment.update(contract_ids)
        family_alignment = (row.get("family_alignment") or {}).copy()
        family_alignment["sentence"] = sentence_alignment
        row["family_alignment"] = family_alignment
        rows_out.append(row)
        updated += 1

    _write_jsonl(Path(args.output_jsonl), rows_out)
    _write_json(
        Path(args.report_json),
        {
            "input_jsonl": str(Path(args.input_jsonl).resolve()),
            "output_jsonl": str(Path(args.output_jsonl).resolve()),
            "rows_total": len(rows_out),
            "rows_updated": updated,
            "rows_skipped": skipped,
        },
    )


if __name__ == "__main__":
    main()
