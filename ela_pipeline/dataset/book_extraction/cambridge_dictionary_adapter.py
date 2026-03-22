"""Configured rulebook adapter for The Cambridge Dictionary of English Grammar."""

from __future__ import annotations

from .engine import BookTextPayload
from .rulebook_adapter import RulebookAdapterConfig, RulebookRow, extract_rulebook_rows


CAMBRIDGE_DICTIONARY_CONFIG = RulebookAdapterConfig(
    name="cambridge_dictionary_of_english_grammar",
    source_markers=(
        "the cambridge dictionary of english grammar",
        "pam peters",
    ),
    front_matter_sections=(
        ("How to use this book", "usage_rule"),
        ("Introduction", "introduction_rule"),
    ),
    body_start_heading="A",
)


def extract_cambridge_dictionary_rows(payload: BookTextPayload) -> list[RulebookRow]:
    return extract_rulebook_rows(payload, CAMBRIDGE_DICTIONARY_CONFIG)
