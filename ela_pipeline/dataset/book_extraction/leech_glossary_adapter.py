"""Configured rulebook adapter for Leech's A Glossary of English Grammar."""

from __future__ import annotations

from .engine import BookTextPayload
from .rulebook_adapter import RulebookAdapterConfig, RulebookRow, extract_rulebook_rows


LEECH_GLOSSARY_CONFIG = RulebookAdapterConfig(
    name="leech_glossary_of_english_grammar",
    source_markers=(
        "a glossary of english grammar",
        "glossaries in linguistics",
        "geoffrey leech",
    ),
    front_matter_sections=(
        ("Use of special symbols", "notational_rule"),
        ("Introduction", "introduction_rule"),
    ),
    body_start_heading="A",
)


def extract_leech_glossary_rows(payload: BookTextPayload) -> list[RulebookRow]:
    return extract_rulebook_rows(payload, LEECH_GLOSSARY_CONFIG)
