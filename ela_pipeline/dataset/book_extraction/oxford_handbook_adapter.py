"""Configured handbook adapter for The Oxford Handbook of English Grammar."""

from __future__ import annotations

from .engine import BookTextPayload
from .handbook_adapter import HandbookAdapterConfig, HandbookRow, extract_handbook_rows


OXFORD_HANDBOOK_CONFIG = HandbookAdapterConfig(
    name="oxford_handbook_of_english_grammar",
    source_markers=(
        "the oxford handbook of english grammar",
        "oxford handbooks in linguistics",
    ),
    topic_patterns={
        "question_tags": ("question tags", "question tag", "tag question", "tag questions"),
        "relative_clauses": ("relative clauses", "relative clause"),
        "prepositional_phrases": ("prepositional phrases", "prepositional phrase"),
        "prepositions": ("prepositions", "preposition"),
        "passive_voice": ("passive voice", "passive sentence", "active-passive", "active–passive", "passive"),
        "that_clause": ("that-clause", "that clause"),
        "wh_clause": ("wh-clause", "wh clause"),
        "conditional_sentences": ("conditional sentence", "conditional sentences", "conditionals", "if-clause", "if clause"),
        "modal": ("modal auxiliaries", "modal auxiliary", "modal verbs", "auxiliary modals"),
        "perfect": ("perfect aspect", "present perfect", "past perfect", "perfect forms"),
        "progressive": ("progressive aspect", "progressive forms", "progressive construction"),
    },
    max_follow_blocks=3,
    min_start_line=14500,
    require_example_signal=True,
    max_block_chars=3200,
    topic_min_start_lines={
        "prepositions": 16900,
        "prepositional_phrases": 16900,
        "conditional_sentences": 17600,
        "question_tags": 20500,
        "perfect": 20900,
        "progressive": 21900,
        "modal": 22000,
        "that_clause": 17500,
        "relative_clauses": 20000,
        "wh_clause": 20000,
    },
)


def extract_oxford_handbook_rows(payload: BookTextPayload) -> list[HandbookRow]:
    return extract_handbook_rows(payload, OXFORD_HANDBOOK_CONFIG)
