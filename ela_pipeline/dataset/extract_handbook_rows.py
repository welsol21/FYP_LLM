"""Extract structured rows from handbook/article-style grammar books."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.azar_basic_grammar_adapter import extract_azar_basic_grammar_rows
from ela_pipeline.dataset.book_extraction.collins_cobuild_2011_adapter import (
    COLLINS_COBUILD_2011_CONFIG,
    extract_collins_cobuild_2011_rows,
)
from ela_pipeline.dataset.book_extraction.cobuild_grammar_adapter import (
    COBUILD_GRAMMAR_CONFIG,
    extract_cobuild_grammar_rows,
)
from ela_pipeline.dataset.book_extraction.english_for_everyone_practice_adapter import (
    extract_english_for_everyone_practice_rows,
)
from ela_pipeline.dataset.book_extraction.english_grammar_in_use_adapter import (
    extract_english_grammar_in_use_rows,
)
from ela_pipeline.dataset.book_extraction.english_grammar_today_adapter import extract_english_grammar_today_rows
from ela_pipeline.dataset.book_extraction.gswe_adapter import GSWE_CONFIG, extract_gswe_rows
from ela_pipeline.dataset.book_extraction.handbook_adapter import supports_payload
from ela_pipeline.dataset.book_extraction.introducing_english_grammar_adapter import (
    INTRODUCING_ENGLISH_GRAMMAR_CONFIG,
    extract_introducing_english_grammar_rows,
)
from ela_pipeline.dataset.book_extraction.mysteries_english_grammar_adapter import (
    MYSTERIES_ENGLISH_GRAMMAR_CONFIG,
    extract_mysteries_english_grammar_rows,
)
from ela_pipeline.dataset.book_extraction.oxford_handbook_adapter import (
    OXFORD_HANDBOOK_CONFIG,
    extract_oxford_handbook_rows,
)


ENGLISH_GRAMMAR_TODAY_PROFILE = "english_grammar_today"
ENGLISH_GRAMMAR_IN_USE_PROFILE = "english_grammar_in_use_5th_2019"
ENGLISH_FOR_EVERYONE_PRACTICE_PROFILE = "english_for_everyone_practice_2019"
AZAR_BASIC_GRAMMAR_PROFILE = "azar_basic_english_grammar_1996"
COLLINS_COBUILD_2011_PROFILE = COLLINS_COBUILD_2011_CONFIG.name
COBUILD_GRAMMAR_PROFILE = COBUILD_GRAMMAR_CONFIG.name
OXFORD_HANDBOOK_PROFILE = OXFORD_HANDBOOK_CONFIG.name
GSWE_PROFILE = GSWE_CONFIG.name
INTRODUCING_ENGLISH_GRAMMAR_PROFILE = INTRODUCING_ENGLISH_GRAMMAR_CONFIG.name
MYSTERIES_ENGLISH_GRAMMAR_PROFILE = MYSTERIES_ENGLISH_GRAMMAR_CONFIG.name


def _supports_english_grammar_today(payload: BookTextPayload) -> bool:
    lowered = f"{payload.source_path} {payload.metadata}".lower()
    return "english grammar today" in lowered


def _supports_english_grammar_in_use(payload: BookTextPayload) -> bool:
    lowered = f"{payload.source_path} {payload.metadata}".lower()
    return "english grammar in use" in lowered and "5th edition" in lowered


def _supports_english_for_everyone_practice(payload: BookTextPayload) -> bool:
    lowered = f"{payload.source_path} {payload.metadata}".lower()
    return "english for everyone" in lowered and "practice book" in lowered


def _supports_azar_basic_grammar(payload: BookTextPayload) -> bool:
    lowered = f"{payload.source_path} {payload.metadata}".lower()
    return "basic english grammar" in lowered and "azar" in lowered


PROFILE_HANDLERS = {
    AZAR_BASIC_GRAMMAR_PROFILE: (
        _supports_azar_basic_grammar,
        extract_azar_basic_grammar_rows,
    ),
    COLLINS_COBUILD_2011_PROFILE: (
        lambda payload: supports_payload(payload, COLLINS_COBUILD_2011_CONFIG),
        extract_collins_cobuild_2011_rows,
    ),
    COBUILD_GRAMMAR_PROFILE: (
        lambda payload: supports_payload(payload, COBUILD_GRAMMAR_CONFIG),
        extract_cobuild_grammar_rows,
    ),
    ENGLISH_FOR_EVERYONE_PRACTICE_PROFILE: (
        _supports_english_for_everyone_practice,
        extract_english_for_everyone_practice_rows,
    ),
    GSWE_PROFILE: (
        lambda payload: supports_payload(payload, GSWE_CONFIG),
        extract_gswe_rows,
    ),
    MYSTERIES_ENGLISH_GRAMMAR_PROFILE: (
        lambda payload: supports_payload(payload, MYSTERIES_ENGLISH_GRAMMAR_CONFIG),
        extract_mysteries_english_grammar_rows,
    ),
    INTRODUCING_ENGLISH_GRAMMAR_PROFILE: (
        lambda payload: supports_payload(payload, INTRODUCING_ENGLISH_GRAMMAR_CONFIG),
        extract_introducing_english_grammar_rows,
    ),
    ENGLISH_GRAMMAR_IN_USE_PROFILE: (
        _supports_english_grammar_in_use,
        extract_english_grammar_in_use_rows,
    ),
    OXFORD_HANDBOOK_PROFILE: (
        lambda payload: supports_payload(payload, OXFORD_HANDBOOK_CONFIG),
        extract_oxford_handbook_rows,
    ),
    ENGLISH_GRAMMAR_TODAY_PROFILE: (
        _supports_english_grammar_today,
        extract_english_grammar_today_rows,
    ),
}


def _write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract handbook/article-aware rows from a grammar book.")
    parser.add_argument("--payload-json", required=True)
    parser.add_argument("--profile", default=OXFORD_HANDBOOK_PROFILE, choices=sorted(PROFILE_HANDLERS))
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    payload_dict = json.loads(Path(args.payload_json).read_text(encoding="utf-8"))
    payload_txt = Path(args.payload_json).with_name("payload.txt")
    payload = BookTextPayload(
        source_path=str(payload_dict.get("source_path") or ""),
        parser_name=str(payload_dict.get("parser_name") or ""),
        format=str(payload_dict.get("format") or ""),
        text=payload_txt.read_text(encoding="utf-8", errors="ignore"),
        metadata=dict(payload_dict.get("metadata") or {}),
    )

    supports_fn, handler = PROFILE_HANDLERS[args.profile]
    if not supports_fn(payload):
        raise SystemExit(f"Unsupported payload for profile: {args.profile}")

    rows = [row.as_dict() for row in handler(payload)]
    report = {
        "pipeline_version": "handbook_rows_v2",
        "profile": args.profile,
        "source_path": payload.source_path,
        "rows_total": len(rows),
        "row_types": {
            key: sum(1 for row in rows if row.get("row_type") == key)
            for key in sorted({str(row.get("row_type") or "") for row in rows})
        },
        "topic_counts": {
            key: sum(1 for row in rows if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in rows})
        },
    }
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
