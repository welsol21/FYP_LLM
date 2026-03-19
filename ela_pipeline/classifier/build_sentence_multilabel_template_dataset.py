"""Build sentence-level multi-label template dataset from projected corpus rows."""

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

from ela_pipeline.annotate.note_context import build_note_context_prompt
from ela_pipeline.dataset.build_dataset import PROMPT_TEMPLATE_VERSION, write_jsonl
from ela_pipeline.dataset.build_t5_dataset_from_projected_corpus import (
    BOOK_WHITELIST,
    _build_sentence_stub,
    _document_id,
    _phrase_candidate_ok,
    _sentence_candidate_ok,
)
from ela_pipeline.dataset.template_topic_mapping import topic_to_template_id


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _sentence_templates(item: Dict[str, Any]) -> List[str]:
    sentence_text = str(item.get("sentence_text") or "")
    out: set[str] = set()
    for candidate in item.get("sentence_note_candidates") or []:
        source_book = str(candidate.get("source_book") or "")
        if source_book not in BOOK_WHITELIST:
            continue
        if not _sentence_candidate_ok(candidate, sentence_text):
            continue
        template_id = topic_to_template_id("Sentence", candidate.get("topic") or "")
        if template_id:
            out.add(template_id)
    return sorted(out)


def _phrase_templates(item: Dict[str, Any]) -> List[str]:
    sentence_text = str(item.get("sentence_text") or "")
    out: set[str] = set()
    for phrase_entry in item.get("phrase_entries") or []:
        phrase_text = str(phrase_entry.get("content") or "")
        for candidate in phrase_entry.get("note_candidates") or []:
            source_book = str(candidate.get("source_book") or "")
            if source_book not in BOOK_WHITELIST:
                continue
            if not _phrase_candidate_ok(candidate, phrase_text, sentence_text):
                continue
            template_id = topic_to_template_id("Phrase", candidate.get("topic") or "")
            if template_id:
                out.add(template_id)
    return sorted(out)


def _make_row(item: Dict[str, Any]) -> Dict[str, Any] | None:
    sentence_stub = _build_sentence_stub(item)
    prompt = build_note_context_prompt(
        node=sentence_stub,
        parent=None,
        sentence_node=sentence_stub,
        path_types=["Sentence"],
        depth=0,
        sibling_index=0,
        sibling_count=1,
        template_version=PROMPT_TEMPLATE_VERSION,
    )
    sentence_templates = _sentence_templates(item)
    phrase_templates = _phrase_templates(item)
    template_ids = sorted(set(sentence_templates) | set(phrase_templates))
    if not template_ids:
        return None
    source_document = item.get("source_document") or {}
    return {
        "input": prompt,
        "level": "Sentence",
        "sentence_text": item.get("sentence_text"),
        "template_ids": template_ids,
        "sentence_template_ids": sentence_templates,
        "phrase_template_ids": phrase_templates,
        "label_count": len(template_ids),
        "sentence_label_count": len(sentence_templates),
        "phrase_label_count": len(phrase_templates),
        "split_group_id": _document_id(item),
        "source_document_id": source_document.get("id"),
        "source_name": source_document.get("source_name"),
        "projection_version": item.get("projection_version"),
        "sentence_exact_family_id": ((item.get("sentence_family_alignment") or {}).get("exact_family_id")),
        "sentence_bucketed_family_id": ((item.get("sentence_family_alignment") or {}).get("bucketed_family_id")),
        "sentence_presence_family_id": ((item.get("sentence_family_alignment") or {}).get("presence_family_id")),
    }


