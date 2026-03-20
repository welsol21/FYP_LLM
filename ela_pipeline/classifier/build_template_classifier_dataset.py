"""Build template_id classifier datasets from projected corpus rows."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from ela_pipeline.annotate.contract_template_builder import (
    CONTRACT_CLASSIFIER_PROMPT_TEMPLATE_VERSION,
    build_contract_template_classifier_prompt,
    build_contract_template_payload,
)
from ela_pipeline.annotate.template_registry import render_template_note
from ela_pipeline.dataset.build_dataset import write_jsonl
from ela_pipeline.dataset.build_t5_dataset_from_projected_corpus import (
    BOOK_PRIORITY,
    BOOK_WHITELIST,
    _build_sentence_stub,
    _document_id,
    _phrase_context,
    _phrase_candidate_ok,
    _quoted_fragments,
    _sentence_candidate_ok,
)
from ela_pipeline.dataset.template_topic_mapping import topic_to_template_id


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _candidate_note_text(candidate: Dict[str, Any]) -> str:
    return str(candidate.get("slot_rendered_note") or candidate.get("note_text") or "").strip()


def _mapped_candidate_priority(candidate: Dict[str, Any]) -> Tuple[int, int, int]:
    source_book = str(candidate.get("source_book") or "")
    note_text = _candidate_note_text(candidate)
    return (
        BOOK_PRIORITY.get(source_book, 0),
        1 if candidate.get("slot_templated") else 0,
        len(_quoted_fragments(note_text)),
    )


def _mapped_sentence_candidate(
    candidates: List[Dict[str, Any]],
    *,
    sentence_text: str,
) -> Tuple[Dict[str, Any] | None, str]:
    accepted: List[Tuple[Dict[str, Any], str]] = []
    for candidate in candidates:
        source_book = str(candidate.get("source_book") or "")
        if source_book not in BOOK_WHITELIST:
            continue
        template_id = topic_to_template_id("Sentence", candidate.get("topic") or "")
        if not template_id:
            continue
        if not _sentence_candidate_ok(candidate, sentence_text):
            continue
        accepted.append((candidate, template_id))
    if not accepted:
        return None, ""
    accepted.sort(key=lambda pair: _mapped_candidate_priority(pair[0]), reverse=True)
    return accepted[0]


def _mapped_phrase_candidate(
    candidates: List[Dict[str, Any]],
    *,
    sentence_text: str,
    phrase_text: str,
) -> Tuple[Dict[str, Any] | None, str]:
    accepted: List[Tuple[Dict[str, Any], str]] = []
    for candidate in candidates:
        source_book = str(candidate.get("source_book") or "")
        if source_book not in BOOK_WHITELIST:
            continue
        template_id = topic_to_template_id("Phrase", candidate.get("topic") or "")
        if not template_id:
            continue
        if not _phrase_candidate_ok(candidate, phrase_text, sentence_text):
            continue
        accepted.append((candidate, template_id))
    if not accepted:
        return None, ""
    accepted.sort(key=lambda pair: _mapped_candidate_priority(pair[0]), reverse=True)
    return accepted[0]


def _make_sentence_row(row: Dict[str, Any], candidate: Dict[str, Any], template_id: str) -> Dict[str, Any]:
    sentence_stub = _build_sentence_stub(row)
    payload = build_contract_template_payload(
        node=sentence_stub,
        sentence_node=sentence_stub,
        parent=None,
        path_types=["Sentence"],
        depth=0,
        sibling_index=0,
        sibling_count=1,
    )
    prompt = build_contract_template_classifier_prompt(payload or {}, node_level="Sentence")
    source_document = row.get("source_document") or {}
    return {
        "input": prompt,
        "prompt_template_version": CONTRACT_CLASSIFIER_PROMPT_TEMPLATE_VERSION,
        "template_id": template_id,
        "level": "Sentence",
        "sentence_text": row.get("sentence_text"),
        "target_content": row.get("sentence_text"),
        "template_preview": render_template_note(template_id, sentence_stub, "classifier_dataset"),
        "note_source_book": candidate.get("source_book"),
        "note_topic": candidate.get("topic"),
        "split_group_id": _document_id(row),
        "source_document_id": source_document.get("id"),
        "source_name": source_document.get("source_name"),
        "projection_version": row.get("projection_version"),
        "sentence_exact_family_id": ((row.get("sentence_family_alignment") or {}).get("exact_family_id")),
        "sentence_bucketed_family_id": ((row.get("sentence_family_alignment") or {}).get("bucketed_family_id")),
        "sentence_presence_family_id": ((row.get("sentence_family_alignment") or {}).get("presence_family_id")),
    }


def _make_phrase_row(row: Dict[str, Any], phrase_entry: Dict[str, Any], candidate: Dict[str, Any], template_id: str) -> Dict[str, Any]:
    sentence_stub, phrase_stub, path_types, depth, sibling_index, sibling_count, parent_stub = _phrase_context(
        row,
        phrase_entry,
    )
    payload = build_contract_template_payload(
        node=phrase_stub,
        parent=parent_stub,
        sentence_node=sentence_stub,
        path_types=path_types,
        depth=depth,
        sibling_index=sibling_index,
        sibling_count=sibling_count,
    )
    prompt = build_contract_template_classifier_prompt(payload or {}, node_level="Phrase")
    source_document = row.get("source_document") or {}
    return {
        "input": prompt,
        "prompt_template_version": CONTRACT_CLASSIFIER_PROMPT_TEMPLATE_VERSION,
        "template_id": template_id,
        "level": "Phrase",
        "sentence_text": row.get("sentence_text"),
        "target_content": phrase_entry.get("content"),
        "template_preview": render_template_note(template_id, phrase_stub, "classifier_dataset"),
        "note_source_book": candidate.get("source_book"),
        "note_topic": candidate.get("topic"),
        "split_group_id": _document_id(row),
        "source_document_id": source_document.get("id"),
        "source_name": source_document.get("source_name"),
        "projection_version": row.get("projection_version"),
        "phrase_exact_family_id": phrase_entry.get("exact_family_id"),
        "phrase_bucketed_family_id": phrase_entry.get("bucketed_family_id"),
        "phrase_presence_family_id": phrase_entry.get("presence_family_id"),
    }


def _build_rows(projected_path: Path, *, include_sentence: bool, include_phrase: bool) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in _iter_jsonl(projected_path):
        sentence_text = str(item.get("sentence_text") or "")
        if include_sentence:
            sentence_candidate, template_id = _mapped_sentence_candidate(
                item.get("sentence_note_candidates") or [],
                sentence_text=sentence_text,
            )
            if sentence_candidate and template_id:
                rows.append(_make_sentence_row(item, sentence_candidate, template_id))

        if include_phrase:
            for phrase_entry in item.get("phrase_entries") or []:
                phrase_candidate, template_id = _mapped_phrase_candidate(
                    phrase_entry.get("note_candidates") or [],
                    phrase_text=str(phrase_entry.get("content") or ""),
                    sentence_text=sentence_text,
                )
                if phrase_candidate and template_id:
                    rows.append(_make_phrase_row(item, phrase_entry, phrase_candidate, template_id))
    return rows


def _dedup_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("level") or ""),
            str(row.get("template_id") or ""),
            str(row.get("input") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _cap_rows(
    rows: List[Dict[str, Any]],
    *,
    min_per_template: int,
    max_per_template: int,
    max_per_template_source: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    skipped_min = 0
    if min_per_template > 1:
        counts = Counter(str(row.get("template_id") or "") for row in rows)
        skipped_min = sum(1 for row in rows if counts[str(row.get("template_id") or "")] < min_per_template)
        rows = [row for row in rows if counts[str(row.get("template_id") or "")] >= min_per_template]

    template_counts: Counter[str] = Counter()
    template_source_counts: Counter[Tuple[str, str]] = Counter()
    kept: List[Dict[str, Any]] = []
    skipped_template = 0
    skipped_template_source = 0

    for row in rows:
        template_id = str(row.get("template_id") or "")
        source_book = str(row.get("note_source_book") or "")
        if max_per_template > 0 and template_counts[template_id] >= max_per_template:
            skipped_template += 1
            continue
        if max_per_template_source > 0 and template_source_counts[(template_id, source_book)] >= max_per_template_source:
            skipped_template_source += 1
            continue
        kept.append(row)
        template_counts[template_id] += 1
        template_source_counts[(template_id, source_book)] += 1

    return kept, {
        "min_per_template": min_per_template,
        "skipped_by_min_template_support": skipped_min,
        "skipped_by_template_cap": skipped_template,
        "skipped_by_template_source_cap": skipped_template_source,
    }


def _split_by_group(
    rows: List[Dict[str, Any]],
    *,
    seed: int,
    dev_ratio: float,
    test_ratio: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("split_group_id") or "unknown")].append(row)

    items = list(grouped.items())
    random.Random(seed).shuffle(items)
    total = len(rows)
    target_dev = int(total * dev_ratio)
    target_test = int(total * test_ratio)
    train: List[Dict[str, Any]] = []
    dev: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []

    for _, group_rows in items:
        if len(test) < target_test:
            test.extend(group_rows)
        elif len(dev) < target_dev:
            dev.extend(group_rows)
        else:
            train.extend(group_rows)
    return train, dev, test


def _distribution(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def build_template_classifier_dataset(
    *,
    input_path: str,
    output_dir: str,
    include_sentence: bool = True,
    include_phrase: bool = True,
    seed: int = 42,
    dev_ratio: float = 0.1,
    test_ratio: float = 0.1,
    min_per_template: int = 1,
    max_per_template: int = 180,
    max_per_template_source: int = 90,
) -> Dict[str, Any]:
    projected_path = Path(input_path)
    rows = _build_rows(projected_path, include_sentence=include_sentence, include_phrase=include_phrase)
    deduped = _dedup_rows(rows)
    capped, cap_report = _cap_rows(
        deduped,
        min_per_template=min_per_template,
        max_per_template=max_per_template,
        max_per_template_source=max_per_template_source,
    )
    train, dev, test = _split_by_group(
        capped,
        seed=seed,
        dev_ratio=dev_ratio,
        test_ratio=test_ratio,
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(capped, str(out_dir / "all.jsonl"))
    write_jsonl(train, str(out_dir / "train.jsonl"))
    write_jsonl(dev, str(out_dir / "dev.jsonl"))
    write_jsonl(test, str(out_dir / "test.jsonl"))

    stats = {
        "task": "template_id_classification",
        "builder": "build_template_classifier_dataset.py",
        "input_path": str(projected_path.resolve()),
        "prompt_template_version": CONTRACT_CLASSIFIER_PROMPT_TEMPLATE_VERSION,
        "include_sentence": include_sentence,
        "include_phrase": include_phrase,
        "total_before_dedup": len(rows),
        "total_after_dedup": len(deduped),
        "total_after_cap": len(capped),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "min_per_template": min_per_template,
        "max_per_template": max_per_template,
        "max_per_template_source": max_per_template_source,
        "cap_report": cap_report,
        "distributions": {
            "level": _distribution(capped, "level"),
            "template_id": _distribution(capped, "template_id"),
            "note_source_book": _distribution(capped, "note_source_book"),
        },
    }
    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build template_id classifier dataset from projected corpus.")
    parser.add_argument(
        "--input-path",
        default="data/processed_corpus_book_projection_v16/ingested_corpus_book_projection_v16.covered_only.jsonl",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--min-per-template", type=int, default=1)
    parser.add_argument("--max-per-template", type=int, default=180)
    parser.add_argument("--max-per-template-source", type=int, default=90)
    parser.add_argument("--include-sentence", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-phrase", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    stats = build_template_classifier_dataset(
        input_path=args.input_path,
        output_dir=args.output_dir,
        include_sentence=bool(args.include_sentence),
        include_phrase=bool(args.include_phrase),
        seed=int(args.seed),
        dev_ratio=float(args.dev_ratio),
        test_ratio=float(args.test_ratio),
        min_per_template=int(args.min_per_template),
        max_per_template=int(args.max_per_template),
        max_per_template_source=int(args.max_per_template_source),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
