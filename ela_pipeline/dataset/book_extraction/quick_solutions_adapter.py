"""Configured rulebook adapter for Quick Solutions to Common Errors in English."""

from __future__ import annotations

from .engine import BookTextPayload
from .rulebook_adapter import RulebookAdapterConfig, RulebookRow, extract_rulebook_rows


QUICK_SOLUTIONS_CONFIG = RulebookAdapterConfig(
    name="quick_solutions_common_errors",
    source_markers=(
        "quick solutions to common errors in english",
        "angela burt",
        "how to use this book",
    ),
    front_matter_sections=(
        ("How to use this book", "usage_rule"),
    ),
    body_start_heading="abbreviations",
)


def extract_quick_solutions_rows(payload: BookTextPayload) -> list[RulebookRow]:
    return extract_rulebook_rows(payload, QUICK_SOLUTIONS_CONFIG)
