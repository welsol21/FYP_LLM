"""Build a contract-aware dataset from Oxford Dictionary rulebook pairs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ela_pipeline.annotate.contract_template_builder import build_contract_template_payload
from ela_pipeline.dataset.build_book_explanation_context_corpus import _template_ids_compatible, _walk_with_parent
from ela_pipeline.dataset.template_topic_mapping import topic_to_template_id
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


TERM_TO_TOPIC_KEY = {
    "question tags": "question_tags",
    "question tag": "question_tags",
    "relative clauses": "relative_clauses",
    "relative clause": "relative_clauses",
    "prepositional phrases": "prepositional_phrases",
    "prepositional phrase": "prepositional_phrases",
    "prepositions": "prepositions",
    "preposition": "prepositions",
    "passive voice": "passive_voice",
    "passive": "passive_voice",
    "that-clause": "that_clause",
    "that clause": "that_clause",
    "wh-clause": "wh_clause",
    "wh clause": "wh_clause",
    "wh-question": "wh_question",
    "wh question": "wh_question",
    "conditional sentences": "conditional_sentences",
    "conditional sentence": "conditional_sentences",
    "conditional": "conditional_sentences",
    "questions and negatives": "questions_and_negatives",
    "negative": "questions_and_negatives",
}

_COMMON_PREPOSITIONS = {
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "around",
    "at",
    "before",
    "behind",
    "below",
    "beside",
    "between",
    "by",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "near",
    "of",
    "off",
    "on",
    "out",
    "over",
    "through",
    "to",
    "under",
    "with",
}
_PREP_OBJECT_RE = re.compile(
    r"\b(?:about|above|across|after|against|along|around|at|before|behind|below|beside|between|by|for|from|"
    r"in|inside|into|near|of|off|on|out|over|through|under|with)\b\s+"
    r"(?:the|a|an|this|that|these|those|my|your|his|her|its|our|their|me|him|her|us|them|[A-Za-z][A-Za-z'-]*)\b",
    re.IGNORECASE,
)
_TO_OBJECT_RE = re.compile(
    r"\bto\b\s+(?:the|a|an|this|that|these|those|my|your|his|her|its|our|their|me|him|her|us|them|[A-Z][a-z]+)\b"
)
_SENTENCE_LIKE_TOPICS = {
    "conditional_sentences",
    "modal",
    "passive_voice",
    "perfect",
    "progressive",
    "question_tags",
    "that_clause",
    "wh_clause",
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


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


def infer_topic_key(entry_head: str, notation_text: str) -> str:
    haystack = f"{_norm(entry_head).lower()} || {_norm(notation_text).lower()}"
    for term, topic_key in TERM_TO_TOPIC_KEY.items():
        if term in haystack:
            return topic_key
    return ""


def _row_id(row: dict[str, Any]) -> str:
    digest = hashlib.sha1(
        json.dumps(
            {
                "source_path": row.get("source_path"),
                "entry_head": row.get("entry_head"),
                "notation_text": row.get("notation_text"),
                "context_text": row.get("context_text"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"oxford_pair_{digest}"


def _pair_quality_ok(topic_key: str, context_text: str) -> bool:
    context_text = _norm(context_text)
    if not context_text:
        return False
    lowered = context_text.lower()
    words = re.findall(r"[A-Za-z']+", context_text)
    first = words[0].lower() if words else ""
    if "*" in context_text:
        return False
    if topic_key in _SENTENCE_LIKE_TOPICS and context_text[:1].islower():
        return False
    if lowered.startswith(("see ", "compare ", "also called ", "inserted, e.g.", "is different:", "that, provided")):
        return False
    if topic_key == "conditional_sentences":
        return any(marker in lowered for marker in ("if ", "unless ", "provided ", "providing "))
    if topic_key == "that_clause":
        return lowered.startswith("that ") or "(that)" in lowered or " ø " in f" {lowered} "
    if topic_key == "prepositions":
        if len(words) > 6 and context_text[-1] not in ".?!'\"":
            return False
        return bool("?" in context_text or "!" in context_text or _PREP_OBJECT_RE.search(context_text) or _TO_OBJECT_RE.search(context_text))
    if topic_key == "prepositional_phrases":
        return bool(_PREP_OBJECT_RE.search(context_text) or _TO_OBJECT_RE.search(context_text))
    return True


def _load_pair_rows(pairs_jsonl: str | list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(pairs_jsonl, str):
        paths = [pairs_jsonl]
    else:
        paths = [str(item) for item in pairs_jsonl]
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(list(_iter_jsonl(path)))
    return rows


def _clean_context_text(text: Any) -> str:
    value = _norm(text)
    if not value:
        return ""
    for marker in (" (compare:", " Compare ", " See also ", " See "):
        idx = value.find(marker)
        if idx > 0:
            value = _norm(value[:idx])
    return value.rstrip(" ,;:")


def _clean_notation_text(text: Any) -> str:
    value = _norm(text)
    if not value:
        return ""
    for prefix in ("congruence ", "conditioning ", "question tag ", "preposition "):
        if value.lower().startswith(prefix):
            value = _norm(value[len(prefix) :])
    return value


def build_oxford_dictionary_dataset(
    *,
    pairs_jsonl: str | list[str] | tuple[str, ...],
    spacy_model: str = "en_core_web_sm",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    pair_rows = _load_pair_rows(pairs_jsonl)

    contract_rows: list[dict[str, Any]] = []
    dataset_rows: list[dict[str, Any]] = []
    stats = {
        "pair_rows": len(pair_rows),
        "topic_mapped_rows": 0,
        "contracts_built": 0,
        "contracts_failed": 0,
        "matched_sentence_nodes": 0,
        "matched_phrase_nodes": 0,
        "dataset_rows": 0,
    }

    for pair in pair_rows:
        topic_key = str(pair.get("topic_key") or "").strip() or infer_topic_key(
            str(pair.get("entry_head") or ""),
            str(pair.get("notation_text") or ""),
        )
        if not topic_key:
            continue
        context_text = _clean_context_text(pair.get("context_text"))
        if not _pair_quality_ok(topic_key, context_text):
            continue
        stats["topic_mapped_rows"] += 1

        try:
            contract_doc = build_skeleton(context_text, nlp)
        except Exception:
            stats["contracts_failed"] += 1
            continue
        if not contract_doc:
            stats["contracts_failed"] += 1
            continue

        sentence_template = topic_to_template_id("Sentence", topic_key)
        phrase_template = topic_to_template_id("Phrase", topic_key)
        contract_doc = copy.deepcopy(contract_doc)
        row_id = _row_id(pair)
        matched_any = False

        for sentence_text, sentence_node in contract_doc.items():
            sentence_children = [child for child in (sentence_node.get("linguistic_elements") or []) if isinstance(child, dict)]
            sentence_payload = build_contract_template_payload(
                node=sentence_node,
                sentence_node=sentence_node,
                parent=None,
                path_types=["Sentence"],
                depth=0,
                sibling_index=0,
                sibling_count=1,
            )
            if sentence_payload is not None:
                sentence_node["contract_template_payload"] = sentence_payload
                if sentence_template and _template_ids_compatible(sentence_template, sentence_payload.get("template_id") or ""):
                    sentence_node["book_templated_notes"] = [
                        {
                            "source": "oxford_rulebook_v1",
                            "topic_key": topic_key,
                            "entry_head": pair.get("entry_head"),
                            "notation_text": pair.get("notation_text"),
                            "notation_text_clean": _clean_notation_text(pair.get("notation_text")),
                            "pair_method": pair.get("pair_method"),
                            "book_template_id": sentence_template,
                            "template_text": sentence_payload.get("template_text"),
                            "rendered_note_text": sentence_payload.get("rendered_note_text"),
                            "allowed_slots": sentence_payload.get("allowed_slots"),
                        }
                    ]
                    dataset_rows.append(
                        {
                            "row_id": row_id,
                            "source_path": pair.get("source_path"),
                            "entry_head": pair.get("entry_head"),
                            "topic_key": topic_key,
                            "node_level": "Sentence",
                            "context_text": context_text,
                            "notation_text": pair.get("notation_text"),
                            "notation_text_clean": _clean_notation_text(pair.get("notation_text")),
                            "pair_method": pair.get("pair_method"),
                            "matched_template_id": sentence_payload.get("template_id"),
                            "book_template_id": sentence_template,
                            "contract_template_payload": sentence_payload,
                        }
                    )
                    stats["matched_sentence_nodes"] += 1
                    stats["dataset_rows"] += 1
                    matched_any = True

            for index, child in enumerate(sentence_children):
                for node, parent, path_types, node_sibling_index, node_sibling_count in _walk_with_parent(
                    child,
                    parent=sentence_node,
                    path_types=["Sentence"],
                    sibling_index=index,
                    sibling_count=max(1, len(sentence_children)),
                ):
                    if str(node.get("type") or "") != "Phrase":
                        continue
                    payload = build_contract_template_payload(
                        node=node,
                        sentence_node=sentence_node,
                        parent=parent,
                        path_types=path_types,
                        depth=max(0, len(path_types) - 1),
                        sibling_index=node_sibling_index,
                        sibling_count=node_sibling_count,
                    )
                    if payload is None:
                        continue
                    node["contract_template_payload"] = payload
                    if phrase_template and _template_ids_compatible(phrase_template, payload.get("template_id") or ""):
                        node["book_templated_notes"] = [
                            {
                                "source": "oxford_rulebook_v1",
                                "topic_key": topic_key,
                                "entry_head": pair.get("entry_head"),
                                "notation_text": pair.get("notation_text"),
                                "notation_text_clean": _clean_notation_text(pair.get("notation_text")),
                                "pair_method": pair.get("pair_method"),
                                "book_template_id": phrase_template,
                                "template_text": payload.get("template_text"),
                                "rendered_note_text": payload.get("rendered_note_text"),
                                "allowed_slots": payload.get("allowed_slots"),
                            }
                        ]
                        dataset_rows.append(
                            {
                                "row_id": row_id,
                                "source_path": pair.get("source_path"),
                                "entry_head": pair.get("entry_head"),
                                "topic_key": topic_key,
                                "node_level": "Phrase",
                                "context_text": context_text,
                                "notation_text": pair.get("notation_text"),
                                "notation_text_clean": _clean_notation_text(pair.get("notation_text")),
                                "pair_method": pair.get("pair_method"),
                                "matched_template_id": payload.get("template_id"),
                                "book_template_id": phrase_template,
                                "contract_template_payload": payload,
                            }
                        )
                        stats["matched_phrase_nodes"] += 1
                        stats["dataset_rows"] += 1
                        matched_any = True

        contract_rows.append(
            {
                "row_id": row_id,
                "source_path": pair.get("source_path"),
                "entry_head": pair.get("entry_head"),
                "topic_key": topic_key,
                "notation_text": pair.get("notation_text"),
                "notation_text_clean": _clean_notation_text(pair.get("notation_text")),
                "context_text": context_text,
                "pair_method": pair.get("pair_method"),
                "book_template_id_sentence": sentence_template,
                "book_template_id_phrase": phrase_template,
                "context_contract": contract_doc,
                "matched_any": matched_any,
            }
        )
        stats["contracts_built"] += 1

    report = {
        "pipeline_version": "oxford_dictionary_dataset_v1",
        "pairs_jsonl": [str(Path(path).resolve()) for path in ([pairs_jsonl] if isinstance(pairs_jsonl, str) else pairs_jsonl)],
        "spacy_model": spacy_model,
        "stats": stats,
    }
    return contract_rows, dataset_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Oxford Dictionary dataset from rulebook note-context pairs.")
    parser.add_argument("--pairs-jsonl", required=True, nargs="+")
    parser.add_argument("--output-contract-jsonl", required=True)
    parser.add_argument("--output-dataset-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    args = parser.parse_args()

    contract_rows, dataset_rows, report = build_oxford_dictionary_dataset(
        pairs_jsonl=args.pairs_jsonl,
        spacy_model=args.spacy_model,
    )
    _write_jsonl(args.output_contract_jsonl, contract_rows)
    _write_jsonl(args.output_dataset_jsonl, dataset_rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
