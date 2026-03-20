"""Selectively integrate rich T5-style notes into the base corpus.

The goal is to capture genuinely useful paraphrase value from a dense rich-note
layer without flooding the dataset with thousands of near-duplicate generic
notes.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


MODALS = {
    "can",
    "could",
    "may",
    "might",
    "must",
    "ought",
    "shall",
    "should",
    "will",
    "would",
    "can't",
    "couldn't",
    "mayn't",
    "mightn't",
    "mustn't",
    "oughtn't",
    "shan't",
    "shouldn't",
    "won't",
    "wouldn't",
}

SENTENCE_TOPIC_BLACKLIST = {"construction_profile", "legacy_verified"}
PHRASE_TOPIC_BLACKLIST = {"construction_profile", "finite_active"}

SENTENCE_NOTE_PREFIX_BLACKLIST = (
    "The sentence is built as",
    "This clause is declarative in form",
    "This is a statement clause",
)
PHRASE_NOTE_PREFIX_BLACKLIST = (
    "This is a ",
    "This is an ",
    "This verb phrase organizes",
    "This is a prepositional phrase headed by",
)

WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?")


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


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _row_key(row: dict[str, Any]) -> tuple[str, int, int]:
    span = row.get("source_span") or {}
    return (
        _norm(row.get("sentence_text")),
        int(span.get("start", -1)),
        int(span.get("end", -1)),
    )


def _phrase_key(phrase: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _norm(phrase.get("content")),
        _norm(phrase.get("part_of_speech")).lower(),
        _norm(phrase.get("grammatical_role")).lower(),
    )


def _candidate_identity(candidate: dict[str, Any]) -> tuple[str, str]:
    return (_norm(candidate.get("topic")), _norm(candidate.get("note_text")))


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def _sentence_note_is_valuable(candidate: dict[str, Any]) -> bool:
    topic = _norm(candidate.get("topic")).lower()
    note = _norm(candidate.get("note_text"))
    if not note:
        return False
    if topic in SENTENCE_TOPIC_BLACKLIST:
        return False
    if len(note) < 60 or len(note) > 260:
        return False
    if any(note.startswith(prefix) for prefix in SENTENCE_NOTE_PREFIX_BLACKLIST):
        return False
    return True


def _phrase_note_is_valuable(candidate: dict[str, Any], phrase_text: str) -> bool:
    topic = _norm(candidate.get("topic")).lower()
    note = _norm(candidate.get("note_text"))
    if not note:
        return False
    if topic in PHRASE_TOPIC_BLACKLIST:
        return False
    if len(note) < 60 or len(note) > 260:
        return False
    if any(note.startswith(prefix) for prefix in PHRASE_NOTE_PREFIX_BLACKLIST):
        return False
    if "modal" in topic:
        tokens = set(_tokens(phrase_text))
        if "need" in tokens and not (tokens & (MODALS - {"need"})):
            return False
        if not (tokens & MODALS):
            return False
    return True


def integrate_rich_notes(
    *,
    base_rows: list[dict[str, Any]],
    rich_rows: list[dict[str, Any]],
    max_examples_per_sentence_note: int,
    max_examples_per_phrase_note: int,
    projection_version: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rich_by_key = {_row_key(row): row for row in rich_rows}
    sentence_note_usage: Counter[tuple[str, str]] = Counter()
    phrase_note_usage: Counter[tuple[str, str]] = Counter()

    report = {
        "base_rows_total": len(base_rows),
        "rich_rows_total": len(rich_rows),
        "matched_rows_total": 0,
        "missing_rich_rows_total": 0,
        "sentence_candidates_added": 0,
        "phrase_candidates_added": 0,
        "rows_with_sentence_additions": 0,
        "rows_with_phrase_additions": 0,
        "unique_sentence_note_pairs_selected": 0,
        "unique_phrase_note_pairs_selected": 0,
        "sentence_rejections": Counter(),
        "phrase_rejections": Counter(),
    }

    output_rows: list[dict[str, Any]] = []

    for base_row in base_rows:
        key = _row_key(base_row)
        rich_row = rich_by_key.get(key)
        row = json.loads(json.dumps(base_row, ensure_ascii=False))
        row["projection_version"] = projection_version

        sentence_added_here = 0
        phrase_added_here = 0

        if rich_row is None:
            report["missing_rich_rows_total"] += 1
            output_rows.append(row)
            continue

        report["matched_rows_total"] += 1

        existing_sentence_ids = {_candidate_identity(candidate) for candidate in (row.get("sentence_note_candidates") or [])}
        for candidate in rich_row.get("sentence_note_candidates") or []:
            ident = _candidate_identity(candidate)
            if ident in existing_sentence_ids:
                report["sentence_rejections"]["already_present"] += 1
                continue
            if not _sentence_note_is_valuable(candidate):
                report["sentence_rejections"]["filtered_out"] += 1
                continue
            if sentence_note_usage[ident] >= max_examples_per_sentence_note:
                report["sentence_rejections"]["example_cap"] += 1
                continue
            row.setdefault("sentence_note_candidates", []).append(candidate)
            existing_sentence_ids.add(ident)
            sentence_note_usage[ident] += 1
            report["sentence_candidates_added"] += 1
            sentence_added_here += 1

        rich_phrases_by_key = {_phrase_key(phrase): phrase for phrase in (rich_row.get("phrase_entries") or [])}
        for phrase in row.get("phrase_entries") or []:
            rich_phrase = rich_phrases_by_key.get(_phrase_key(phrase))
            if rich_phrase is None:
                continue
            existing_phrase_ids = {_candidate_identity(candidate) for candidate in (phrase.get("note_candidates") or [])}
            for candidate in rich_phrase.get("note_candidates") or []:
                ident = _candidate_identity(candidate)
                if ident in existing_phrase_ids:
                    report["phrase_rejections"]["already_present"] += 1
                    continue
                if not _phrase_note_is_valuable(candidate, _norm(phrase.get("content"))):
                    report["phrase_rejections"]["filtered_out"] += 1
                    continue
                if phrase_note_usage[ident] >= max_examples_per_phrase_note:
                    report["phrase_rejections"]["example_cap"] += 1
                    continue
                phrase.setdefault("note_candidates", []).append(candidate)
                existing_phrase_ids.add(ident)
                phrase_note_usage[ident] += 1
                report["phrase_candidates_added"] += 1
                phrase_added_here += 1

        if sentence_added_here:
            report["rows_with_sentence_additions"] += 1
        if phrase_added_here:
            report["rows_with_phrase_additions"] += 1
        if sentence_added_here or phrase_added_here:
            row["rich_selective_meta"] = {
                "source": "ingested_corpus_book_projection_v8_rich_t5_notes",
                "integration_strategy": "selective_unique_paraphrase_enrichment",
            }

        output_rows.append(row)

    report["unique_sentence_note_pairs_selected"] = len(sentence_note_usage)
    report["unique_phrase_note_pairs_selected"] = len(phrase_note_usage)
    report["output_rows_total"] = len(output_rows)
    report["sentence_rejections"] = dict(report["sentence_rejections"])
    report["phrase_rejections"] = dict(report["phrase_rejections"])
    return output_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Selectively integrate rich T5 notes into the base corpus.")
    parser.add_argument("--base-input", required=True)
    parser.add_argument("--rich-input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--projection-version", default="book_note_corpus_projection_v10")
    parser.add_argument("--max-examples-per-sentence-note", type=int, default=2)
    parser.add_argument("--max-examples-per-phrase-note", type=int, default=2)
    args = parser.parse_args()

    rows, report = integrate_rich_notes(
        base_rows=list(_iter_jsonl(args.base_input)),
        rich_rows=list(_iter_jsonl(args.rich_input)),
        max_examples_per_sentence_note=args.max_examples_per_sentence_note,
        max_examples_per_phrase_note=args.max_examples_per_phrase_note,
        projection_version=args.projection_version,
    )
    report.update(
        {
            "base_input": str(Path(args.base_input).resolve()),
            "rich_input": str(Path(args.rich_input).resolve()),
            "projection_version": args.projection_version,
            "max_examples_per_sentence_note": args.max_examples_per_sentence_note,
            "max_examples_per_phrase_note": args.max_examples_per_phrase_note,
        }
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(rows),
                "output_jsonl": str(Path(args.output_jsonl).resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
