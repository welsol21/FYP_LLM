"""Configured rulebook adapter for The Oxford Dictionary of English Grammar."""

from __future__ import annotations

from .engine import BookTextPayload
from .rulebook_adapter import RulebookAdapterConfig, RulebookRow, extract_rulebook_rows


OXFORD_DICTIONARY_CONFIG = RulebookAdapterConfig(
    name="oxford_dictionary_of_english_grammar",
    source_markers=(
        "the oxford dictionary of english grammar",
        "oxford quick reference",
    ),
    front_matter_sections=(
        ("Organization", "organization_rule"),
        ("Notational Conventions", "notational_rule"),
        ("Abbreviations", "abbreviation_rule"),
    ),
    body_start_heading="A",
)


def extract_oxford_dictionary_rows(payload: BookTextPayload) -> list[RulebookRow]:
    return extract_rulebook_rows(payload, OXFORD_DICTIONARY_CONFIG)
