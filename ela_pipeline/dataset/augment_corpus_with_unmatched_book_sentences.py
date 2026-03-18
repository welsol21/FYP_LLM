"""Append unmatched book-note sentences to the projected natural corpus.

If a templated book note did not land on the natural corpus after projection
guards, we keep it by adding the original book sentence as a new parsed record.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ela_pipeline.dataset.project_template_notes_onto_corpus import (
    _build_sentence_profiles,
    _iter_jsonl,
    _note_payload,
    _sort_candidates,
    _write_json,
    _write_jsonl,
)
from ela_pipeline.parse.spacy_parser import load_nlp


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _projected_source_record_ids(projected_corpus_path: str) -> set[str]:
    source_ids: set[str] = set()
    for row in _iter_jsonl(projected_corpus_path):
        for candidate in row.get("sentence_note_candidates") or []:
            if candidate.get("source_record_id"):
                source_ids.add(str(candidate["source_record_id"]))
        for phrase in row.get("phrase_entries") or []:
            for candidate in phrase.get("note_candidates") or []:
                if candidate.get("source_record_id"):
                    source_ids.add(str(candidate["source_record_id"]))
    return source_ids


def _match_phrase_index(
    phrase_entries: list[dict[str, Any]],
    *,
    target_content: str,
    target_pos: str,
    target_role: str,
) -> int | None:
    exact = [
        idx
        for idx, phrase in enumerate(phrase_entries)
        if _norm(phrase.get("content")) == target_content
        and _norm(phrase.get("part_of_speech")).lower() == target_pos
        and _norm(phrase.get("grammatical_role")).lower() == target_role
    ]
    if exact:
        return exact[0]
    loose = [
        idx
        for idx, phrase in enumerate(phrase_entries)
        if _norm(phrase.get("content")) == target_content
        and _norm(phrase.get("part_of_speech")).lower() == target_pos
    ]
    if loose:
        return loose[0]
    content_only = [
        idx for idx, phrase in enumerate(phrase_entries) if _norm(phrase.get("content")) == target_content
    ]
    if content_only:
        return content_only[0]
    return None


def build_augmented_corpus(
    *,
    projected_corpus_path: str,
    templated_note_rows_path: str,
    spacy_model: str,
    max_phrase_depth: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_rows = list(_iter_jsonl(projected_corpus_path))
    matched_source_ids = _projected_source_record_ids(projected_corpus_path)
    unmatched_rows = [
        row
        for row in _iter_jsonl(templated_note_rows_path)
        if _norm(((row.get("source") or {}).get("source_record_id"))) not in matched_source_ids
    ]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in unmatched_rows:
        source = row.get("source") or {}
        context = row.get("context") or {}
        key = (
            _norm(source.get("document_id")),
            _norm(context.get("sentence_text") or context.get("content")),
        )
        grouped[key].append(row)

    nlp = load_nlp(spacy_model)
    appended_rows: list[dict[str, Any]] = []
    report_counts: Counter[str] = Counter()

    for (document_id, sentence_text), rows in grouped.items():
        if not sentence_text:
            report_counts["skipped_missing_sentence_text"] += 1
            continue
        profiles = _build_sentence_profiles(sentence_text, nlp, max_phrase_depth=max_phrase_depth)
        if not profiles:
            report_counts["skipped_parse_failed"] += 1
            continue

        profile = profiles[0]
        sentence_candidates: list[dict[str, Any]] = []
        phrase_entries = [copy.deepcopy(entry) for entry in profile["phrase_entries"]]
        for phrase in phrase_entries:
            phrase["note_candidates"] = []

        for row in rows:
            context = row.get("context") or {}
            node_type = _norm(context.get("node_type")).lower()
            candidate = _note_payload(row, match_level="book_fallback")
            if node_type == "sentence":
                sentence_candidates.append(candidate)
                report_counts["appended_sentence_note_rows"] += 1
                continue
            if node_type == "phrase":
                phrase_index = _match_phrase_index(
                    phrase_entries,
                    target_content=_norm(context.get("content")),
                    target_pos=_norm(context.get("part_of_speech")).lower(),
                    target_role=_norm(context.get("grammatical_role")).lower(),
                )
                if phrase_index is None:
                    report_counts["unmatched_phrase_targets_inside_book_sentence"] += 1
                    continue
                phrase_entries[phrase_index]["note_candidates"].append(candidate)
                report_counts["appended_phrase_note_rows"] += 1

        sentence_candidates = _sort_candidates(sentence_candidates)
        for phrase in phrase_entries:
            phrase["note_candidates"] = _sort_candidates(phrase.get("note_candidates") or [])

        appended_rows.append(
            {
                "projection_version": "book_note_corpus_projection_v6",
                "source_document": {
                    "id": "",
                    "source_name": f"book_fallback:{document_id}",
                    "source_url": "",
                },
                "sentence_index_in_source": 0,
                "sentence_text": profile["sentence_text"],
                "source_span": profile["source_span"],
                "sentence_family_alignment": {
                    "exact_family_id": profile["sentence_exact_family_id"],
                    "bucketed_family_id": profile["sentence_bucketed_family_id"],
                    "presence_family_id": profile["sentence_presence_family_id"],
                },
                "sentence_note_candidates": sentence_candidates,
                "phrase_entries": phrase_entries,
                "augmentation_meta": {
                    "augmentation_type": "book_sentence_fallback",
                    "source_document_id": document_id,
                    "book_note_rows_count": len(rows),
                },
            }
        )

    merged_rows = base_rows + appended_rows
    report = {
        "projection_version": "book_note_corpus_projection_v6",
        "base_projected_corpus_path": str(Path(projected_corpus_path).resolve()),
        "templated_note_rows_path": str(Path(templated_note_rows_path).resolve()),
        "matched_source_record_ids_total": len(matched_source_ids),
        "unmatched_book_note_rows_total": len(unmatched_rows),
        "book_fallback_sentence_rows_added": len(appended_rows),
        "appended_sentence_note_rows": report_counts["appended_sentence_note_rows"],
        "appended_phrase_note_rows": report_counts["appended_phrase_note_rows"],
        "unmatched_phrase_targets_inside_book_sentence": report_counts["unmatched_phrase_targets_inside_book_sentence"],
        "merged_rows_total": len(merged_rows),
    }
    return merged_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Augment the projected natural corpus with unmatched book sentences.")
    parser.add_argument("--projected-corpus-input", required=True)
    parser.add_argument("--templated-notes-input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--max-phrase-depth", type=int, default=2)
    args = parser.parse_args()

    rows, report = build_augmented_corpus(
        projected_corpus_path=args.projected_corpus_input,
        templated_note_rows_path=args.templated_notes_input,
        spacy_model=args.spacy_model,
        max_phrase_depth=args.max_phrase_depth,
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
