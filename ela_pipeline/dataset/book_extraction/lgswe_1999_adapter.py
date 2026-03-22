"""Configured handbook adapter for Longman Grammar of Spoken and Written English (1999)."""

from __future__ import annotations

from .engine import BookTextPayload
from .handbook_adapter import HandbookAdapterConfig, HandbookRow, extract_handbook_rows


LGSWE_1999_CONFIG = HandbookAdapterConfig(
    name="longman_grammar_spoken_written_english_1999",
    source_markers=(
        "longman grammar of spoken and written english",
        "lgswe",
        "longman_grammar",
    ),
    topic_patterns={
        "question_tags": (
            "question tags",
            "question tag",
        ),
        "modal": (
            "modal auxiliaries",
            "modal auxiliary",
            "modals and semi-modals",
        ),
        "prepositions": (
            "prepositions",
            "free v. bound prepositions",
            "complex prepositions",
        ),
        "prepositional_phrases": (
            "prepositional phrases",
            "extended prepositional phrases",
            "syntactic roles of prepositional phrases",
        ),
        "conditional_sentences": (
            "conditional clauses",
            "conditional clause",
            "conditional sentences",
        ),
        "relative_clauses": (
            "relative clauses",
            "relative clause",
        ),
        "that_clause": (
            "that-clauses",
            "that-clause",
            "head nouns taking that-clauses",
            "that complement clauses",
        ),
        "passive_voice": (
            "the passive",
            "passives",
            "passive voice",
            "passives across syntactic positions",
        ),
    },
    max_follow_blocks=3,
    min_start_line=7000,
    require_example_signal=False,
    max_block_chars=3800,
    topic_min_start_lines={
        "modal": 7700,
        "prepositions": 7700,
        "prepositional_phrases": 9500,
        "question_tags": 11700,
        "passive_voice": 12900,
        "conditional_sentences": 14500,
        "relative_clauses": 15600,
        "that_clause": 48300,
    },
)

# Stop before the index/appendix section (last ~10K lines)
_BODY_END_LINE = 80000


def extract_lgswe_1999_rows(payload: BookTextPayload) -> list[HandbookRow]:
    rows = extract_handbook_rows(payload, LGSWE_1999_CONFIG)
    return [row for row in rows if int(row.start_line or 0) < _BODY_END_LINE]
