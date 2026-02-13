"""Build train/dev/test JSONL pairs for linguistic notes generation."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

TELEMETRY_PATTERNS = (
    re.compile(r"\bquality_flags\b", re.IGNORECASE),
    re.compile(r"\breason_codes\b", re.IGNORECASE),
    re.compile(r"\brejected_candidates\b", re.IGNORECASE),
    re.compile(r"\brejected_candidate_stats\b", re.IGNORECASE),
    re.compile(r"\brejected_[a-z_]+\b", re.IGNORECASE),
)

LOW_QUALITY_NOTE_PATTERNS = (
    re.compile(r"^\s*node content\.?\s*(part of speech)?\.?\s*$", re.IGNORECASE),
    re.compile(r"\bpart of speech\b", re.IGNORECASE),
    re.compile(r"\bverb-?centred phrase expressing what happens to or about the subject\b", re.IGNORECASE),
    re.compile(r"\bsubordinate clause of concession\b", re.IGNORECASE),
    re.compile(r"\bsubordinate clause of reason\b", re.IGNORECASE),
    re.compile(r"\bsubordinate clause of reference\b", re.IGNORECASE),
    re.compile(r"^\s*sentence:\s*", re.IGNORECASE),
)

PROMPT_TEMPLATE_VERSION = "v1"


def format_feature_list(features: List[str]) -> str:
    return ", ".join(features).replace("|", ":")


def _sentence_count(text: str) -> int:
    parts = [p.strip() for p in re.split(r"[.!?]+", text) if p.strip()]
    return len(parts)


def _is_style_compliant(text: str) -> bool:
    for pattern in LOW_QUALITY_NOTE_PATTERNS:
        if pattern.search(text):
            return False
    sentence_n = _sentence_count(text)
    return 1 <= sentence_n <= 2


def _sanitize_training_target_text(text: str) -> Tuple[str | None, str | None]:
    clean = text.strip()
    if not clean:
        return None, "EMPTY"
    for pattern in TELEMETRY_PATTERNS:
        if pattern.search(clean):
            return None, "TELEMETRY"
    if not _is_style_compliant(clean):
        return None, "LOW_QUALITY_STYLE"
    return clean, None


def _target_key(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _node_input_text(node: Dict[str, Any]) -> str:
    text = node.get("input")
    if isinstance(text, str) and text.strip():
        return text
    content = node.get("content")
    if isinstance(content, str):
        return content
    return ""


POS_LABELS = {
    "ADJ": "adjective",
    "ADP": "preposition",
    "ADV": "adverb",
    "AUX": "auxiliary verb",
    "CCONJ": "coordinating conjunction",
    "DET": "determiner",
    "INTJ": "interjection",
    "NOUN": "noun",
    "NUM": "numeral",
    "PART": "particle",
    "PRON": "pronoun",
    "PROPN": "proper noun",
    "PUNCT": "punctuation mark",
    "SCONJ": "subordinating conjunction",
    "SYM": "symbol",
    "VERB": "verb",
    "X": "word form",
}

DEP_ROLE_LABELS = {
    "nsubj": "subject",
    "nsubjpass": "passive subject",
    "dobj": "direct object",
    "iobj": "indirect object",
    "pobj": "object of a preposition",
    "attr": "predicative complement",
    "acomp": "adjectival complement",
    "advmod": "adverbial modifier",
    "amod": "adjectival modifier",
    "prep": "prepositional linker",
    "pcomp": "complement of a preposition",
    "aux": "auxiliary dependency",
    "det": "determiner dependency",
    "ROOT": "clause head",
}

TEMPLATE_IDS = {
    "SENTENCE_FINITE_CLAUSE",
    "CLAUSE_SUBORDINATE_TIME",
    "CLAUSE_SUBORDINATE_REASON",
    "CLAUSE_SUBORDINATE_CONCESSION",
    "VP_MODAL_PERFECT",
    "VP_AUXILIARY",
    "VP_PARTICIPLE",
    "NP_POSSESSIVE",
    "NP_DETERMINER_NOUN",
    "PP_TIME_BEFORE_ING",
    "PP_GENERAL_LINKING",
    "WORD_AUX_MODAL",
    "WORD_AUX_HAVE",
    "WORD_VERB_PARTICIPLE",
    "WORD_PRONOUN_POSSESSIVE",
    "WORD_NOUN_COMMON",
    "WORD_ARTICLE_DEFINITE",
    "WORD_PREPOSITION",
    "WORD_VERB_ING",
}

TEMPLATE_NOTE_LIBRARY = {
    "SENTENCE_FINITE_CLAUSE": "This is a finite clause expressing a complete proposition.",
    "CLAUSE_SUBORDINATE_TIME": "This clause marks a time relation inside the sentence.",
    "CLAUSE_SUBORDINATE_REASON": "This clause expresses a reason for the main event.",
    "CLAUSE_SUBORDINATE_CONCESSION": "This clause marks concession against the main statement.",
    "VP_MODAL_PERFECT": "This verb phrase shows modal meaning with perfect aspect.",
    "VP_AUXILIARY": "This verb phrase uses an auxiliary to support tense or mood.",
    "VP_PARTICIPLE": "This verb phrase is built around a participle form.",
    "NP_POSSESSIVE": "This noun phrase marks possession inside the noun group.",
    "NP_DETERMINER_NOUN": "This noun phrase combines a determiner with a noun head.",
    "PP_TIME_BEFORE_ING": "This prepositional phrase marks time with 'before' plus an -ing form.",
    "PP_GENERAL_LINKING": "This prepositional phrase links a complement to the clause.",
    "WORD_AUX_MODAL": "This word is a modal auxiliary marking speaker stance or obligation.",
    "WORD_AUX_HAVE": "This word is auxiliary 'have' supporting perfect construction.",
    "WORD_VERB_PARTICIPLE": "This word is a participle verb form in the verbal group.",
    "WORD_PRONOUN_POSSESSIVE": "This word is a possessive pronoun or determiner in a noun phrase.",
    "WORD_NOUN_COMMON": "This word is a common noun naming an entity in context.",
    "WORD_ARTICLE_DEFINITE": "This word is the definite article specifying a known referent.",
    "WORD_PREPOSITION": "This word is a preposition linking a complement to another element.",
    "WORD_VERB_ING": "This word is an -ing verb form with non-finite function.",
}

HARD_BANNED_PREFIXES = (
    "sentence:",
    "phrase:",
    "word:",
    "node content",
    "part of speech",
    "node type",
)

HARD_BANNED_SUBSTRINGS = (
    "sensibilisation",
    "sensence",
    "nod to",
    "node content",
    "none. node content",
    "sensual",
    "sensational",
)

MODAL_AUX = {"should", "could", "would", "might", "may", "must", "can", "will", "shall"}
POSSESSIVES = {"my", "your", "his", "her", "our", "their", "its"}


def _stable_variant_index(*parts: str, modulo: int = 2) -> int:
    payload = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(digest[:8], 16) % max(1, modulo)


def _primary_feature(features: Dict[str, Any], key: str, fallback: str = "UNKNOWN") -> str:
    vals = features.get(key, [])
    if isinstance(vals, list) and vals:
        v = vals[0]
        if isinstance(v, str) and v.strip():
            return v.strip()
    return fallback


def _dep_role_text(dep: str) -> str:
    return DEP_ROLE_LABELS.get(dep, dep.lower().replace("_", " "))


def _phrase_kind(features: Dict[str, Any]) -> str:
    pos_list = [p for p in features.get("pos", []) if isinstance(p, str)]
    pos_set = set(pos_list)
    if "ADP" in pos_set and ("NOUN" in pos_set or "PROPN" in pos_set or "PRON" in pos_set):
        return "prepositional phrase"
    if "VERB" in pos_set or "AUX" in pos_set:
        return "verb phrase"
    if "NOUN" in pos_set or "PROPN" in pos_set or "PRON" in pos_set:
        return "noun phrase"
    if "ADJ" in pos_set:
        return "adjectival phrase"
    if "ADV" in pos_set:
        return "adverbial phrase"
    return "phrase"


def _node_tokens(text: str) -> List[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _looks_gerund(text: str, features: Dict[str, Any]) -> bool:
    tags = [str(t) for t in features.get("tag", [])]
    if any(t.upper() == "VBG" for t in tags):
        return True
    return any(tok.endswith("ing") and len(tok) > 4 for tok in _node_tokens(text))


def _looks_participle(features: Dict[str, Any]) -> bool:
    tags = [str(t).upper() for t in features.get("tag", [])]
    morph = " ".join(str(m) for m in features.get("morph", []))
    return "VBN" in tags or ("VerbForm=Part" in morph and "Tense=Past" in morph)


def _template_id_for_node(level: str, node_text: str, features: Dict[str, Any], tam_bucket: str) -> str:
    tokens = _node_tokens(node_text)
    pos_set = {str(p).upper() for p in features.get("pos", [])}
    dep = _primary_feature(features, "dep", fallback="").lower()
    first = tokens[0] if tokens else ""

    if level == "Sentence":
        if first in {"before", "after", "when", "while"}:
            return "CLAUSE_SUBORDINATE_TIME"
        if first in {"because", "since", "as"}:
            return "CLAUSE_SUBORDINATE_REASON"
        if first in {"although", "though"}:
            return "CLAUSE_SUBORDINATE_CONCESSION"
        return "SENTENCE_FINITE_CLAUSE"

    if level == "Phrase":
        if first == "before" and _looks_gerund(node_text, features):
            return "PP_TIME_BEFORE_ING"
        if "ADP" in pos_set:
            return "PP_GENERAL_LINKING"
        if any(tok in POSSESSIVES for tok in tokens):
            return "NP_POSSESSIVE"
        if "DET" in pos_set and ("NOUN" in pos_set or "PROPN" in pos_set):
            return "NP_DETERMINER_NOUN"
        if tam_bucket == "modal_perfect" or (any(t in MODAL_AUX for t in tokens) and "have" in tokens):
            return "VP_MODAL_PERFECT"
        if "AUX" in pos_set:
            return "VP_AUXILIARY"
        if _looks_participle(features):
            return "VP_PARTICIPLE"
        if "VERB" in pos_set:
            return "VP_AUXILIARY"
        return "NP_DETERMINER_NOUN"

    # Word
    pos = _primary_feature(features, "pos", fallback="").upper()
    if pos == "AUX" and first in MODAL_AUX:
        return "WORD_AUX_MODAL"
    if pos == "AUX" and first == "have":
        return "WORD_AUX_HAVE"
    if pos == "VERB" and _looks_gerund(node_text, features):
        return "WORD_VERB_ING"
    if pos == "VERB" and _looks_participle(features):
        return "WORD_VERB_PARTICIPLE"
    if pos == "PRON" and dep == "poss":
        return "WORD_PRONOUN_POSSESSIVE"
    if pos == "NOUN" or pos == "PROPN":
        return "WORD_NOUN_COMMON"
    if pos == "DET" and first == "the":
        return "WORD_ARTICLE_DEFINITE"
    if pos == "ADP":
        return "WORD_PREPOSITION"
    if pos == "VERB":
        return "WORD_VERB_PARTICIPLE"
    return "WORD_NOUN_COMMON"


def _is_hard_rule_compliant_note(note: str) -> bool:
    s = " ".join(note.strip().split())
    if not s:
        return False
    if len(s.split()) > 30:
        return False
    if _sentence_count(s) < 1 or _sentence_count(s) > 2:
        return False
    sl = s.lower()
    if any(sl.startswith(prefix) for prefix in HARD_BANNED_PREFIXES):
        return False
    if any(bad in sl for bad in HARD_BANNED_SUBSTRINGS):
        return False
    if re.search(r"[<{].*[>}]", s):
        return False
    if re.search(r"\b(i|you|we|llm|chatgpt|model)\b", sl):
        return False
    return True


def _build_template_target(level: str, node_text: str, features: Dict[str, Any], tam_bucket: str) -> Tuple[str | None, str | None]:
    template_id = _template_id_for_node(level, node_text, features, tam_bucket)
    if template_id not in TEMPLATE_IDS:
        return None, "UNKNOWN_TEMPLATE_ID"
    note = TEMPLATE_NOTE_LIBRARY.get(template_id, "")
    if not _is_hard_rule_compliant_note(note):
        return None, "TEMPLATE_RULE_VIOLATION"
    return f"{template_id}|{note}", None


def _build_reference_note(
    *,
    level: str,
    node_text: str,
    features: Dict[str, Any],
    tam_bucket: str,
) -> str:
    dep = _primary_feature(features, "dep", fallback="dep")
    role = _dep_role_text(dep)

    if level == "Word":
        pos = _primary_feature(features, "pos", fallback="X")
        pos_label = POS_LABELS.get(pos, pos.lower())
        idx = _stable_variant_index(level, node_text, pos, dep, tam_bucket, modulo=3)
        if idx == 0:
            return f"'{node_text}' functions as a {pos_label} and serves as {role} in the clause."
        if idx == 1:
            return f"In this sentence, '{node_text}' is used as a {pos_label} with a {dep} dependency role."
        return f"'{node_text}' is a {pos_label} contributing to the clause as {role}."

    if level == "Phrase":
        kind = _phrase_kind(features)
        idx = _stable_variant_index(level, node_text, kind, dep, tam_bucket, modulo=2)
        if idx == 0:
            return f"The phrase '{node_text}' is a {kind} functioning as {role} in the sentence."
        return f"'{node_text}' forms a {kind} and contributes a {role} role in clause structure."

    # Sentence
    pos_seq = [p for p in features.get("pos", []) if isinstance(p, str)]
    finite_hint = "finite" if any(t in {"VERB", "AUX"} for t in pos_seq) else "non-finite"
    idx = _stable_variant_index(level, node_text, tam_bucket, finite_hint, modulo=2)
    if idx == 0:
        return (
            f"This sentence is a {finite_hint} clause with a {tam_bucket} TAM profile, "
            f"expressing a complete proposition."
        )
    return (
        f"The sentence encodes a complete clause-level meaning with {finite_hint} structure "
        f"and TAM bucket '{tam_bucket}'."
    )


def _extract_note_from_targets(targets: Dict[str, Any], counters: Dict[str, int] | None = None) -> str | None:
    if not isinstance(targets, dict):
        return None
    notes = targets.get("notes")
    if not isinstance(notes, list):
        legacy = targets.get("linguistic_notes")
        if isinstance(legacy, str):
            sanitized, reason = _sanitize_training_target_text(legacy)
            if sanitized:
                if counters is not None:
                    counters["legacy_notes_used"] += 1
                return sanitized
            if counters is not None and reason:
                counters[f"filtered_{reason.lower()}"] += 1
        return None

    if counters is not None:
        counters["notes_array_seen"] += 1

    for note in notes:
        if not isinstance(note, dict):
            continue
        text = note.get("text")
        if not isinstance(text, str):
            continue
        if note.get("source") != "model":
            continue
        sanitized, reason = _sanitize_training_target_text(text)
        if sanitized:
            if counters is not None:
                counters["model_notes_used"] += 1
            return sanitized
        if counters is not None and reason:
            counters[f"filtered_{reason.lower()}"] += 1
    return None


def _extract_tam_bucket(node: Dict[str, Any]) -> str:
    direct = node.get("tam_construction")
    if isinstance(direct, str) and direct.strip():
        return direct.strip().lower()
    targets = node.get("targets")
    if isinstance(targets, dict):
        nested = targets.get("tam_construction")
        if isinstance(nested, str) and nested.strip():
            return nested.strip().lower()
    return "none"


def _render_sentence_prompt(sentence: str, pos_text: str, dep_text: str, tam_bucket: str) -> str:
    return (
        f"task: write_linguistic_note "
        f"template_version: {PROMPT_TEMPLATE_VERSION} "
        f"node_type: Sentence "
        f"tam_bucket: {tam_bucket} "
        f"sentence: {sentence} "
        f"pos: {pos_text} "
        f"dep: {dep_text}"
    )


def _render_phrase_prompt(sentence: str, phrase_text: str, pos_text: str, dep_text: str, tam_bucket: str) -> str:
    return (
        f"task: write_linguistic_note "
        f"template_version: {PROMPT_TEMPLATE_VERSION} "
        f"node_type: Phrase "
        f"tam_bucket: {tam_bucket} "
        f"sentence: {sentence} "
        f"phrase: {phrase_text} "
        f"pos: {pos_text} "
        f"dep: {dep_text}"
    )


def _render_word_prompt(
    sentence: str,
    word_text: str,
    pos_text: str,
    tag_text: str,
    dep_text: str,
    morph_text: str,
    tam_bucket: str,
) -> str:
    return (
        f"task: write_linguistic_note "
        f"template_version: {PROMPT_TEMPLATE_VERSION} "
        f"node_type: Word "
        f"tam_bucket: {tam_bucket} "
        f"sentence: {sentence} "
        f"word: {word_text} "
        f"pos: {pos_text} "
        f"tag: {tag_text} "
        f"dep: {dep_text} "
        f"morph: {morph_text}"
    )


def iter_examples(
    item: Dict[str, Any],
    counters: Dict[str, int] | None = None,
    *,
    use_reference_templates: bool = False,
    use_template_id_targets: bool = False,
) -> Iterable[Dict[str, str]]:
    sentence = _node_input_text(item)
    sent_features = item.get("features", {})
    sent_targets = item.get("targets", {})

    sent_tam = _extract_tam_bucket(item)
    if use_template_id_targets:
        sentence_note, reason = _build_template_target("Sentence", sentence, sent_features, sent_tam)
        if counters is not None:
            if sentence_note:
                counters["template_targets_used"] += 1
            elif reason:
                counters[f"template_filtered_{reason.lower()}"] += 1
    elif use_reference_templates:
        sentence_note = _build_reference_note(
            level="Sentence",
            node_text=sentence,
            features=sent_features,
            tam_bucket=sent_tam,
        )
    else:
        sentence_note = _extract_note_from_targets(sent_targets, counters=counters)

    if sentence_note:
        prompt = _render_sentence_prompt(
            sentence=sentence,
            pos_text=format_feature_list(sent_features.get("pos", [])),
            dep_text=format_feature_list(sent_features.get("dep", [])),
            tam_bucket=sent_tam,
        )
        yield {
            "input": prompt,
            "target": sentence_note,
            "level": "Sentence",
            "tam_bucket": sent_tam,
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        }
        if counters is not None:
            counters["rows_emitted"] += 1

    for phrase in item.get("linguistic_elements", []):
        if phrase.get("type") != "Phrase":
            continue
        phrase_tam = _extract_tam_bucket(phrase)
        phrase_text = _node_input_text(phrase)
        phrase_features = phrase.get("features", {})
        if use_template_id_targets:
            p_note, reason = _build_template_target("Phrase", phrase_text, phrase_features, phrase_tam)
            if counters is not None:
                if p_note:
                    counters["template_targets_used"] += 1
                elif reason:
                    counters[f"template_filtered_{reason.lower()}"] += 1
        elif use_reference_templates:
            p_note = _build_reference_note(
                level="Phrase",
                node_text=phrase_text,
                features=phrase_features,
                tam_bucket=phrase_tam,
            )
        else:
            p_note = _extract_note_from_targets(phrase.get("targets", {}), counters=counters)
        if p_note:
            prompt = _render_phrase_prompt(
                sentence=sentence,
                phrase_text=phrase_text,
                pos_text=format_feature_list(phrase_features.get("pos", [])),
                dep_text=format_feature_list(phrase_features.get("dep", [])),
                tam_bucket=phrase_tam,
            )
            yield {
                "input": prompt,
                "target": p_note,
                "level": "Phrase",
                "tam_bucket": phrase_tam,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            }
            if counters is not None:
                counters["rows_emitted"] += 1

        for word in phrase.get("linguistic_elements", []):
            if word.get("type") != "Word":
                continue
            word_tam = _extract_tam_bucket(word)
            word_text = _node_input_text(word)
            word_features = word.get("features", {})
            if use_template_id_targets:
                w_note, reason = _build_template_target("Word", word_text, word_features, word_tam)
                if counters is not None:
                    if w_note:
                        counters["template_targets_used"] += 1
                    elif reason:
                        counters[f"template_filtered_{reason.lower()}"] += 1
            elif use_reference_templates:
                w_note = _build_reference_note(
                    level="Word",
                    node_text=word_text,
                    features=word_features,
                    tam_bucket=word_tam,
                )
            else:
                w_note = _extract_note_from_targets(word.get("targets", {}), counters=counters)
            if not w_note:
                continue
            prompt = _render_word_prompt(
                sentence=sentence,
                word_text=word_text,
                pos_text=(word_features.get("pos", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                tag_text=(word_features.get("tag", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                dep_text=(word_features.get("dep", ["UNKNOWN"]) or ["UNKNOWN"])[0],
                morph_text=format_feature_list(word_features.get("morph", [])),
                tam_bucket=word_tam,
            )
            yield {
                "input": prompt,
                "target": w_note,
                "level": "Word",
                "tam_bucket": word_tam,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            }
            if counters is not None:
                counters["rows_emitted"] += 1


def _iter_nodes(item: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield item
    for phrase in item.get("linguistic_elements", []):
        if not isinstance(phrase, dict):
            continue
        yield phrase
        for word in phrase.get("linguistic_elements", []):
            if isinstance(word, dict):
                yield word


def detect_dataset_schema(raw: List[Dict[str, Any]]) -> Dict[str, int | str]:
    nodes_total = 0
    with_notes_array = 0
    with_legacy_notes = 0
    with_targets = 0
    for item in raw:
        for node in _iter_nodes(item):
            nodes_total += 1
            targets = node.get("targets")
            if isinstance(targets, dict):
                with_targets += 1
                if isinstance(targets.get("notes"), list):
                    with_notes_array += 1
                if isinstance(targets.get("linguistic_notes"), str):
                    with_legacy_notes += 1

    schema = "unknown"
    if with_notes_array and with_legacy_notes:
        schema = "mixed"
    elif with_notes_array:
        schema = "new_notes_array"
    elif with_legacy_notes:
        schema = "legacy_linguistic_notes"
    return {
        "nodes_total": nodes_total,
        "nodes_with_targets": with_targets,
        "nodes_with_notes_array": with_notes_array,
        "nodes_with_legacy_linguistic_notes": with_legacy_notes,
        "detected_schema": schema,
    }


def dedup_and_cap_rows(
    rows: List[Dict[str, str]],
    *,
    max_per_target: int,
    dedup_exact_input_target: bool,
) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    capped: List[Dict[str, str]] = []
    target_counts: Dict[str, int] = defaultdict(int)
    seen_pairs = set()
    skipped_target_cap = 0
    skipped_exact_dup = 0

    for row in rows:
        target = row.get("target", "")
        key = _target_key(target)
        pair = (row.get("input", ""), key)
        if dedup_exact_input_target and pair in seen_pairs:
            skipped_exact_dup += 1
            continue
        if max_per_target > 0 and target_counts[key] >= max_per_target:
            skipped_target_cap += 1
            continue
        seen_pairs.add(pair)
        target_counts[key] += 1
        capped.append(row)

    return capped, {
        "skipped_exact_input_target_duplicates": skipped_exact_dup,
        "skipped_by_target_cap": skipped_target_cap,
    }


def _count_by(rows: List[Dict[str, str]], key_fn) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[key_fn(row)] += 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _count_level_tam(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        level = row.get("level", "Unknown")
        tam = row.get("tam_bucket", "none")
        matrix[level][tam] += 1
    return {
        level: dict(sorted(tam_counts.items(), key=lambda item: item[0]))
        for level, tam_counts in sorted(matrix.items(), key=lambda item: item[0])
    }


def balance_rows_by_level_tam(rows: List[Dict[str, str]], seed: int) -> List[Dict[str, str]]:
    rng = random.Random(seed)
    grouped: Dict[str, Dict[str, List[Dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row.get("level", "Unknown")][row.get("tam_bucket", "none")].append(row)

    balanced: List[Dict[str, str]] = []
    for level in sorted(grouped.keys()):
        buckets = grouped[level]
        if len(buckets) <= 1:
            for bucket_rows in buckets.values():
                balanced.extend(bucket_rows)
            continue

        target_size = min(len(bucket_rows) for bucket_rows in buckets.values())
        for bucket_name in sorted(buckets.keys()):
            bucket_rows = buckets[bucket_name]
            if len(bucket_rows) <= target_size:
                balanced.extend(bucket_rows)
            else:
                balanced.extend(rng.sample(bucket_rows, target_size))

    rng.shuffle(balanced)
    return balanced


def split_data(rows: List[Dict[str, str]], seed: int, dev_ratio: float, test_ratio: float):
    rng = random.Random(seed)
    data = rows[:]
    rng.shuffle(data)

    total = len(data)
    test_n = int(total * test_ratio)
    dev_n = int(total * dev_ratio)

    test = data[:test_n]
    dev = data[test_n : test_n + dev_n]
    train = data[test_n + dev_n :]
    return train, dev, test


def write_jsonl(rows: List[Dict[str, str]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _extract_template_id(target: str) -> str:
    if not isinstance(target, str):
        return "none"
    if "|" not in target:
        return "none"
    maybe_id = target.split("|", 1)[0].strip()
    if maybe_id in TEMPLATE_IDS:
        return maybe_id
    return "none"


def evaluate_quality_gates(
    *,
    target_stats_after_balance: Dict[str, Any],
    template_id_distribution_after_balance: Dict[str, int],
    min_unique_targets: int = 0,
    max_top1_share: float = 1.0,
    min_active_template_ids: int = 0,
) -> List[str]:
    failures: List[str] = []
    total = int(target_stats_after_balance.get("total", 0) or 0)
    unique_targets = int(target_stats_after_balance.get("unique_targets", 0) or 0)
    top = target_stats_after_balance.get("top_repeated_targets", []) or []
    top1_count = int(top[0].get("count", 0)) if top else 0
    top1_share = (top1_count / total) if total > 0 else 0.0
    active_template_ids = sum(
        1 for template_id, count in template_id_distribution_after_balance.items() if template_id != "none" and count > 0
    )

    if min_unique_targets > 0 and unique_targets < min_unique_targets:
        failures.append(f"min_unique_targets violated: {unique_targets} < {min_unique_targets}")
    if 0.0 <= max_top1_share < 1.0 and top1_share > max_top1_share:
        failures.append(f"max_top1_share violated: {top1_share:.6f} > {max_top1_share:.6f}")
    if min_active_template_ids > 0 and active_template_ids < min_active_template_ids:
        failures.append(f"min_active_template_ids violated: {active_template_ids} < {min_active_template_ids}")

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Build train/dev/test JSONL from hierarchical dataset")
    parser.add_argument("--input", default="linguistic_hierarchical_3000_v3.json")
    parser.add_argument("--output-dir", default="data/processed")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--max-per-target", type=int, default=120, help="Cap examples per normalized target; <=0 disables cap")
    parser.add_argument(
        "--dedup-exact-input-target",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Drop exact duplicate pairs of (input, normalized_target)",
    )
    parser.add_argument(
        "--balance-level-tam",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Balance examples by (level, tam_bucket) before train/dev/test split",
    )
    parser.add_argument(
        "--use-reference-templates",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Generate target notes from deterministic reference-backed templates instead of raw dataset notes.",
    )
    parser.add_argument(
        "--use-template-id-targets",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Generate target notes as `template_id|note` from fixed deterministic templates.",
    )
    parser.add_argument("--min-unique-targets", type=int, default=0, help="Fail build if unique targets after balance are below threshold.")
    parser.add_argument(
        "--max-top1-share",
        type=float,
        default=1.0,
        help="Fail build if top repeated target share after balance is above threshold (0..1).",
    )
    parser.add_argument(
        "--min-active-template-ids",
        type=int,
        default=0,
        help="Fail build if active template IDs after balance are below threshold.",
    )
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    schema_report = detect_dataset_schema(raw)
    quality_counters: Dict[str, int] = defaultdict(int)
    rows: List[Dict[str, str]] = []
    for item in raw:
        rows.extend(
            iter_examples(
                item,
                counters=quality_counters,
                use_reference_templates=bool(args.use_reference_templates),
                use_template_id_targets=bool(args.use_template_id_targets),
            )
        )
    rows_before_dedup = rows[:]
    rows, dedup_report = dedup_and_cap_rows(
        rows,
        max_per_target=args.max_per_target,
        dedup_exact_input_target=bool(args.dedup_exact_input_target),
    )
    rows_after_dedup = rows[:]
    if args.balance_level_tam:
        rows = balance_rows_by_level_tam(rows, seed=args.seed)
    rows_after_balance = rows[:]

    if not rows:
        raise SystemExit(
            "Dataset build produced 0 rows. "
            f"Schema={schema_report['detected_schema']} "
            f"nodes_with_notes_array={schema_report['nodes_with_notes_array']} "
            f"nodes_with_legacy_linguistic_notes={schema_report['nodes_with_legacy_linguistic_notes']}"
        )

    os.makedirs(args.output_dir, exist_ok=True)
    train, dev, test = split_data(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    write_jsonl(train, os.path.join(args.output_dir, "train.jsonl"))
    write_jsonl(dev, os.path.join(args.output_dir, "dev.jsonl"))
    write_jsonl(test, os.path.join(args.output_dir, "test.jsonl"))

    def _target_stats(rows_block: List[Dict[str, str]]) -> Dict[str, Any]:
        counts = defaultdict(int)
        for row in rows_block:
            counts[_target_key(row.get("target", ""))] += 1
        unique_count = len(counts)
        total_count = len(rows_block)
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:15]
        return {
            "total": total_count,
            "unique_targets": unique_count,
            "duplicate_ratio": round(1 - (unique_count / total_count), 6) if total_count else 0.0,
            "top_repeated_targets": [{"target": k, "count": v} for k, v in top],
        }

    stats = {
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "input_path": str(Path(args.input).resolve()),
        "use_reference_templates": bool(args.use_reference_templates),
        "use_template_id_targets": bool(args.use_template_id_targets),
        "schema_report": schema_report,
        "total_before_dedup": len(rows_before_dedup),
        "total_after_dedup": len(rows_after_dedup),
        "total_after_balance": len(rows_after_balance),
        "balance_level_tam": bool(args.balance_level_tam),
        "max_per_target": int(args.max_per_target),
        "dedup_exact_input_target": bool(args.dedup_exact_input_target),
        "dedup_report": dedup_report,
        "quality_counters": dict(sorted(quality_counters.items(), key=lambda kv: kv[0])),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "target_stats": {
            "before_dedup": _target_stats(rows_before_dedup),
            "after_dedup": _target_stats(rows_after_dedup),
            "after_balance": _target_stats(rows_after_balance),
        },
        "distributions": {
            "before_dedup": {
                "level": _count_by(rows_before_dedup, lambda row: row.get("level", "Unknown")),
                "tam_bucket": _count_by(rows_before_dedup, lambda row: row.get("tam_bucket", "none")),
                "template_id": _count_by(rows_before_dedup, lambda row: _extract_template_id(row.get("target", ""))),
                "level_tam": _count_level_tam(rows_before_dedup),
            },
            "after_dedup": {
                "level": _count_by(rows_after_dedup, lambda row: row.get("level", "Unknown")),
                "tam_bucket": _count_by(rows_after_dedup, lambda row: row.get("tam_bucket", "none")),
                "template_id": _count_by(rows_after_dedup, lambda row: _extract_template_id(row.get("target", ""))),
                "level_tam": _count_level_tam(rows_after_dedup),
            },
            "after_balance": {
                "level": _count_by(rows_after_balance, lambda row: row.get("level", "Unknown")),
                "tam_bucket": _count_by(rows_after_balance, lambda row: row.get("tam_bucket", "none")),
                "template_id": _count_by(rows_after_balance, lambda row: _extract_template_id(row.get("target", ""))),
                "level_tam": _count_level_tam(rows_after_balance),
            },
        },
    }

    quality_gate_failures = evaluate_quality_gates(
        target_stats_after_balance=stats["target_stats"]["after_balance"],
        template_id_distribution_after_balance=stats["distributions"]["after_balance"]["template_id"],
        min_unique_targets=int(args.min_unique_targets),
        max_top1_share=float(args.max_top1_share),
        min_active_template_ids=int(args.min_active_template_ids),
    )
    stats["quality_gates"] = {
        "min_unique_targets": int(args.min_unique_targets),
        "max_top1_share": float(args.max_top1_share),
        "min_active_template_ids": int(args.min_active_template_ids),
        "failures": quality_gate_failures,
        "passed": len(quality_gate_failures) == 0,
    }
    with open(os.path.join(args.output_dir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    if quality_gate_failures:
        raise SystemExit("Dataset quality gates failed: " + "; ".join(quality_gate_failures))

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
