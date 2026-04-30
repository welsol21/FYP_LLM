#!/usr/bin/env python3
"""Merge book-derived sentence pair sources and build balanced cycle-1 subsets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_INPUTS = (
    "data/processed_sentence_seed/oxford_peu_sentence_pairs_v2_clean_v2.jsonl",
    "data/processed_sentence_seed/cobuild_first_chapters_pairs_v1_clean.jsonl",
    "data/processed_sentence_seed/cobuild_grammar_chapters_pairs_v1_clean.jsonl",
    "data/processed_sentence_seed/cobuild_c04_tense_pairs_v1_clean.jsonl",
    "data/processed_sentence_seed/cobuild_c05_question_tag_pairs_v1.jsonl",
    "data/processed_sentence_seed/purdue_owl_curated_pairs_v1.jsonl",
    "data/processed_sentence_seed/perfect_english_grammar_curated_pairs_v1.jsonl",
    "data/processed_sentence_seed/peter_simon_targeted_pairs_v2_clean.jsonl",
    "data/processed_sentence_seed/dummies_chapter3_pairs_v2_clean.jsonl",
    "data/processed_sentence_seed/geraldine2010_targeted_pairs_v1_clean.jsonl",
    "data/processed_sentence_seed/dutwin_targeted_pairs_v1_clean.jsonl",
    "data/processed_sentence_seed/woods2017_ch6_perfect_pairs_v2_clean.jsonl",
)
CORE_TOPICS = (
    "conditional_sentences",
    "existential",
    "passive_voice",
    "perfect",
    "progressive",
    "question_tags",
    "relative_clauses",
)
EXPANDED_TOPICS = CORE_TOPICS + ("modal",)
EXPANDED_CAPS = {"modal": 60}

WS_RE = re.compile(r"\s+")
BAD_UTF_REPLACEMENTS = {
    "â": "'",
    "â": "'",
    "â": '"',
    "â": '"',
    "wiU": "will",
    "Yd": "I'd",
    "Vve": "I've",
}
META_CONTEXT_START_RE = re.compile(
    r"^(?:"
    r"full forms\b|negatives?\b|infinitives?\b|note that\b|what are\b|there can be used\b|"
    r"clauses?\b|both of these structures\b|explain and suggest\b|this sentence means\b|"
    r"in the first example\b|the progressive gives\b"
    r")",
    re.IGNORECASE,
)
PROGRESSIVE_CONTEXT_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being|will be|have been|has been|had been)\b(?:\s+\w+){0,2}\s+\w+ing\b",
    re.IGNORECASE,
)
PASSIVE_CONTEXT_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being|get|gets|got|have been|has been|had been|will be)\b"
    r"(?:\s+\w+){0,3}\s+\w+(?:ed|en|wn|lt|pt|nt|ft)\b",
    re.IGNORECASE,
)
PERFECT_CONTEXT_RE = re.compile(
    r"\b(?:have|has|had|will have|would have)\b(?:\s+\w+){0,2}\s+\w+(?:ed|en|wn|lt|pt|nt|ft)\b",
    re.IGNORECASE,
)
QUESTION_TAG_CONTEXT_RE = re.compile(
    r",\s*(?:am|is|are|was|were|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must)"
    r"(?:n't| not)?\s+(?:i|you|he|she|it|we|they|there)\?",
    re.IGNORECASE,
)
EXISTENTIAL_CONTEXT_RE = re.compile(
    r"(?:\bthere\s+(?:is|are|was|were|'s|will be|would be|could be|can be|might be|may be|must be|should be|"
    r"has been|have been|had been|to be|being|could have been|would have been|might have been)\b)"
    r"|(?:\b(?:is|are|was|were)\s+there\b)",
    re.IGNORECASE,
)
RELATIVE_CONTEXT_RE = re.compile(
    r"\b(?:who|which|that|whose|whom|where|when)\b",
    re.IGNORECASE,
)
REDUCED_RELATIVE_CONTEXT_RE = re.compile(
    r"\b(?:anyone|someone|somebody|everyone|everybody|people|person|things?|man|woman|half)\s+\w+ing\b",
    re.IGNORECASE,
)
RELATIVE_QUESTION_RE = re.compile(r"^(?:who|whom|what|which)\b.*\?$", re.IGNORECASE)
RELATIVE_META_CONTEXT_RE = re.compile(
    r"^(?:the relative pronoun\b|who was recovering\b|cannot stand alone\b|can stand alone\b)",
    re.IGNORECASE,
)
BAD_CONTEXT_FRAGMENT_RE = re.compile(r"\b(?:mucht|Warsaw,which|Thewoman|Areyou|theif-clause|whoanswered)\b|non­", re.IGNORECASE)
CONDITIONAL_CONTEXT_RE = re.compile(
    r"\bif\b|\bunless\b|\bprovided\b|\bsupposing\b|\bwould\b|\bshould\b",
    re.IGNORECASE,
)


def _norm(value: Any) -> str:
    return WS_RE.sub(" ", str(value or "").strip())


def _clean_text(text: str) -> str:
    cleaned = str(text or "")
    for src, dst in BAD_UTF_REPLACEMENTS.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = re.sub(r"\bI f\b", "If", cleaned)
    cleaned = re.sub(r"\bo f\b", "of", cleaned)
    cleaned = re.sub(r"([A-Za-z])from\b", r"\1 from", cleaned)
    cleaned = re.sub(r"\bUnde\b", "Uncle", cleaned)
    cleaned = re.sub(r"\bTU\b", "I'll", cleaned)
    cleaned = re.sub(r"\bYd\b", "I'd", cleaned)
    cleaned = cleaned.replace("mucht", "much")
    cleaned = re.sub(r"\s+([?.!,;:])", r"\1", cleaned)
    cleaned = re.sub(r"\b([A-Za-z]+)\s+’s\b", r"\1’s", cleaned)
    cleaned = re.sub(r"\b([A-Za-z]+)\s+'s\b", r"\1's", cleaned)
    cleaned = re.sub(r"([A-Za-z])\s+'s\b", r"\1's", cleaned)
    cleaned = re.sub(r"\bIt 's\b", "It's", cleaned)
    cleaned = re.sub(r"\bIt ’s\b", "It’s", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return _norm(cleaned)


def _clean_notation_text(topic_key: str, notation_text: str) -> str:
    text = _clean_text(notation_text)
    if topic_key == "question_tags":
        if "What are question tags?" in text:
            return "Question tags are short questions added at the end of a statement, especially in speech and informal writing."
        if "meaning and intonation" in text:
            return "In speech, intonation helps show the exact meaning of a question tag."
        if text.startswith("5.16 Question tags are formed"):
            return "Question tags are formed with an auxiliary or form of be/do plus a pronoun referring to the subject."
        if text.startswith("5.104 Modals are used in question tags."):
            return "Question tags use a matching modal auxiliary and pronoun."
        if "Subject-auxiliary inversion in question tags" in text:
            return "Question tags are added after a statement to keep the flow of conversation."
        if text.startswith("In sentences with question tags, it is quite common to leave out pronoun subjects and auxiliary verbs."):
            return "Question tags can also be used for reactions, challenges, or checking an assumption."
    if topic_key == "relative_clauses":
        if "Whose is a possessive relative pronoun" in text:
            return "Relative clauses can identify a noun or add extra information about it."
        if "Clauses used like this are called" in text:
            return "Clauses used like this are called relative clauses."
        if "A participle is often used instead of a relative pronoun and full verb." in text:
            return "A participle can sometimes replace a relative pronoun and full verb in a reduced relative clause."
        if text.startswith("One way to do this is to use a relative clause."):
            return "A relative clause adds information about a noun immediately after it."
        if "The difference between defining and non-defining relative clauses" in text:
            return "A relative clause can be defining or non-defining depending on whether it identifies the noun or adds extra information."
        if text.startswith("What is a relative clause?"):
            return "Relative clauses refer back to a noun and are often introduced by who, whom, whose, which, or that."
        if text.startswith("somebody I know you'll like"):
            return "Relative clauses can combine with other clause patterns, such as reporting structures."
        if text.startswith("8.114 Nominal relative clauses that begin with where"):
            return "Nominal relative clauses beginning with where can follow a preposition or the verb be."
        if text.startswith("The main clause is always the one that can stand alone"):
            return "Relative pronouns can introduce a clause that adds information about a noun."
        if text.startswith("Once again, some pronouns can be used as subjects"):
            return "Relative pronouns such as who, whom, that, and which help connect a clause to a noun."
    if topic_key == "existential":
        if "There can be used in this way with all tenses of be." in text:
            return "Existential there can be used with different tenses of be."
        if "There's ice on the lake." in text:
            return "We often use existential there to say that something exists or is present somewhere."
        if text.startswith("9.47 The noun phrase is usually followed"):
            return "In existential there sentences, the noun phrase is often followed by a place phrase, complement, or clause."
    if topic_key == "passive_voice":
        if "Both of these structures can be made passive." in text:
            return "Some verbs with two objects can form two different passive structures."
        if text.startswith("Explain and suggest cannot be used in structure A."):
            return "Some verbs with two objects can form two different passive structures."
        if text.startswith("9.3 One way of changing word order"):
            return "The passive changes word order to focus on the affected person or thing."
        if text.startswith("9.18 Because of their meaning, some transitive verbs are usually used in the passive."):
            return "Some transitive verbs are commonly used in the passive."
        if "passive structures are often possible with preparatory it" in text:
            return "Passive structures are often possible with preparatory it."
        if text.startswith("In most cases, these structures can be made passive."):
            return "Many object-plus-infinitive structures can be made passive."
        if text.startswith("The difference between the active and passive voice"):
            return "In the passive voice, the subject receives the action."
    if topic_key == "progressive":
        if "The progressive gives you slightly more of a sense of being in the middle of things." in text:
            return "The future progressive emphasizes an action in progress at a future time."
        if "The difference between the plain past tense and the past progressive tense" in text:
            return "The past progressive can show an action in progress at a specific time in the past."
        if "This sentence means that right now" in text:
            return "The present progressive can describe an action happening right now."
        if "Now find the verbs and sort them into present progressive" in text:
            return "Progressive forms use be with an -ing verb."
        if text.startswith("4.19 You also use the present progressive"):
            return "The present progressive can describe changes, trends, development, and progress."
        if text.startswith("4.17 If you want to talk about an activity"):
            return "The present progressive describes an activity that is in progress at the moment of speaking."
        if text.startswith("4.18 If you want to emphasize the present moment"):
            return "The present progressive can emphasize the present moment or a temporary situation."
        if text.startswith("4.31 If you want to focus on action in progress"):
            return "The past progressive describes an action in progress or repeated actions in the past."
        if text.startswith("4.32 If you want to contrast a situation"):
            return "The past progressive can provide background for an event that happened afterwards."
    if topic_key == "perfect":
        if "The present perfect is often used to express the idea of completion or achievement." in text:
            return "The present perfect often expresses completion or achievement with present relevance."
        if text.startswith("We can use the present perfect to say that something has happened several times up to the present."):
            return "The present perfect can describe things that have happened repeatedly up to the present."
        if text.startswith("It's important to add one other verb formation to this list"):
            return "The present perfect links a past action or state to the present."
        if text.startswith("The present perfect tense is used for past events when the exact time is not mentioned"):
            return "The present perfect is used for past events when the exact time is not mentioned."
        if "The two present perfect forms show actions or states of being that began in the past" in text:
            return "The present perfect links a past action or state to the present."
        if "Here are a couple of examples of the past perfect tense" in text:
            return "The past perfect shows an earlier action before another past action."
        if "First, take a look at the plain version of the future perfect" in text:
            return "The future perfect shows an action completed before another future point."
        if text.startswith("When we talk about longer-lasting or permanent situations"):
            return "For longer-lasting or permanent situations, English often prefers the simple present perfect."
        if text.startswith("4.33 If you want to mention something that happened in the past"):
            return "The present perfect can describe a past event without stating a specific past time."
        if text.startswith("4.47 Note that if you are talking about a quality, attitude, or possession"):
            return "The present perfect with a duration expression can describe a state that still exists."
        if text.startswith("4.50 If you are using the past perfect to talk about a situation"):
            return "The past perfect can combine with a duration expression to show how long an earlier past situation lasted."
        if text.startswith("4.51 If you are using the past perfect progressive"):
            return "The past perfect progressive can show a recent continuous activity before a past time."
    if topic_key == "conditional_sentences":
        if "We often use were instead of was after if" in text:
            return "After if, were is often used instead of was in more formal or traditional usage."
        if text.startswith("In theif-clause, we use the past perfect subjunctive"):
            return "In third conditionals, the if-clause uses the past perfect."
        if text.startswith("Would can be used to make a request even more polite."):
            return "Conditional patterns can use should, were to, or stressed will for more marked meanings."
    return text


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


def _source_name(path: str) -> str:
    lowered = path.lower()
    if "oxford" in lowered:
        return "oxford_peu"
    if "peter_simon" in lowered or "grammaring" in lowered:
        return "peter_simon"
    if "dummies_chapter3" in lowered or "geraldine2010" in lowered or "geraldine woods" in lowered:
        return "geraldine_dummies"
    if "cobuild_c04" in lowered:
        return "cobuild_c04"
    if "cobuild_c05" in lowered:
        return "cobuild_c05"
    if "purdue_owl" in lowered:
        return "purdue_owl"
    if "perfect_english_grammar" in lowered:
        return "perfect_english_grammar"
    if "cobuild_grammar_chapters" in lowered:
        return "cobuild_grammar_chapters"
    if "cobuild_first_chapters" in lowered:
        return "cobuild_first_chapters"
    if "collins cobuild english grammar" in lowered:
        return "cobuild"
    return Path(path).stem


def _stable_id(topic_key: str, notation_text: str, context_text: str) -> str:
    normalized_context = _norm(context_text).lower().rstrip(".!?")
    payload = f"{_norm(topic_key).lower()}|||{_norm(notation_text).lower()}|||{normalized_context}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _topic_row_ok(row: dict[str, Any]) -> bool:
    topic_key = _norm(row.get("topic_key"))
    context_text = _norm(row.get("context_text"))
    if META_CONTEXT_START_RE.search(context_text):
        return False
    if "*" in context_text:
        return False
    if "/" in context_text:
        return False
    if BAD_CONTEXT_FRAGMENT_RE.search(context_text):
        return False
    if not context_text.endswith((".", "!", "?")):
        return False
    if len(context_text.split()) < 3:
        return False
    if topic_key == "progressive":
        return bool(PROGRESSIVE_CONTEXT_RE.search(context_text))
    if topic_key == "passive_voice":
        if context_text.startswith(("We chose ", "It provides the theme", "With the passive voice")):
            return False
        return bool(PASSIVE_CONTEXT_RE.search(context_text))
    if topic_key == "perfect":
        return bool(PERFECT_CONTEXT_RE.search(context_text))
    if topic_key == "question_tags":
        return bool(QUESTION_TAG_CONTEXT_RE.search(context_text))
    if topic_key == "existential":
        return bool(EXISTENTIAL_CONTEXT_RE.search(context_text))
    if topic_key == "relative_clauses":
        if RELATIVE_QUESTION_RE.search(context_text):
            return False
        if RELATIVE_META_CONTEXT_RE.search(context_text):
            return False
        if "Who is correct because" in context_text or "Where means the place where" in context_text:
            return False
        if context_text.startswith("I didn't know who "):
            return False
        return bool(RELATIVE_CONTEXT_RE.search(context_text) or REDUCED_RELATIVE_CONTEXT_RE.search(context_text))
    if topic_key == "conditional_sentences":
        if len(context_text.split()) < 5:
            return False
        return bool(CONDITIONAL_CONTEXT_RE.search(context_text))
    return True


def merge_rows(inputs: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    source_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()
    dropped_topic_qc: Counter[str] = Counter()

    for input_path in inputs:
        source_name = _source_name(input_path)
        for row in _iter_jsonl(input_path):
            topic_key = _norm(row.get("topic_key"))
            notation_text = _clean_notation_text(topic_key, _norm(row.get("notation_text")))
            context_text = _clean_text(_norm(row.get("context_text")))
            heading = _norm(row.get("heading") or row.get("entry_head"))
            if not topic_key or not notation_text or not context_text:
                continue
            built = {
                "id": _stable_id(topic_key, notation_text, context_text),
                "source_name": source_name,
                "source_path": row.get("source_path"),
                "topic_key": topic_key,
                "notation_text": notation_text,
                "context_text": context_text,
                "heading": heading,
                "pair_method": row.get("pair_method"),
            }
            if not _topic_row_ok(built):
                dropped_topic_qc[topic_key] += 1
                continue
            key = (topic_key.lower(), notation_text.lower(), context_text.lower().rstrip(".!?"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(built)
            source_counts[source_name] += 1
            topic_counts[topic_key] += 1

    merged.sort(key=lambda row: (_norm(row.get("topic_key")), _norm(row.get("heading")), _norm(row.get("context_text"))))
    report = {
        "pipeline_version": "book_sentence_pair_pool_v2",
        "inputs": list(inputs),
        "rows_total": len(merged),
        "source_counts": dict(source_counts),
        "topic_counts": dict(topic_counts),
        "unique_notes": len({_norm(row.get("notation_text")).lower() for row in merged}),
        "unique_contexts": len({_norm(row.get("context_text")).lower() for row in merged}),
        "dropped_topic_qc": dict(dropped_topic_qc),
    }
    return merged, report


def build_subset(rows: list[dict[str, Any]], *, topics: tuple[str, ...], caps: dict[str, int] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    caps = caps or {}
    kept: list[dict[str, Any]] = []
    topic_counts: Counter[str] = Counter()
    for row in rows:
        topic_key = _norm(row.get("topic_key"))
        if topic_key not in topics:
            continue
        if topic_key in caps and topic_counts[topic_key] >= caps[topic_key]:
            continue
        kept.append(row)
        topic_counts[topic_key] += 1
    report = {
        "rows_total": len(kept),
        "topic_counts": dict(topic_counts),
        "unique_notes": len({_norm(row.get("notation_text")).lower() for row in kept}),
        "unique_contexts": len({_norm(row.get("context_text")).lower() for row in kept}),
        "caps": caps,
    }
    return kept, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge sentence pair sources and build balanced cycle-1 subsets.")
    parser.add_argument("--inputs", nargs="*", default=list(DEFAULT_INPUTS))
    parser.add_argument("--pool-jsonl", required=True)
    parser.add_argument("--pool-report-json", required=True)
    parser.add_argument("--core-jsonl", required=True)
    parser.add_argument("--core-report-json", required=True)
    parser.add_argument("--expanded-jsonl", required=True)
    parser.add_argument("--expanded-report-json", required=True)
    args = parser.parse_args()

    merged, pool_report = merge_rows(tuple(args.inputs))
    core_rows, core_report = build_subset(merged, topics=CORE_TOPICS)
    expanded_rows, expanded_report = build_subset(merged, topics=EXPANDED_TOPICS, caps=EXPANDED_CAPS)

    _write_jsonl(args.pool_jsonl, merged)
    _write_json(args.pool_report_json, pool_report)
    _write_jsonl(args.core_jsonl, core_rows)
    _write_json(args.core_report_json, core_report)
    _write_jsonl(args.expanded_jsonl, expanded_rows)
    _write_json(args.expanded_report_json, expanded_report)
    print(
        json.dumps(
            {
                "pool": pool_report,
                "core": core_report,
                "expanded": expanded_report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
