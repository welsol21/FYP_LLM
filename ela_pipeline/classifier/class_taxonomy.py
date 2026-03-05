"""Canonical grammar-class taxonomy helpers."""

from __future__ import annotations


GRAMMAR_CLASS_ALIASES: dict[str, str] = {
    # Legacy/simple labels from phase1 datasets -> canonical pedagogical classes.
    "past_simple": "past_simple_affirmative",
    "present_perfect": "present_perfect_affirmative",
    "relative_clauses": "relative_clause",
    "prepositions_time": "preposition_linker",
    "prepositions_place": "preposition_linker",
    "articles_a_an_the": "article_determiner",
    "frequency_adverbs": "adverb_modifier",
    "comparative_adjectives": "adjective_modifier",
    "superlative_adjectives": "adjective_modifier",
    "countable_uncountable_nouns": "common_noun_lexeme",
    "there_is_are": "copular_clause",
    # Conjunction buckets are flattened to discourse-linking behavior.
    "coordinating_conjunctions": "adverb_modifier",
    "subordinating_conjunctions": "relative_clause",
}


def normalize_grammar_class_id(class_id: str | None) -> str:
    value = str(class_id or "").strip().lower()
    if not value:
        return ""
    return GRAMMAR_CLASS_ALIASES.get(value, value)

