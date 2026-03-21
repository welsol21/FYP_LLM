"""Configured handbook adapter for Introducing English Grammar (2010)."""

from __future__ import annotations

from .engine import BookTextPayload
from .handbook_adapter import HandbookAdapterConfig, HandbookRow, extract_handbook_rows


INTRODUCING_ENGLISH_GRAMMAR_CONFIG = HandbookAdapterConfig(
    name="introducing_english_grammar_2010",
    source_markers=(
        "introducing english grammar",
        "kersti börjars",
        "kate burridge",
    ),
    topic_patterns={
        "sentence_types": (
            "different sentence types",
            "declaratives",
            "interrogatives",
            "imperatives",
            "exclamatives",
        ),
        "modal": (
            "auxiliary verbs",
            "modal verbs",
            "auxiliary have, be and do",
        ),
        "noun_phrases": (
            "the noun phrase",
            "how to spot a noun phrase",
            "determiners",
            "post-modifiers",
            "complements",
        ),
        "relative_clauses": (
            "relative clauses",
            "relative clause",
        ),
        "that_clause": (
            "that-clauses",
            "that-clause",
            "finite sub-clauses",
        ),
        "non_finite_clauses": (
            "non-finite clauses",
            "subjectless clauses",
        ),
        "passive_voice": (
            "passive",
        ),
        "prepositions": (
            "preposition",
            "prepositions",
        ),
    },
    max_follow_blocks=3,
    min_start_line=7000,
    require_example_signal=False,
    max_block_chars=3600,
    topic_min_start_lines={
        "sentence_types": 7600,
        "modal": 9000,
        "noun_phrases": 11600,
        "relative_clauses": 157000,
        "that_clause": 460000,
        "non_finite_clauses": 13300,
        "passive_voice": 160000,
        "prepositions": 29000,
    },
)


def extract_introducing_english_grammar_rows(payload: BookTextPayload) -> list[HandbookRow]:
    rows = extract_handbook_rows(payload, INTRODUCING_ENGLISH_GRAMMAR_CONFIG)
    return [row for row in rows if int(row.start_line or 0) < 13550]
