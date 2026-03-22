"""WordNet lexical definition lookup for word-level notes.

Provides get_wordnet_note() which returns level-differentiated notes for a
content word based on its lemma and part-of-speech.

Integration contract:
- Used as a fallback when build_note_blueprints() returns {} (no grammar_classes).
- Only applies to content words (noun, verb, adjective, adverb).
- Skips auxiliary verbs, modal auxiliaries, and pure function words.
- Skips words already covered by a parent phrase-level grammar note.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Default path relative to repo root; override via ELA_WORDNET_DEFINITIONS env var.
_DEFAULT_PATH = Path(__file__).parent.parent.parent / "data" / "wordnet" / "wordnet_definitions.jsonl"

# spaCy POS tags → WordNet POS codes
_SPACY_TO_WN_POS: dict[str, str] = {
    "noun": "n",
    "proper noun": "n",
    "verb": "v",
    "adjective": "a",
    "adverb": "r",
}

# Grammatical roles where this word acts as a structural auxiliary;
# we give a short note pointing to the enclosing phrase rather than a lexical one.
_AUXILIARY_ROLES = {"auxiliary", "cop"}

# Surface-form/lemma list of auxiliaries and function words to skip
_SKIP_LEMMAS = {
    "be", "is", "am", "are", "was", "were", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did",
    "will", "would", "shall", "should", "can", "could",
    "may", "might", "must", "ought", "need", "dare",
    "get", "a", "an", "the", "to", "of", "in", "on", "at",
    "and", "or", "but", "not", "no", "so", "yet", "for",
    "that", "this", "it", "its",
}


@lru_cache(maxsize=1)
def _load_index() -> dict[tuple[str, str], dict]:
    """Load the WordNet definitions JSONL into a (lemma, pos) → entry dict."""
    path = Path(os.environ.get("ELA_WORDNET_DEFINITIONS", "") or _DEFAULT_PATH)
    if not path.exists():
        return {}
    index: dict[tuple[str, str], dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                key = (str(entry.get("lemma", "")), str(entry.get("pos", "")))
                index[key] = entry
            except (json.JSONDecodeError, KeyError):
                pass
    return index


def _make_notes(entry: dict, surface: str) -> dict[str, str]:
    """Build elementary / intermediate / advanced notes from a WordNet entry."""
    primary_def = entry.get("primary_definition", "")
    examples = entry.get("primary_examples") or []
    senses = entry.get("senses") or []
    pos_label = entry.get("pos_label", "word")
    word = surface or entry.get("lemma", "")

    # Elementary: simple one-liner with optional example
    example_part = f' For example: "{examples[0]}"' if examples else ""
    elementary = f'"{word}" is a {pos_label} that means: {primary_def}.{example_part}'

    # Intermediate: definition only (clean, no example noise)
    intermediate = f'"{word}": {primary_def}.'

    # Advanced: list up to 3 senses
    if len(senses) > 1:
        sense_lines = "; ".join(
            f'({i + 1}) {s["definition"]}' for i, s in enumerate(senses[:3])
        )
        advanced = f'"{word}" ({pos_label}) has multiple senses: {sense_lines}.'
    else:
        advanced = intermediate

    return {
        "elementary_text": elementary,
        "intermediate_text": intermediate,
        "advanced_text": advanced,
    }


def get_wordnet_note(
    *,
    lemma: str,
    part_of_speech: str,
    grammatical_role: str,
    surface: str = "",
) -> Optional[dict[str, str]]:
    """Return level-differentiated notes for a word, or None if not applicable.

    Args:
        lemma: spaCy lemma (lowercase).
        part_of_speech: word's part_of_speech field from the node.
        grammatical_role: word's grammatical_role field.
        surface: surface form of the word (for display).

    Returns:
        Dict with elementary_text / intermediate_text / advanced_text, or None.
    """
    role = (grammatical_role or "").strip().lower()
    lemma_lower = (lemma or "").strip().lower()
    word = surface or lemma_lower

    # Auxiliaries: short note pointing to the enclosing phrase explanation.
    if role in _AUXILIARY_ROLES or (
        part_of_speech in ("auxiliary verb",) and lemma_lower in _SKIP_LEMMAS
    ):
        return {
            "elementary_text": (
                f'"{word}" is a helper verb. '
                "It works together with the other verbs in this phrase."
            ),
            "intermediate_text": (
                f'"{word}" is an auxiliary verb whose grammatical role '
                "is explained in the verb phrase note above."
            ),
            "advanced_text": (
                f'"{word}" functions as an auxiliary within the enclosing verb phrase. '
                "Its contribution to tense, aspect, modality, or voice "
                "is analysed in the phrase-level note."
            ),
        }

    if lemma_lower in _SKIP_LEMMAS:
        return None

    wn_pos = _SPACY_TO_WN_POS.get((part_of_speech or "").strip().lower())
    if not wn_pos:
        return None

    index = _load_index()
    if not index:
        return None

    entry = index.get((lemma_lower, wn_pos))
    if not entry:
        return None

    return _make_notes(entry, surface or lemma_lower)
