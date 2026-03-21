"""Configured handbook adapter for COBUILD English Grammar (2017)."""

from __future__ import annotations

from .engine import BookTextPayload
from .handbook_adapter import HandbookAdapterConfig, HandbookRow, extract_handbook_rows


COBUILD_GRAMMAR_CONFIG = HandbookAdapterConfig(
    name="cobuild_english_grammar_2017",
    source_markers=(
        "cobuild english grammar",
        "collins cobuild grammar",
    ),
    topic_patterns={
        "question_tags": ("question tags",),
        "modal": ("using modals", "modal verbs", "semi-modals"),
        "prepositions": ("prepositions", "prepositions used with verbs", "prepositional phrases"),
        "prepositional_phrases": ("prepositional phrases", "prepositions used with verbs"),
        "conditional_sentences": ("conditional clauses", "if ", "unless "),
        "relative_clauses": ("relative clauses",),
        "that_clause": ("nominal that-clauses", "that-clauses"),
        "passive_voice": ("the passive", "passive"),
    },
    max_follow_blocks=3,
    min_start_line=21000,
    require_example_signal=False,
    max_block_chars=3200,
    topic_min_start_lines={
        "modal": 21900,
        "question_tags": 22350,
        "prepositions": 25900,
        "prepositional_phrases": 25900,
        "conditional_sentences": 31800,
        "relative_clauses": 32800,
        "that_clause": 33350,
        "passive_voice": 34800,
    },
)

_SUPPLEMENT_START_LINE = 42549


def extract_cobuild_grammar_rows(payload: BookTextPayload) -> list[HandbookRow]:
    rows = extract_handbook_rows(payload, COBUILD_GRAMMAR_CONFIG)
    return [row for row in rows if int(row.start_line or 0) < _SUPPLEMENT_START_LINE]
