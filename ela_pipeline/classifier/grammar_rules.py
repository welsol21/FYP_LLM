"""Shared rules-first pedagogical grammar mapping."""

from __future__ import annotations

from typing import Iterable


def map_pedagogical_grammar_classes(
    *,
    tense: str | None = None,
    aspect: str | None = None,
    mood: str | None = None,
    voice: str | None = None,
    tam_construction: str | None = None,
    dep_labels: Iterable[str] | None = None,
    content: str | None = None,
    node_type: str | None = None,
    part_of_speech: str | None = None,
    has_neg: bool | None = None,
    has_relative_clause: bool | None = None,
    has_passive_signal: bool | None = None,
    is_question: bool | None = None,
) -> list[str]:
    classes: list[str] = []
    seen: set[str] = set()

    def add_class(class_id: str) -> None:
        cid = str(class_id or "").strip().lower()
        if not cid or cid in seen:
            return
        seen.add(cid)
        classes.append(cid)

    dep_signature = [str(item).strip().lower() for item in (dep_labels or []) if str(item).strip()]
    raw_text = str(content or "").strip()
    text = raw_text.lower()
    tense_value = str(tense or "").strip().lower()
    aspect_value = str(aspect or "").strip().lower()
    mood_value = str(mood or "").strip().lower()
    voice_value = str(voice or "").strip().lower()
    construction = str(tam_construction or "").strip().lower()
    node_kind = str(node_type or "").strip().lower()
    pos_value = str(part_of_speech or "").strip().lower()
    verb_like_word = pos_value in {"verb", "auxiliary verb"}
    is_tense_applicable = node_kind in {"", "sentence", "phrase"} or (node_kind == "word" and verb_like_word)

    negative = bool(has_neg) if has_neg is not None else (
        "neg" in dep_signature or " not " in f" {text} " or "n't" in text
    )
    relative_clause = bool(has_relative_clause) if has_relative_clause is not None else ("acl:relcl" in dep_signature)
    passive_signal = bool(has_passive_signal) if has_passive_signal is not None else (
        "aux:pass" in dep_signature or "nsubj:pass" in dep_signature or voice_value == "passive" or construction == "passive_voice"
    )
    question = bool(is_question) if is_question is not None else (text.endswith("?") or ("aux" in dep_signature and "?" in text))

    if relative_clause:
        add_class("relative_clause")
    if is_tense_applicable:
        if construction == "future_perfect" or ("future" in tense_value and aspect_value == "perfect"):
            add_class("future_perfect")
        if construction == "modal_perfect" or (mood_value == "modal" and aspect_value == "perfect"):
            add_class("modal_perfect")
        if construction == "past_perfect" or ("past perfect" in tense_value) or (tense_value == "past" and aspect_value == "perfect"):
            add_class("past_perfect")
        if passive_signal:
            add_class("passive_voice")
        if construction == "modal_should":
            add_class("modal_should_advice")
        if construction == "modal_can":
            add_class("modal_can_ability")
        if construction == "future_will":
            add_class("future_will")
        elif tense_value == "future" and aspect_value in {"simple", ""}:
            add_class("future_will")
        if construction == "future_going_to":
            add_class("future_going_to")
        if construction == "present_simple" and question:
            add_class("present_simple_question")
        if construction == "present_perfect" or "present perfect" in tense_value:
            add_class("present_perfect_negative" if negative else "present_perfect_affirmative")
        elif construction == "present_simple" or tense_value == "present":
            add_class("present_simple_negative" if negative else "present_simple_affirmative")
        elif construction == "past_simple" or tense_value == "past":
            add_class("past_simple_negative" if negative else "past_simple_affirmative")
        elif construction == "present_continuous" or "progressive" in tense_value or aspect_value in {"progressive", "continuous"}:
            add_class("present_continuous")
        elif construction == "be_copula" or (node_kind == "phrase" and pos_value == "noun phrase" and "cop" in dep_signature):
            add_class("copular_clause")

    if node_kind == "phrase":
        if pos_value == "noun phrase":
            text_tokens = [token for token in raw_text.split() if token]
            if len(text_tokens) >= 2:
                if all(token[:1].isupper() for token in text_tokens if token[:1].isalpha()):
                    add_class("proper_name_phrase")
                else:
                    add_class("noun_phrase_reference")
        elif pos_value == "prepositional phrase":
            add_class("prepositional_relation_phrase")

    if node_kind == "word":
        if pos_value == "pronoun":
            add_class("pronoun_reference")
        elif pos_value == "proper noun":
            add_class("proper_noun_name")
        elif pos_value == "noun":
            add_class("common_noun_lexeme")
        elif pos_value == "preposition":
            add_class("preposition_linker")
        elif pos_value == "article":
            add_class("article_determiner")
        elif pos_value == "adjective":
            add_class("adjective_modifier")
        elif pos_value == "adverb":
            add_class("adverb_modifier")
        elif pos_value == "punctuation":
            add_class("punctuation_marker")

    return classes
