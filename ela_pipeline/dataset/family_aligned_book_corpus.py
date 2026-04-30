"""Build a versioned notes-only family-aligned book corpus against the natural 3k sentence corpus."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ela_pipeline.dataset.contract_signatures import (
    contract_bucketed_signature,
    contract_exact_signature,
    contract_presence_signature,
)
from ela_pipeline.dataset.tree_construction_inventory import (
    _compress_phrase_signature_bucketed,
    _compress_phrase_signature_presence,
    _compress_sentence_signature_bucketed,
    _compress_sentence_signature_presence,
    _iter_phrase_signatures,
    _iter_phrase_children,
    _normalize_phrase_children,
    _phrase_signature,
    _sentence_signature,
)
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _family_id(prefix: str, signature: Any) -> str:
    digest = hashlib.sha1(repr(signature).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _is_note_row(row: dict[str, Any]) -> bool:
    target = row.get("target") or {}
    note_text = _norm_text(target.get("note_text") or row.get("model_target"))
    return bool(note_text)


def _load_book_rows(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for row in _iter_jsonl(path):
            if _is_note_row(row):
                rows.append(row)
    return rows


def _prepare_sentence_profiles(text: str, nlp: Any, *, max_phrase_depth: int) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for sentence_text, sentence_node in build_skeleton(text, nlp).items():
        exact_contract_signature = contract_exact_signature(sentence_node)
        bucketed_contract_signature = contract_bucketed_signature(exact_contract_signature)
        presence_contract_signature = contract_presence_signature(exact_contract_signature)
        effective_children = _normalize_phrase_children(
            sentence_node,
            depth=1,
            max_depth=max_phrase_depth,
            stats=Counter(),
        )
        exact_sentence_signature = _sentence_signature(effective_children)
        bucketed_sentence_signature = _compress_sentence_signature_bucketed(exact_sentence_signature)
        presence_sentence_signature = _compress_sentence_signature_presence(exact_sentence_signature)

        phrase_profiles: list[dict[str, Any]] = []

        def walk(children: list[dict[str, Any]]) -> None:
            for child in children:
                exact_phrase_signature = _phrase_signature(child)
                phrase_profiles.append(
                    {
                        "content": _norm_text(child.get("content")),
                        "part_of_speech": _norm_text(child.get("part_of_speech")).lower(),
                        "grammatical_role": _norm_text(child.get("grammatical_role")).lower(),
                        "exact_signature": exact_phrase_signature,
                        "bucketed_signature": _compress_phrase_signature_bucketed(exact_phrase_signature),
                        "presence_signature": _compress_phrase_signature_presence(exact_phrase_signature),
                    }
                )
                walk(child.get("children") or [])

        walk(effective_children)
        profiles.append(
            {
                "sentence_text": sentence_text,
                "sentence_node": sentence_node,
                "exact_signature": exact_sentence_signature,
                "bucketed_signature": bucketed_sentence_signature,
                "presence_signature": presence_sentence_signature,
                "contract_exact_signature": exact_contract_signature,
                "contract_bucketed_signature": bucketed_contract_signature,
                "contract_presence_signature": presence_contract_signature,
                "phrase_profiles": phrase_profiles,
            }
        )
    return profiles


def _build_corpus_registry(
    *,
    corpus_input_path: str,
    spacy_model: str,
    max_phrase_depth: int,
) -> dict[str, Any]:
    nlp = load_nlp(spacy_model)
    sentence_exact_counts: Counter[str] = Counter()
    sentence_bucketed_counts: Counter[str] = Counter()
    sentence_presence_counts: Counter[str] = Counter()
    sentence_contract_exact_counts: Counter[str] = Counter()
    sentence_contract_bucketed_counts: Counter[str] = Counter()
    sentence_contract_presence_counts: Counter[str] = Counter()
    phrase_exact_counts: Counter[str] = Counter()
    phrase_bucketed_counts: Counter[str] = Counter()
    phrase_presence_counts: Counter[str] = Counter()

    sentence_examples: dict[str, list[str]] = defaultdict(list)
    phrase_examples: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in _iter_jsonl(corpus_input_path):
        text = _norm_text(row.get("text"))
        if not text:
            continue
        for profile in _prepare_sentence_profiles(text, nlp, max_phrase_depth=max_phrase_depth):
            sentence_exact_id = _family_id("sent_exact", profile["exact_signature"])
            sentence_bucketed_id = _family_id("sent_bucket", profile["bucketed_signature"])
            sentence_presence_id = _family_id("sent_presence", profile["presence_signature"])
            sentence_contract_exact_id = _family_id("sent_contract_exact", profile["contract_exact_signature"])
            sentence_contract_bucketed_id = _family_id("sent_contract_bucket", profile["contract_bucketed_signature"])
            sentence_contract_presence_id = _family_id("sent_contract_presence", profile["contract_presence_signature"])
            sentence_exact_counts[sentence_exact_id] += 1
            sentence_bucketed_counts[sentence_bucketed_id] += 1
            sentence_presence_counts[sentence_presence_id] += 1
            sentence_contract_exact_counts[sentence_contract_exact_id] += 1
            sentence_contract_bucketed_counts[sentence_contract_bucketed_id] += 1
            sentence_contract_presence_counts[sentence_contract_presence_id] += 1
            if len(sentence_examples[sentence_exact_id]) < 3:
                sentence_examples[sentence_exact_id].append(profile["sentence_text"])

            for phrase_profile in profile["phrase_profiles"]:
                phrase_exact_id = _family_id("phrase_exact", phrase_profile["exact_signature"])
                phrase_bucketed_id = _family_id("phrase_bucket", phrase_profile["bucketed_signature"])
                phrase_presence_id = _family_id("phrase_presence", phrase_profile["presence_signature"])
                phrase_exact_counts[phrase_exact_id] += 1
                phrase_bucketed_counts[phrase_bucketed_id] += 1
                phrase_presence_counts[phrase_presence_id] += 1
                if len(phrase_examples[phrase_exact_id]) < 3:
                    phrase_examples[phrase_exact_id].append(
                        {
                            "sentence_text": profile["sentence_text"],
                            "phrase_text": phrase_profile["content"],
                            "part_of_speech": phrase_profile["part_of_speech"],
                            "grammatical_role": phrase_profile["grammatical_role"],
                        }
                    )

    return {
        "registry_version": "book_family_alignment_v2",
        "corpus_input_path": str(Path(corpus_input_path).resolve()),
        "spacy_model": spacy_model,
        "max_phrase_depth": int(max_phrase_depth),
        "sentence_exact_counts": dict(sentence_exact_counts),
        "sentence_bucketed_counts": dict(sentence_bucketed_counts),
        "sentence_presence_counts": dict(sentence_presence_counts),
        "sentence_contract_exact_counts": dict(sentence_contract_exact_counts),
        "sentence_contract_bucketed_counts": dict(sentence_contract_bucketed_counts),
        "sentence_contract_presence_counts": dict(sentence_contract_presence_counts),
        "phrase_exact_counts": dict(phrase_exact_counts),
        "phrase_bucketed_counts": dict(phrase_bucketed_counts),
        "phrase_presence_counts": dict(phrase_presence_counts),
        "sentence_examples": dict(sentence_examples),
        "phrase_examples": dict(phrase_examples),
    }


def _select_profile_for_row(row: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    sentence_text = _norm_text(row.get("context", {}).get("sentence_text") or row.get("context", {}).get("content"))
    if not sentence_text:
        return profiles[0] if profiles else None
    for profile in profiles:
        if _norm_text(profile["sentence_text"]) == sentence_text:
            return profile
    return profiles[0] if profiles else None


def _match_phrase_profile(row: dict[str, Any], phrase_profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    context = row.get("context") or {}
    target_content = _norm_text(context.get("content"))
    target_pos = _norm_text(context.get("part_of_speech")).lower()
    target_role = _norm_text(context.get("grammatical_role")).lower()

    exact_matches = [
        profile
        for profile in phrase_profiles
        if profile["content"] == target_content
        and profile["part_of_speech"] == target_pos
        and profile["grammatical_role"] == target_role
    ]
    if exact_matches:
        return exact_matches[0]

    loose_matches = [
        profile
        for profile in phrase_profiles
        if profile["content"] == target_content and profile["part_of_speech"] == target_pos
    ]
    if loose_matches:
        return loose_matches[0]

    content_matches = [profile for profile in phrase_profiles if profile["content"] == target_content]
    if content_matches:
        return content_matches[0]

    return None


def _align_book_rows(
    *,
    book_rows: list[dict[str, Any]],
    registry: dict[str, Any],
    spacy_model: str,
    max_phrase_depth: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    aligned_rows: list[dict[str, Any]] = []
    coverage_sentence_exact: set[str] = set()
    coverage_sentence_bucketed: set[str] = set()
    coverage_sentence_presence: set[str] = set()
    coverage_phrase_exact: set[str] = set()
    coverage_phrase_bucketed: set[str] = set()
    coverage_phrase_presence: set[str] = set()
    alignment_stats: Counter[str] = Counter()

    for row in book_rows:
        working = copy.deepcopy(row)
        context = working.get("context") or {}
        node_type = _norm_text(context.get("node_type"))
        sentence_text = _norm_text(context.get("sentence_text") or context.get("content"))
        if not sentence_text:
            alignment_stats["skipped_missing_sentence_text"] += 1
            continue

        profiles = _prepare_sentence_profiles(sentence_text, nlp, max_phrase_depth=max_phrase_depth)
        profile = _select_profile_for_row(working, profiles)
        if profile is None:
            alignment_stats["skipped_parse_failed"] += 1
            continue

        sentence_exact_id = _family_id("sent_exact", profile["exact_signature"])
        sentence_bucketed_id = _family_id("sent_bucket", profile["bucketed_signature"])
        sentence_presence_id = _family_id("sent_presence", profile["presence_signature"])
        sentence_contract_exact_id = _family_id("sent_contract_exact", profile["contract_exact_signature"])
        sentence_contract_bucketed_id = _family_id("sent_contract_bucket", profile["contract_bucketed_signature"])
        sentence_contract_presence_id = _family_id("sent_contract_presence", profile["contract_presence_signature"])

        family_alignment = {
            "registry_version": registry["registry_version"],
            "max_phrase_depth": int(max_phrase_depth),
            "sentence": {
                "exact_family_id": sentence_exact_id,
                "bucketed_family_id": sentence_bucketed_id,
                "presence_family_id": sentence_presence_id,
                "contract_exact_family_id": sentence_contract_exact_id,
                "contract_bucketed_family_id": sentence_contract_bucketed_id,
                "contract_presence_family_id": sentence_contract_presence_id,
                "corpus_exact_count": int(registry["sentence_exact_counts"].get(sentence_exact_id, 0)),
                "corpus_bucketed_count": int(registry["sentence_bucketed_counts"].get(sentence_bucketed_id, 0)),
                "corpus_presence_count": int(registry["sentence_presence_counts"].get(sentence_presence_id, 0)),
                "corpus_contract_exact_count": int(registry["sentence_contract_exact_counts"].get(sentence_contract_exact_id, 0)),
                "corpus_contract_bucketed_count": int(registry["sentence_contract_bucketed_counts"].get(sentence_contract_bucketed_id, 0)),
                "corpus_contract_presence_count": int(registry["sentence_contract_presence_counts"].get(sentence_contract_presence_id, 0)),
            },
        }

        coverage_sentence_exact.add(sentence_exact_id)
        coverage_sentence_bucketed.add(sentence_bucketed_id)
        coverage_sentence_presence.add(sentence_presence_id)

        if node_type.lower() == "phrase":
            phrase_profile = _match_phrase_profile(working, profile["phrase_profiles"])
            if phrase_profile is None:
                alignment_stats["phrase_target_not_found"] += 1
                family_alignment["phrase"] = None
            else:
                phrase_exact_id = _family_id("phrase_exact", phrase_profile["exact_signature"])
                phrase_bucketed_id = _family_id("phrase_bucket", phrase_profile["bucketed_signature"])
                phrase_presence_id = _family_id("phrase_presence", phrase_profile["presence_signature"])
                family_alignment["phrase"] = {
                    "exact_family_id": phrase_exact_id,
                    "bucketed_family_id": phrase_bucketed_id,
                    "presence_family_id": phrase_presence_id,
                    "corpus_exact_count": int(registry["phrase_exact_counts"].get(phrase_exact_id, 0)),
                    "corpus_bucketed_count": int(registry["phrase_bucketed_counts"].get(phrase_bucketed_id, 0)),
                    "corpus_presence_count": int(registry["phrase_presence_counts"].get(phrase_presence_id, 0)),
                    "matched_phrase_text": phrase_profile["content"],
                }
                coverage_phrase_exact.add(phrase_exact_id)
                coverage_phrase_bucketed.add(phrase_bucketed_id)
                coverage_phrase_presence.add(phrase_presence_id)
                alignment_stats["phrase_aligned"] += 1
        else:
            alignment_stats["sentence_aligned"] += 1

        working["family_alignment"] = family_alignment
        working["corpus_projection_version"] = "notes_only_family_alignment_v2"
        aligned_rows.append(working)

    coverage = {
        "registry_version": registry["registry_version"],
        "book_note_rows_total": len(book_rows),
        "aligned_note_rows_total": len(aligned_rows),
        "alignment_stats": dict(alignment_stats),
        "sentence_coverage": {
            "exact_families_covered": len(coverage_sentence_exact),
            "bucketed_families_covered": len(coverage_sentence_bucketed),
            "presence_families_covered": len(coverage_sentence_presence),
            "corpus_exact_families_total": len(registry["sentence_exact_counts"]),
            "corpus_bucketed_families_total": len(registry["sentence_bucketed_counts"]),
            "corpus_presence_families_total": len(registry["sentence_presence_counts"]),
        },
        "phrase_coverage": {
            "exact_families_covered": len(coverage_phrase_exact),
            "bucketed_families_covered": len(coverage_phrase_bucketed),
            "presence_families_covered": len(coverage_phrase_presence),
            "corpus_exact_families_total": len(registry["phrase_exact_counts"]),
            "corpus_bucketed_families_total": len(registry["phrase_bucketed_counts"]),
            "corpus_presence_families_total": len(registry["phrase_presence_counts"]),
        },
    }
    return aligned_rows, coverage


def _write_json(path: str, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a versioned notes-only family-aligned book corpus.")
    parser.add_argument(
        "--book-inputs",
        nargs="+",
        required=True,
        help="Processed book training-row JSONL files with target.note_text/model_target.",
    )
    parser.add_argument(
        "--corpus-input",
        default="/home/vlad/Dev/FYP_LLM/data/raw_sources/ingested_sentences.jsonl",
        help="Natural sentence corpus JSONL used as the family registry base.",
    )
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--max-phrase-depth", type=int, default=2)
    parser.add_argument(
        "--output-dir",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_family_v2",
        help="Directory for versioned output artifacts.",
    )
    args = parser.parse_args()

    registry = _build_corpus_registry(
        corpus_input_path=args.corpus_input,
        spacy_model=args.spacy_model,
        max_phrase_depth=args.max_phrase_depth,
    )
    book_rows = _load_book_rows(args.book_inputs)
    aligned_rows, coverage = _align_book_rows(
        book_rows=book_rows,
        registry=registry,
        spacy_model=args.spacy_model,
        max_phrase_depth=args.max_phrase_depth,
    )

    output_dir = Path(args.output_dir)
    _write_json(str(output_dir / "corpus_family_registry_v2.json"), registry)
    _write_jsonl(str(output_dir / "book_note_rows_family_aligned_v2.jsonl"), aligned_rows)
    _write_json(str(output_dir / "book_note_family_coverage_v2.json"), coverage)

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(output_dir.resolve()),
                "registry_sentence_families": len(registry["sentence_bucketed_counts"]),
                "registry_phrase_families": len(registry["phrase_bucketed_counts"]),
                "aligned_rows": len(aligned_rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