def _build_rows(projected_path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in _iter_jsonl(projected_path):
        row = _make_row(item)
        if row:
            out.append(row)
    return out


def _dedup_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, Tuple[str, ...]]] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("input") or ""),
            tuple(str(x) for x in row.get("template_ids") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _filter_by_template_support(
    rows: List[Dict[str, Any]],
    *,
    min_template_support: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    if min_template_support <= 1:
        return rows, {"min_template_support": min_template_support, "rows_dropped": 0, "labels_dropped": 0}

    template_counts: Counter[str] = Counter()
    for row in rows:
        template_counts.update(str(x) for x in row.get("template_ids") or [])

    kept: List[Dict[str, Any]] = []
    rows_dropped = 0
    labels_dropped = 0
    for row in rows:
        filtered = [tid for tid in row.get("template_ids") or [] if template_counts[str(tid)] >= min_template_support]
        labels_dropped += len(row.get("template_ids") or []) - len(filtered)
        if not filtered:
            rows_dropped += 1
            continue
        new_row = dict(row)
        sentence_filtered = [tid for tid in row.get("sentence_template_ids") or [] if template_counts[str(tid)] >= min_template_support]
        phrase_filtered = [tid for tid in row.get("phrase_template_ids") or [] if template_counts[str(tid)] >= min_template_support]
        new_row["template_ids"] = filtered
        new_row["sentence_template_ids"] = sentence_filtered
        new_row["phrase_template_ids"] = phrase_filtered
        new_row["label_count"] = len(filtered)
        new_row["sentence_label_count"] = len(sentence_filtered)
        new_row["phrase_label_count"] = len(phrase_filtered)
        kept.append(new_row)
    return kept, {
        "min_template_support": min_template_support,
        "rows_dropped": rows_dropped,
        "labels_dropped": labels_dropped,
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


def _label_distribution(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(str(x) for x in row.get(key) or [])
    return dict(sorted(counter.items()))


def _count_distribution(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    return dict(sorted(Counter(int(row.get(key) or 0) for row in rows).items()))


def build_sentence_multilabel_template_dataset(
    *,
    input_path: str,
    output_dir: str,
    seed: int = 42,
    dev_ratio: float = 0.1,
    test_ratio: float = 0.1,
    min_template_support: int = 1,
) -> Dict[str, Any]:
    projected_path = Path(input_path)
    rows = _build_rows(projected_path)
    deduped = _dedup_rows(rows)
    filtered, filter_report = _filter_by_template_support(
        deduped,
        min_template_support=min_template_support,
    )
    train, dev, test = _split_by_group(
        filtered,
        seed=seed,
        dev_ratio=dev_ratio,
        test_ratio=test_ratio,
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(filtered, str(out_dir / "all.jsonl"))
    write_jsonl(train, str(out_dir / "train.jsonl"))
    write_jsonl(dev, str(out_dir / "dev.jsonl"))
    write_jsonl(test, str(out_dir / "test.jsonl"))

    all_template_ids = sorted({tid for row in filtered for tid in row.get("template_ids") or []})
    sentence_template_ids = sorted({tid for row in filtered for tid in row.get("sentence_template_ids") or []})
    phrase_template_ids = sorted({tid for row in filtered for tid in row.get("phrase_template_ids") or []})

    stats = {
        "task": "sentence_multilabel_template_classification",
        "builder": "build_sentence_multilabel_template_dataset.py",
        "input_path": str(projected_path.resolve()),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "total_before_dedup": len(rows),
        "total_after_dedup": len(deduped),
        "total_after_filter": len(filtered),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "min_template_support": min_template_support,
        "filter_report": filter_report,
        "template_space_size": len(all_template_ids),
        "sentence_template_space_size": len(sentence_template_ids),
        "phrase_template_space_size": len(phrase_template_ids),
        "avg_label_count": (sum(int(row.get("label_count") or 0) for row in filtered) / len(filtered)) if filtered else 0.0,
        "avg_sentence_label_count": (sum(int(row.get("sentence_label_count") or 0) for row in filtered) / len(filtered)) if filtered else 0.0,
        "avg_phrase_label_count": (sum(int(row.get("phrase_label_count") or 0) for row in filtered) / len(filtered)) if filtered else 0.0,
        "distributions": {
            "label_count": _count_distribution(filtered, "label_count"),
            "sentence_label_count": _count_distribution(filtered, "sentence_label_count"),
            "phrase_label_count": _count_distribution(filtered, "phrase_label_count"),
            "template_ids": _label_distribution(filtered, "template_ids"),
            "sentence_template_ids": _label_distribution(filtered, "sentence_template_ids"),
            "phrase_template_ids": _label_distribution(filtered, "phrase_template_ids"),
            "source_name": dict(sorted(Counter(str(row.get("source_name") or "") for row in filtered).items())),
        },
    }
    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sentence-level multi-label template dataset.")
    parser.add_argument(
        "--input-path",
        default="data/processed_corpus_book_projection_v16/ingested_corpus_book_projection_v16.covered_only.jsonl",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--min-template-support", type=int, default=1)
    args = parser.parse_args()

    stats = build_sentence_multilabel_template_dataset(
        input_path=args.input_path,
        output_dir=args.output_dir,
        seed=int(args.seed),
        dev_ratio=float(args.dev_ratio),
        test_ratio=float(args.test_ratio),
        min_template_support=int(args.min_template_support),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
