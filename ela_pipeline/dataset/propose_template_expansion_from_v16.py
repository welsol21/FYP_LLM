"""Propose template-registry expansion from enriched v16 projected corpus.

This script does not modify the active registry. It audits sentence/phrase note
topics in the projected corpus, groups them into proposed template families, and
emits a compact JSON report with counts and examples. The goal is to guide the
next iteration of the deterministic template registry and a classifier-first
pipeline.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from ela_pipeline.dataset.template_topic_mapping import normalize_note_topic, topic_to_template_id


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _note_text(candidate: Dict[str, Any]) -> str:
    return str(candidate.get("slot_rendered_note") or candidate.get("note_text") or "").strip()


def _collect_examples(
    bucket: dict[str, list[dict[str, Any]]],
    key: str,
    *,
    limit: int,
    sentence_text: str,
    note_text: str,
    source_book: str,
    topic: str,
    level: str,
) -> None:
    items = bucket.setdefault(key, [])
    if len(items) >= limit:
        return
    items.append(
        {
            "level": level,
            "topic": topic,
            "source_book": source_book,
            "sentence_text": sentence_text,
            "note_text": note_text,
        }
    )


def build_report(input_path: Path) -> Dict[str, Any]:
    sentence_topic_counts: Counter[str] = Counter()
    phrase_topic_counts: Counter[str] = Counter()
    sentence_template_counts: Counter[str] = Counter()
    phrase_template_counts: Counter[str] = Counter()
    sentence_examples: dict[str, list[dict[str, Any]]] = {}
    phrase_examples: dict[str, list[dict[str, Any]]] = {}
    unresolved_sentence_topics: Counter[str] = Counter()
    unresolved_phrase_topics: Counter[str] = Counter()

    for row in _iter_jsonl(input_path):
        sentence_text = str(row.get("sentence_text") or "").strip()

        for cand in row.get("sentence_note_candidates") or []:
            topic = normalize_note_topic(cand.get("topic") or "")
            if not topic:
                continue
            note_text = _note_text(cand)
            source_book = str(cand.get("source_book") or "").strip()
            sentence_topic_counts[topic] += 1
            template_id = topic_to_template_id("Sentence", topic)
            if template_id:
                sentence_template_counts[template_id] += 1
                _collect_examples(
                    sentence_examples,
                    template_id,
                    limit=3,
                    sentence_text=sentence_text,
                    note_text=note_text,
                    source_book=source_book,
                    topic=topic,
                    level="Sentence",
                )
            else:
                unresolved_sentence_topics[topic] += 1

        for phrase in row.get("phrase_entries") or []:
            for cand in phrase.get("note_candidates") or []:
                topic = normalize_note_topic(cand.get("topic") or "")
                if not topic:
                    continue
                note_text = _note_text(cand)
                source_book = str(cand.get("source_book") or "").strip()
                phrase_topic_counts[topic] += 1
                template_id = topic_to_template_id("Phrase", topic)
                if template_id:
                    phrase_template_counts[template_id] += 1
                    _collect_examples(
                        phrase_examples,
                        template_id,
                        limit=3,
                        sentence_text=sentence_text,
                        note_text=note_text,
                        source_book=source_book,
                        topic=topic,
                        level="Phrase",
                    )
                else:
                    unresolved_phrase_topics[topic] += 1

    return {
        "input_path": str(input_path),
        "summary": {
            "mapped_sentence_topics": len(sentence_template_counts),
            "mapped_phrase_topics": len(phrase_template_counts),
            "distinct_sentence_topics": len(sentence_topic_counts),
            "distinct_phrase_topics": len(phrase_topic_counts),
        },
        "sentence": {
            "proposed_templates": [
                {
                    "template_id": template_id,
                    "count": count,
                    "examples": sentence_examples.get(template_id, []),
                }
                for template_id, count in sentence_template_counts.most_common()
            ],
            "top_topics": sentence_topic_counts.most_common(80),
            "unresolved_topics": unresolved_sentence_topics.most_common(40),
        },
        "phrase": {
            "proposed_templates": [
                {
                    "template_id": template_id,
                    "count": count,
                    "examples": phrase_examples.get(template_id, []),
                }
                for template_id, count in phrase_template_counts.most_common()
            ],
            "top_topics": phrase_topic_counts.most_common(80),
            "unresolved_topics": unresolved_phrase_topics.most_common(40),
        },
        "recommendation": {
            "preferred_model_family_for_template_prediction": "deberta-v3-small or deberta-v3-base sequence classifier",
            "task_formulation": "predict template_id from compact structural prompt, then render note deterministically",
            "why_not_t5_first": [
                "current free-form target space is too heterogeneous for the dataset size",
                "template classification is lower-entropy and easier to validate",
                "BERT/DeBERTa classifiers are usually more data-efficient for closed-label tasks",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/processed_corpus_book_projection_v16/ingested_corpus_book_projection_v16.covered_only.jsonl",
    )
    parser.add_argument(
        "--output",
        default="data/reports/template_expansion_proposal_v16.json",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = build_report(input_path)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    main()
