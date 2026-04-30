"""Build T5 train/dev/test datasets from projected book->corpus JSONL.

The exporter selects one note candidate per eligible Sentence/Phrase node,
serializes the same contract-template payload used by runtime controlled notes,
deduplicates exact pairs, caps over-repeated targets, and splits data by source
document to reduce leakage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from ela_pipeline.annotate.contract_template_builder import (
    CONTRACT_PROMPT_TEMPLATE_VERSION,
    build_contract_template_payload,
    build_contract_template_training_prompt,
    normalize_template_text,
    template_uses_allowed_slots,
)
from ela_pipeline.dataset.template_topic_mapping import topic_to_template_id
from ela_pipeline.dataset.note_patterning import build_note_pattern
from ela_pipeline.dataset.build_dataset import (
    _count_by,
    _count_level_tam,
    _sanitize_training_target_text,
    _target_key,
    dedup_and_cap_rows,
    write_jsonl,
)


BOOK_PRIORITY = {
    "mark_lester_english_grammar_drills_2009": 100,
    "collins_cobuild_english_grammar_2011": 95,
    "george_yule_explaining_english_grammar_1998": 92,
    "betty_azar_basic_english_grammar_1996": 90,
    "oxford_advanced_2012": 88,
    "cobuild_grammar_2017": 87,
    "egiu_2019": 86,
    "borjars_burridge_2010": 84,
    "peter_simon_grammaring_guide_2013": 83,
    "phyllis_dutwin_grammar_demystified_2010": 82,
    "carter_2011": 80,
    "farlex_grammar_2016": 75,
    "geraldine_woods_grammar_dummies_2017": 70,
    "brehe_grammar_anatomy_2019": 68,
    "thiessen_academic_grammar_2025": 67,
    "internal_pedagogical_grammar": 10,
}

BOOK_WHITELIST = set(BOOK_PRIORITY.keys())

BAD_PHRASE_SOURCE_TOPICS = {
    ("geraldine_woods_grammar_dummies_2017", "prepositional phrase"),
    ("carter_2011", "prepositional phrases"),
    ("farlex_grammar_2016", "prepositional phrases"),
}

BAD_NOTE_SUBSTRINGS = (
    "see explanation",
    "(see",
    "e, above",
)

SAFE_INTERNAL_PHRASE_TOPICS = {
    "prepositional phrase",
    "verb phrase",
    "phrasal verb",
    "collocation",
}

QUOTE_RE = re.compile(r'["“](.*?)["”]')


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _quoted_fragments(text: str) -> List[str]:
    return [frag.strip() for frag in QUOTE_RE.findall(text or "") if frag.strip()]


def _candidate_target_text(candidate: Dict[str, Any]) -> str:
    slot_text = str(candidate.get("slot_rendered_note") or "").strip()
    if slot_text:
        return slot_text
    return str(candidate.get("note_text") or "").strip()


def _candidate_target_template(
    candidate: Dict[str, Any],
    payload: Dict[str, Any] | None,
    *,
    target_selection: str,
) -> tuple[str, str]:
    raw_note_text = normalize_template_text(candidate.get("note_text"))
    slot_rendered_note = normalize_template_text(candidate.get("slot_rendered_note"))
    canonical_template = normalize_template_text((payload or {}).get("template_text"))
    allowed_slots = list((payload or {}).get("allowed_slots") or [])
    payload_template_id = str((payload or {}).get("template_id") or "").strip()
    note_text_fallback = raw_note_text
    payload_level = ""
    if payload_template_id.startswith("SENT"):
        payload_level = "Sentence"
    elif payload_template_id.startswith("PHRASE"):
        payload_level = "Phrase"
    slot_template = normalize_template_text(candidate.get("slot_template_text"))
    candidate_topic = str(candidate.get("topic") or "")
    mapped_template_id = topic_to_template_id(payload_level, candidate_topic)
    compatible = True
    if mapped_template_id and payload_template_id:
        compatible = mapped_template_id == payload_template_id
        if not compatible and mapped_template_id == "SENT_NEGATION_GENERAL" and payload_template_id.startswith("SENT_NEGATION_"):
            compatible = True
        if not compatible and mapped_template_id == "SENT_CONDITIONAL_GENERAL" and payload_template_id.startswith("SENT_CONDITIONAL_"):
            compatible = True
        if not compatible and mapped_template_id == "SENT_PASSIVE_GENERAL" and payload_template_id.startswith("SENT_PASSIVE_"):
            compatible = True
        if not compatible and mapped_template_id == "SENT_QUESTION_WH" and payload_template_id in {"SENT_QUESTION_WH", "SENT_QUESTION_WH_DO_SUPPORT"}:
            compatible = True
        if not compatible and mapped_template_id == "PHRASE_PP_GENERAL" and payload_template_id.startswith("PHRASE_PP_"):
            compatible = True
        if not compatible and mapped_template_id == "PHRASE_RELATIVE_CLAUSE" and payload_template_id.startswith("PHRASE_RELATIVE_CLAUSE"):
            compatible = True
        if not compatible and mapped_template_id == "PHRASE_VP_GENERAL" and payload_template_id.startswith("PHRASE_VP_"):
            compatible = True

    if target_selection == "note_first":
        if note_text_fallback:
            return note_text_fallback, "note_text_fallback"
        if slot_rendered_note:
            return slot_rendered_note, "slot_rendered_note"
        if canonical_template and compatible:
            return canonical_template, "contract_template"
        return "", "missing_template"

    if (
        slot_template
        and bool(candidate.get("slot_templated"))
        and compatible
        and template_uses_allowed_slots(slot_template, allowed_slots)
    ):
        return slot_template, "slot_template"

    # Only use the contract template as the training target when the note topic
    # is semantically compatible with the selected runtime template. Otherwise
    # the exporter collapses diverse book notes into a few generic sentence
    # templates, which destroys the value of the projected supervision.
    if canonical_template and compatible:
        return canonical_template, "contract_template"
    if note_text_fallback:
        return note_text_fallback, "note_text_fallback"
    return "", "missing_template"


def _candidate_risk_flags(candidate: Dict[str, Any]) -> List[str]:
    flags = list(candidate.get("risk_flags") or [])
    slot_flags = list(candidate.get("slot_risk_flags") or [])
    return sorted(set(str(flag) for flag in flags + slot_flags if str(flag).strip()))


def _contains_bad_substring(text: str) -> bool:
    lower = text.lower()
    return any(bad in lower for bad in BAD_NOTE_SUBSTRINGS)


def _document_id(row: Dict[str, Any]) -> str:
    source_document = row.get("source_document")
    if isinstance(source_document, dict):
        doc_id = source_document.get("id")
        if isinstance(doc_id, str) and doc_id.strip():
            return doc_id.strip()
    text = str(row.get("sentence_text") or "").strip()
    return f"fallback::{text[:80]}"


def _candidate_note_id(candidate: Dict[str, Any], *, fallback_source: str, fallback_text: str) -> str:
    source_record_id = str(candidate.get("source_record_id") or "").strip()
    if source_record_id:
        return source_record_id
    payload = f"{fallback_source}::{fallback_text}".encode("utf-8")
    return f"note_{hashlib.sha1(payload).hexdigest()[:12]}"


def _simple_phrase_stub(phrase_entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "Phrase",
        "content": phrase_entry.get("content"),
        "part_of_speech": phrase_entry.get("part_of_speech"),
        "grammatical_role": phrase_entry.get("grammatical_role"),
        "cefr_level": None,
        "tense": None,
        "aspect": None,
        "mood": None,
        "voice": None,
        "finiteness": None,
        "tam_construction": None,
        "grammar_classes": None,
        "dep_label": None,
        "head_id": None,
        "source_span": phrase_entry.get("source_span"),
        "linguistic_elements": [],
    }


def _build_sentence_stub(row: Dict[str, Any]) -> Dict[str, Any]:
    phrase_entries = row.get("phrase_entries") or []
    top_level_children = [
        _simple_phrase_stub(phrase)
        for phrase in phrase_entries
        if phrase.get("parent_phrase_index") is None
    ]
    return {
        "type": "Sentence",
        "content": row.get("sentence_text"),
        "part_of_speech": "sentence",
        "grammatical_role": "clause",
        "cefr_level": None,
        "tense": None,
        "aspect": None,
        "mood": None,
        "voice": None,
        "finiteness": None,
        "tam_construction": None,
        "grammar_classes": None,
        "dep_label": None,
        "head_id": None,
        "source_span": row.get("source_span"),
        "linguistic_elements": top_level_children,
    }


def _phrase_maps(phrase_entries: List[Dict[str, Any]]) -> Tuple[Dict[int, Dict[str, Any]], Dict[int | None, List[int]]]:
    by_index: Dict[int, Dict[str, Any]] = {}
    children_by_parent: Dict[int | None, List[int]] = defaultdict(list)
    for phrase in phrase_entries:
        idx = int(phrase["phrase_index"])
        by_index[idx] = phrase
        parent_idx = phrase.get("parent_phrase_index")
        if isinstance(parent_idx, int):
            children_by_parent[parent_idx].append(idx)
        else:
            children_by_parent[None].append(idx)
    for group in children_by_parent.values():
        group.sort()
    return by_index, children_by_parent


def _build_phrase_stub(
    phrase_entry: Dict[str, Any],
    by_index: Dict[int, Dict[str, Any]],
    children_by_parent: Dict[int | None, List[int]],
) -> Dict[str, Any]:
    child_stubs = []
    for child_idx in children_by_parent.get(int(phrase_entry["phrase_index"]), []):
        child_stubs.append(_simple_phrase_stub(by_index[child_idx]))
    return {
        "type": "Phrase",
        "content": phrase_entry.get("content"),
        "part_of_speech": phrase_entry.get("part_of_speech"),
        "grammatical_role": phrase_entry.get("grammatical_role"),
        "cefr_level": None,
        "tense": None,
        "aspect": None,
        "mood": None,
        "voice": None,
        "finiteness": None,
        "tam_construction": None,
        "grammar_classes": None,
        "dep_label": None,
        "head_id": None,
        "source_span": phrase_entry.get("source_span"),
        "linguistic_elements": child_stubs,
    }


def _phrase_context(
    row: Dict[str, Any],
    phrase_entry: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str], int, int, int]:
    phrase_entries = row.get("phrase_entries") or []
    by_index, children_by_parent = _phrase_maps(phrase_entries)
    sentence_stub = _build_sentence_stub(row)
    phrase_stub = _build_phrase_stub(phrase_entry, by_index, children_by_parent)

    parent_idx = phrase_entry.get("parent_phrase_index")
    if isinstance(parent_idx, int) and parent_idx in by_index:
        parent_phrase = by_index[parent_idx]
        parent_stub = _build_phrase_stub(parent_phrase, by_index, children_by_parent)
        group = children_by_parent.get(parent_idx, [])
        depth = 2
        path_types = ["Sentence", "Phrase", "Phrase"]
    else:
        parent_stub = sentence_stub
        group = children_by_parent.get(None, [])
        depth = 1
        path_types = ["Sentence", "Phrase"]

    phrase_index = int(phrase_entry["phrase_index"])
    sibling_count = len(group) if group else 1
    sibling_index = group.index(phrase_index) if phrase_index in group else 0
    return sentence_stub, phrase_stub, path_types, depth, sibling_index, sibling_count, parent_stub


def _candidate_text_ok(note_text: str) -> bool:
    sanitized, reason = _sanitize_training_target_text(note_text)
    if sanitized is None:
        return False
    if _contains_bad_substring(sanitized):
        return False
    if sanitized.rstrip().endswith(":"):
        return False
    return True


def _sentence_candidate_ok(candidate: Dict[str, Any], sentence_text: str) -> bool:
    if _candidate_risk_flags(candidate):
        return False
    note_text = _candidate_target_text(candidate)
    if not _candidate_text_ok(note_text):
        return False
    if len(note_text.split()) > 45:
        return False
    for fragment in _quoted_fragments(note_text):
        if len(fragment) <= 1:
            continue
        if fragment.lower() not in sentence_text.lower():
            return False
    return True


def _phrase_candidate_ok(candidate: Dict[str, Any], phrase_text: str, sentence_text: str) -> bool:
    if _candidate_risk_flags(candidate):
        return False
    source_book = str(candidate.get("source_book") or "")
    topic = str(candidate.get("topic") or "")
    slot_safe = bool(candidate.get("slot_templated")) and bool(candidate.get("slot_rendered_note"))
    if (source_book, topic) in BAD_PHRASE_SOURCE_TOPICS and not slot_safe:
        return False
    if source_book == "internal_pedagogical_grammar":
        if not (topic in SAFE_INTERNAL_PHRASE_TOPICS or topic.startswith("preposition:") or topic.startswith("pp_")):
            return False
    note_text = _candidate_target_text(candidate)
    if not _candidate_text_ok(note_text):
        return False
    if len(note_text.split()) > 40:
        return False
    for fragment in _quoted_fragments(note_text):
        if len(fragment) <= 1:
            continue
        lower = fragment.lower()
        if lower not in phrase_text.lower() and lower not in sentence_text.lower():
            return False
    return True


def _candidate_priority(candidate: Dict[str, Any]) -> Tuple[int, int, int]:
    source_book = str(candidate.get("source_book") or "")
    note_text = _candidate_target_text(candidate)
    return (
        BOOK_PRIORITY.get(source_book, 0),
        1 if candidate.get("slot_templated") else 0,
        1 if not candidate.get("templated") else 0,
        len(note_text.split()),
    )


def _choose_candidate(
    candidates: List[Dict[str, Any]],
    *,
    level: str,
    sentence_text: str,
    phrase_text: str = "",
    mode: str,
) -> Dict[str, Any] | None:
    accepted: List[Dict[str, Any]] = []
    for candidate in candidates:
        source_book = str(candidate.get("source_book") or "")
        if source_book not in BOOK_WHITELIST:
            continue
        if mode == "book_only" and source_book == "internal_pedagogical_grammar":
            continue
        ok = (
            _sentence_candidate_ok(candidate, sentence_text)
            if level == "Sentence"
            else _phrase_candidate_ok(candidate, phrase_text, sentence_text)
        )
        if ok:
            accepted.append(candidate)

    if not accepted:
        return None
    accepted.sort(key=_candidate_priority, reverse=True)
    return accepted[0]


def _choose_candidates(
    candidates: List[Dict[str, Any]],
    *,
    level: str,
    sentence_text: str,
    phrase_text: str = "",
    mode: str,
    max_candidates: int,
) -> List[Dict[str, Any]]:
    accepted: List[Dict[str, Any]] = []
    seen_note_texts: set[str] = set()

    for candidate in sorted(candidates, key=_candidate_priority, reverse=True):
        source_book = str(candidate.get("source_book") or "")
        if source_book not in BOOK_WHITELIST:
            continue
        if mode == "book_only" and source_book == "internal_pedagogical_grammar":
            continue
        ok = (
            _sentence_candidate_ok(candidate, sentence_text)
            if level == "Sentence"
            else _phrase_candidate_ok(candidate, phrase_text, sentence_text)
        )
        if not ok:
            continue
        note_text_key = _candidate_target_text(candidate).strip().lower()
        if not note_text_key or note_text_key in seen_note_texts:
            continue
        seen_note_texts.add(note_text_key)
        accepted.append(candidate)
        if len(accepted) >= max(1, int(max_candidates)):
            break

    return accepted


def _make_sentence_row(row: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
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
    prompt = build_contract_template_training_prompt(payload or {}, node_level="Sentence")
    target_template, target_variant = _candidate_target_template(
        candidate,
        payload,
        target_selection=str(row.get("_target_selection") or "canonical_first"),
    )
    note_pattern = build_note_pattern(
        note_text=target_template,
        sentence_text=str(row.get("sentence_text") or ""),
        slot_template_text=str(candidate.get("slot_template_text") or ""),
        slot_values=dict(candidate.get("slot_values") or {}),
    )
    source_document = row.get("source_document") or {}
    source_name = source_document.get("source_name") or row.get("projection_version") or candidate.get("source_book")
    note_text = target_template
    return {
        "input": prompt,
        "target": target_template,
        "target_rendered": target_template,
        "note_text": note_text,
        "note_id": _candidate_note_id(candidate, fallback_source=str(source_name or ""), fallback_text=note_text),
        "source": str(source_name or ""),
        "target_pattern": note_pattern["pattern_text"],
        "target_pattern_slots": note_pattern["slot_values"],
        "target_pattern_source": note_pattern["pattern_source"],
        "spacy_signature_depth": row.get("spacy_signature_depth"),
        "spacy_signature": row.get("spacy_signature"),
        "spacy_signature_nodes": row.get("spacy_signature_nodes"),
        "spacy_signature_family_id": row.get("spacy_signature_family_id"),
        "level": "Sentence",
        "tam_bucket": "none",
        "prompt_template_version": CONTRACT_PROMPT_TEMPLATE_VERSION,
        "source_document_id": source_document.get("id"),
        "source_name": source_document.get("source_name"),
        "sentence_text": row.get("sentence_text"),
        "target_content": row.get("sentence_text"),
        "note_source_book": candidate.get("source_book"),
        "note_topic": candidate.get("topic"),
        "note_origin_unit": candidate.get("origin_unit"),
        "note_match_level": candidate.get("match_level"),
        "note_selection_mode": "book_preferred",
        "note_target_variant": target_variant,
        "note_source_tier": "internal_fallback"
        if candidate.get("source_book") == "internal_pedagogical_grammar"
        else "book",
        "projection_version": row.get("projection_version"),
        "split_group_id": _document_id(row),
    }


def _make_phrase_row(row: Dict[str, Any], phrase_entry: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
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
    prompt = build_contract_template_training_prompt(payload or {}, node_level="Phrase")
    target_template, target_variant = _candidate_target_template(
        candidate,
        payload,
        target_selection=str(row.get("_target_selection") or "canonical_first"),
    )
    note_pattern = build_note_pattern(
        note_text=target_template,
        sentence_text=str(row.get("sentence_text") or ""),
        slot_template_text=str(candidate.get("slot_template_text") or ""),
        slot_values=dict(candidate.get("slot_values") or {}),
    )
    source_document = row.get("source_document") or {}
    source_name = source_document.get("source_name") or row.get("projection_version") or candidate.get("source_book")
    note_text = target_template
    return {
        "input": prompt,
        "target": target_template,
        "target_rendered": target_template,
        "note_text": note_text,
        "note_id": _candidate_note_id(candidate, fallback_source=str(source_name or ""), fallback_text=note_text),
        "source": str(source_name or ""),
        "target_pattern": note_pattern["pattern_text"],
        "target_pattern_slots": note_pattern["slot_values"],
        "target_pattern_source": note_pattern["pattern_source"],
        "spacy_signature_depth": row.get("spacy_signature_depth"),
        "spacy_signature": row.get("spacy_signature"),
        "spacy_signature_nodes": row.get("spacy_signature_nodes"),
        "spacy_signature_family_id": row.get("spacy_signature_family_id"),
        "level": "Phrase",
        "tam_bucket": "none",
        "prompt_template_version": CONTRACT_PROMPT_TEMPLATE_VERSION,
        "source_document_id": source_document.get("id"),
        "source_name": source_document.get("source_name"),
        "sentence_text": row.get("sentence_text"),
        "target_content": phrase_entry.get("content"),
        "note_source_book": candidate.get("source_book"),
        "note_topic": candidate.get("topic"),
        "note_origin_unit": candidate.get("origin_unit"),
        "note_match_level": candidate.get("match_level"),
        "note_selection_mode": "book_preferred",
        "note_target_variant": target_variant,
        "note_source_tier": "internal_fallback"
        if candidate.get("source_book") == "internal_pedagogical_grammar"
        else "book",
        "projection_version": row.get("projection_version"),
        "split_group_id": _document_id(row),
    }


def _build_rows(
    projected_path: Path,
    mode: str,
    *,
    max_sentence_targets_per_node: int = 1,
    target_selection: str = "canonical_first",
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    rows: List[Dict[str, Any]] = []
    counters: Dict[str, int] = defaultdict(int)
    for item in _iter_jsonl(projected_path):
        item["_target_selection"] = target_selection
        sentence_text = str(item.get("sentence_text") or "")
        sentence_candidates = _choose_candidates(
            item.get("sentence_note_candidates") or [],
            level="Sentence",
            sentence_text=sentence_text,
            mode=mode,
            max_candidates=max_sentence_targets_per_node,
        )
        for sentence_candidate in sentence_candidates:
            rows.append(_make_sentence_row(item, sentence_candidate))
            counters["sentence_rows_selected"] += 1
            counters[f"source__{sentence_candidate.get('source_book') or 'unknown'}"] += 1

        for phrase_entry in item.get("phrase_entries") or []:
            phrase_candidate = _choose_candidate(
                phrase_entry.get("note_candidates") or [],
                level="Phrase",
                phrase_text=str(phrase_entry.get("content") or ""),
                sentence_text=sentence_text,
                mode=mode,
            )
            if phrase_candidate:
                rows.append(_make_phrase_row(item, phrase_entry, phrase_candidate))
                counters["phrase_rows_selected"] += 1
                counters[f"source__{phrase_candidate.get('source_book') or 'unknown'}"] += 1
    return rows, counters


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

    group_items = list(grouped.items())
    rng = random.Random(seed)
    rng.shuffle(group_items)

    total = len(rows)
    target_test = int(total * test_ratio)
    target_dev = int(total * dev_ratio)

    test: List[Dict[str, Any]] = []
    dev: List[Dict[str, Any]] = []
    train: List[Dict[str, Any]] = []

    for _, group_rows in group_items:
        if len(test) < target_test:
            test.extend(group_rows)
        elif len(dev) < target_dev:
            dev.extend(group_rows)
        else:
            train.extend(group_rows)
    return train, dev, test


def _target_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(_target_key(str(row.get("target") or "")) for row in rows)
    top = counts.most_common(20)
    return {
        "total": len(rows),
        "unique_targets": len(counts),
        "duplicate_ratio": round(1 - (len(counts) / len(rows)), 6) if rows else 0.0,
        "top_repeated_targets": [{"target": target, "count": count} for target, count in top],
    }


def _note_source_distribution(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return dict(sorted(Counter(str(row.get("note_source_book") or "unknown") for row in rows).items()))


def _cap_by_topic_and_source(
    rows: List[Dict[str, Any]],
    *,
    max_per_topic: int,
    max_per_source_sentence: int,
    max_per_source_phrase: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    if max_per_topic <= 0 and max_per_source_sentence <= 0 and max_per_source_phrase <= 0:
        return rows[:], {
            "skipped_by_topic_cap": 0,
            "skipped_by_source_cap": 0,
        }

    topic_counts: Counter[Tuple[str, str, str]] = Counter()
    source_counts: Counter[Tuple[str, str]] = Counter()
    kept: List[Dict[str, Any]] = []
    skipped_by_topic = 0
    skipped_by_source = 0

    for row in rows:
        level = str(row.get("level") or "Unknown")
        source_book = str(row.get("note_source_book") or "unknown")
        topic = str(row.get("note_topic") or "unknown")
        topic_key = (level, source_book, topic)
        source_key = (level, source_book)

        if max_per_topic > 0 and topic_counts[topic_key] >= max_per_topic:
            skipped_by_topic += 1
            continue

        source_cap = 0
        if level == "Sentence":
            source_cap = max_per_source_sentence
        elif level == "Phrase":
            source_cap = max_per_source_phrase
        if source_cap > 0 and source_counts[source_key] >= source_cap:
            skipped_by_source += 1
            continue

        kept.append(row)
        topic_counts[topic_key] += 1
        source_counts[source_key] += 1

    return kept, {
        "skipped_by_topic_cap": skipped_by_topic,
        "skipped_by_source_cap": skipped_by_source,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build T5 dataset from projected corpus JSONL")
    parser.add_argument(
        "--input",
        default="data/processed_corpus_book_projection_v15/ingested_corpus_book_projection_v15.jsonl",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", choices=["book_only", "hybrid"], default="hybrid")
    parser.add_argument(
        "--target-selection",
        choices=["canonical_first", "note_first"],
        default="canonical_first",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--max-per-target", type=int, default=40)
    parser.add_argument("--max-per-topic", type=int, default=0)
    parser.add_argument("--max-per-source-sentence", type=int, default=0)
    parser.add_argument("--max-per-source-phrase", type=int, default=0)
    parser.add_argument("--max-sentence-targets-per-node", type=int, default=1)
    parser.add_argument(
        "--dedup-exact-input-target",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()

    projected_path = Path(args.input)
    rows_before_dedup, selection_counters = _build_rows(
        projected_path,
        mode=args.mode,
        max_sentence_targets_per_node=int(args.max_sentence_targets_per_node),
        target_selection=str(args.target_selection),
    )
    rows_after_dedup, dedup_report = dedup_and_cap_rows(
        rows_before_dedup,
        max_per_target=int(args.max_per_target),
        dedup_exact_input_target=bool(args.dedup_exact_input_target),
    )
    rows_after_topic_source_caps, topic_source_report = _cap_by_topic_and_source(
        rows_after_dedup,
        max_per_topic=int(args.max_per_topic),
        max_per_source_sentence=int(args.max_per_source_sentence),
        max_per_source_phrase=int(args.max_per_source_phrase),
    )
    train, dev, test = _split_by_group(
        rows_after_topic_source_caps,
        seed=int(args.seed),
        dev_ratio=float(args.dev_ratio),
        test_ratio=float(args.test_ratio),
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(rows_after_topic_source_caps, str(out_dir / "all.jsonl"))
    write_jsonl(train, str(out_dir / "train.jsonl"))
    write_jsonl(dev, str(out_dir / "dev.jsonl"))
    write_jsonl(test, str(out_dir / "test.jsonl"))

    stats = {
        "task": "linguistic_note",
        "builder": "build_t5_dataset_from_projected_corpus.py",
        "mode": args.mode,
        "target_selection": args.target_selection,
        "prompt_template_version": CONTRACT_PROMPT_TEMPLATE_VERSION,
        "input_path": str(projected_path.resolve()),
        "total_before_dedup": len(rows_before_dedup),
        "total_after_dedup": len(rows_after_dedup),
        "total_after_balance": len(rows_after_topic_source_caps),
        "balance_level_tam": False,
        "max_per_target": int(args.max_per_target),
        "max_per_topic": int(args.max_per_topic),
        "max_per_source_sentence": int(args.max_per_source_sentence),
        "max_per_source_phrase": int(args.max_per_source_phrase),
        "max_sentence_targets_per_node": int(args.max_sentence_targets_per_node),
        "dedup_exact_input_target": bool(args.dedup_exact_input_target),
        "dedup_report": dedup_report,
        "topic_source_report": topic_source_report,
        "quality_counters": dict(sorted(selection_counters.items())),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "target_stats": {
            "before_dedup": _target_stats(rows_before_dedup),
            "after_dedup": _target_stats(rows_after_dedup),
            "after_balance": _target_stats(rows_after_topic_source_caps),
        },
        "distributions": {
            "after_dedup": {
                "level": _count_by(rows_after_topic_source_caps, lambda row: row.get("level", "Unknown")),
                "tam_bucket": _count_by(rows_after_topic_source_caps, lambda row: row.get("tam_bucket", "none")),
                "level_tam": _count_level_tam(rows_after_topic_source_caps),
                "note_source_book": _note_source_distribution(rows_after_topic_source_caps),
            }
        },
        "split_strategy": "group_by_source_document_id",
    }
    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
