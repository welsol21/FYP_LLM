"""Configured handbook adapter for Mysteries of English Grammar (2022)."""

from __future__ import annotations

from .engine import BookTextPayload
from .handbook_adapter import HandbookAdapterConfig, HandbookRow, extract_handbook_rows


MYSTERIES_ENGLISH_GRAMMAR_CONFIG = HandbookAdapterConfig(
    name="mysteries_english_grammar_2022",
    source_markers=(
        "mysteries of english grammar",
        "andreea s. calude",
        "laurie bauer",
    ),
    topic_patterns={
        "prepositions": (
            "prepositions",
            "preposition",
            "preposition stranding",
        ),
        "double_negatives": (
            "double negatives",
            "double negative",
        ),
        "definite_article": (
            "definite article",
        ),
        "countability": (
            "countability",
            "count nouns",
            "mass nouns",
        ),
        "perfect": (
            "present perfect",
            "the present perfect",
        ),
        "comparatives": (
            "comparatives and superlatives",
            "comparison",
            "comparative",
            "superlative",
        ),
        "progressive": (
            "the progressive",
            "progressive aspect",
        ),
        "adjectives": (
            "adjectives",
            "gradable adjectives",
        ),
        "double_be": (
            "double be construction",
            "double be",
        ),
        "gender": (
            "gender and related matters",
            "gender",
        ),
        "shadow_pronouns": (
            "shadow pronouns",
            "shadow pronoun",
        ),
        "number_agreement": (
            "number agreement",
            "agreement",
        ),
        "insubordinate_clauses": (
            "insubordinate clauses",
            "insubordinate clause",
        ),
        "pronominal_case": (
            "pronominal case",
            "pronoun case",
        ),
        "possession": (
            "possession",
            "possessive",
            "possessives",
        ),
    },
    max_follow_blocks=3,
    min_start_line=1100,
    require_example_signal=False,
    max_block_chars=4200,
    topic_min_start_lines={
        "prepositions": 1150,
        "double_negatives": 1560,
        "definite_article": 1860,
        "countability": 2175,
        "perfect": 2540,
        "comparatives": 3000,
        "progressive": 3445,
        "adjectives": 3885,
        "double_be": 4445,
        "gender": 4870,
        "shadow_pronouns": 5465,
        "number_agreement": 5800,
        "insubordinate_clauses": 6219,
        "pronominal_case": 6707,
        "possession": 7270,
    },
)


def extract_mysteries_english_grammar_rows(payload: BookTextPayload) -> list[HandbookRow]:
    rows = extract_handbook_rows(payload, MYSTERIES_ENGLISH_GRAMMAR_CONFIG)
    return [row for row in rows if int(row.start_line or 0) < 7800]
