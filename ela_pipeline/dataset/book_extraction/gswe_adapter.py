"""Configured handbook adapter for Grammar of Spoken and Written English (2021)."""

from __future__ import annotations

from .engine import BookTextPayload
from .handbook_adapter import HandbookAdapterConfig, HandbookRow, extract_handbook_rows


GSWE_CONFIG = HandbookAdapterConfig(
    name="grammar_of_spoken_and_written_english_2021",
    source_markers=(
        "grammar of spoken and written english",
        "gswe",
    ),
    topic_patterns={
        "question_tags": (
            "question tags",
            "question tag",
        ),
        "modal": (
            "modal auxiliaries",
            "modal auxiliary",
            "modal verbs",
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
        ),
        "relative_clauses": (
            "relative clauses",
            "relative clause",
        ),
        "that_clause": (
            "that-clauses",
            "that-clause",
            "head nouns taking that-clauses",
        ),
        "passive_voice": (
            "passives across syntactic positions and registers",
            "passives",
            "passive voice",
        ),
        "progressive": (
            "progressive aspect:",
            "progressive aspect",
        ),
        "perfect": (
            "perfect aspect",
            "perfect aspect:",
        ),
        "noun_phrase": (
            "noun phrases",
        ),
        "verb_phrase": (
            "verb phrases",
        ),
    },
    max_follow_blocks=3,
    min_start_line=5900,
    require_example_signal=False,
    max_block_chars=3800,
    topic_min_start_lines={
        "modal": 5960,
        "prepositions": 5990,
        "prepositional_phrases": 8090,
        "noun_phrase": 7600,
        "verb_phrase": 7800,
        "relative_clauses": 14640,
        "question_tags": 15539,
        "progressive": 32700,
        "perfect": 35200,
        "that_clause": 48047,
        "passive_voice": 68261,
        "conditional_sentences": 60610,
    },
)

_SUPPLEMENT_START_LINE = 81780


def extract_gswe_rows(payload: BookTextPayload) -> list[HandbookRow]:
    rows = extract_handbook_rows(payload, GSWE_CONFIG)
    return [row for row in rows if int(row.start_line or 0) < _SUPPLEMENT_START_LINE]
