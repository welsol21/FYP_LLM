"""Configured handbook adapter for Collins COBUILD English Grammar (2011)."""

from __future__ import annotations

from .engine import BookTextPayload
from .handbook_adapter import HandbookAdapterConfig, HandbookRow, extract_handbook_rows


COLLINS_COBUILD_2011_CONFIG = HandbookAdapterConfig(
    name="collins_cobuild_english_grammar_2011",
    source_markers=(
        "collins cobuild english grammar",
        "cobuild english grammar - 2011",
    ),
    topic_patterns={
        "question_tags": (
            "making a statement into a question: question tags",
            "question tags",
        ),
        "modal": (
            "using modals",
            "modal verbs",
            "modal auxiliaries",
        ),
        "prepositions": (
            "prepositions",
            "preposition",
        ),
        "prepositional_phrases": (
            "prepositional phrases",
        ),
        "conditional_sentences": (
            "conditional clauses",
            "if-clause",
            "if-clauses",
            "conditionals",
        ),
        "relative_clauses": (
            "relative clauses",
            "defining relative clause",
            "non-defining relative clause",
        ),
        "that_clause": (
            "nominal that-clauses",
            "that-clauses",
        ),
        "passive_voice": (
            "focusing on the thing affected: the passive",
            "using the passive",
            "the passive",
        ),
        "progressive": (
            "the present progressive",
            "actions in progress in the past: the past progressive",
            "past progressive",
            "future progressive",
        ),
        "perfect": (
            "the past in relation to the present: the present perfect",
            "present perfect",
            "past perfect",
            "future perfect",
        ),
        "noun_phrase": (
            "noun phrases",
        ),
        "verb_phrase": (
            "verb phrases",
        ),
    },
    max_follow_blocks=3,
    min_start_line=17000,
    require_example_signal=False,
    max_block_chars=3600,
    topic_min_start_lines={
        "progressive": 17300,
        "perfect": 17500,
        "question_tags": 19530,
        "modal": 20700,
        "prepositional_phrases": 22040,
        "prepositions": 23790,
        "conditional_sentences": 27480,
        "relative_clauses": 28170,
        "that_clause": 28580,
        "passive_voice": 29770,
        "noun_phrase": 34700,
        "verb_phrase": 34700,
    },
)

_SUPPLEMENT_START_LINE = 37656


def extract_collins_cobuild_2011_rows(payload: BookTextPayload) -> list[HandbookRow]:
    rows = extract_handbook_rows(payload, COLLINS_COBUILD_2011_CONFIG)
    return [row for row in rows if int(row.start_line or 0) < _SUPPLEMENT_START_LINE]
