"""Deterministic fallback notes when model output is low quality."""

from __future__ import annotations

from typing import Dict


def _sentence_note(node: Dict) -> str:
    tense = (node.get("tense") or "null").strip().lower()
    content = (node.get("content") or "").strip()
    token_count = len(content.split()) if content else 0

    if tense and tense != "null":
        return (
            f"This sentence expresses a complete proposition and is anchored in {tense} time reference, "
            f"with about {token_count} lexical items."
        )
    return (
        f"This sentence expresses a complete proposition with finite clause structure "
        f"and about {token_count} lexical items."
    )


def _phrase_note(node: Dict) -> str:
    content = node.get("content", "this phrase")
    pos = (node.get("part_of_speech") or "phrase").strip().lower()
    tense = (node.get("tense") or "null").strip().lower()
    words = content.split()
    lead = words[0].lower() if words else ""

    if "noun phrase" in pos:
        if lead in {"a", "an", "the"}:
            return (
                f"The phrase '{content}' is a noun phrase with an explicit determiner, "
                "marking a participant or referential entity."
            )
        return f"The phrase '{content}' functions as a noun phrase marking a participant or referential entity."
    if "verb phrase" in pos:
        if tense and tense != "null":
            return (
                f"The phrase '{content}' is a verb phrase encoding an action/state "
                f"with {tense} temporal interpretation."
            )
        return f"The phrase '{content}' is a verb phrase encoding an action or state."
    if "prepositional phrase" in pos:
        return (
            f"The phrase '{content}' is a prepositional phrase introducing relational context "
            "such as location, time, or semantic linkage."
        )
    return (
        f"The phrase '{content}' contributes phrasal structure that supports sentence-level "
        "interpretation and information packaging."
    )


def _word_note(node: Dict) -> str:
    content = node.get("content", "This word")
    content_l = content.lower()
    pos = (node.get("part_of_speech") or "word").strip().lower()
    tense = (node.get("tense") or "null").strip().lower()

    if pos == "article":
        if content_l == "the":
            return f"'{content}' is the definite article, signaling a specific or identifiable noun reference."
        if content_l in {"a", "an"}:
            return f"'{content}' is an indefinite article, introducing a nonspecific countable noun reference."

    if pos == "verb":
        if tense == "past":
            return f"'{content}' is a past-form verb that presents the event as completed in prior time."
        if tense == "present":
            return f"'{content}' is a present-form verb expressing an action or state in current relevance."
        if tense == "past participle":
            return f"'{content}' is a past participle that often contributes perfect or passive verbal constructions."
        if tense == "present participle":
            return f"'{content}' is a present participle that can mark progressive aspect or modifier function."
        if tense == "participle":
            return f"'{content}' is a participial verb form contributing non-finite verbal meaning."

    if pos == "preposition":
        prep_templates = {
            "in": f"'{content}' is a preposition marking containment or location within a bounded context.",
            "on": f"'{content}' is a preposition marking surface contact or supported spatial relation.",
            "at": f"'{content}' is a preposition marking a point-like location or temporal anchor.",
            "to": f"'{content}' is a preposition marking direction, goal, or recipient relation.",
            "from": f"'{content}' is a preposition marking source, origin, or starting point relation.",
            "with": f"'{content}' is a preposition marking accompaniment, instrument, or associative relation.",
            "by": f"'{content}' is a preposition marking agency, means, or proximity relation.",
            "of": f"'{content}' is a preposition marking dependency, composition, or possessive relation.",
        }
        if content_l in prep_templates:
            return prep_templates[content_l]

    templates = {
        "article": f"'{content}' is an article used to specify or determine a related noun.",
        "noun": f"'{content}' is a noun that names an entity, concept, or object in context.",
        "proper noun": f"'{content}' is a proper noun referring to a specific named entity.",
        "pronoun": f"'{content}' is a pronoun used to refer to an entity without repeating a full noun phrase.",
        "verb": f"'{content}' is a verb form that contributes core action or state meaning.",
        "auxiliary verb": f"'{content}' is an auxiliary verb that supports tense, aspect, modality, or voice.",
        "adjective": f"'{content}' is an adjective that modifies a noun by adding descriptive information.",
        "adverb": f"'{content}' is an adverb that modifies a verb, adjective, or clause-level meaning.",
        "preposition": f"'{content}' is a preposition that links a noun phrase to another sentence element.",
        "coordinating conjunction": f"'{content}' is a coordinating conjunction that joins parallel elements.",
        "subordinating conjunction": f"'{content}' is a subordinating conjunction introducing a dependent clause.",
        "particle": f"'{content}' functions as a particle that refines a verb or clause meaning.",
        "numeral": f"'{content}' is a numeral expressing quantity or order.",
        "interjection": f"'{content}' is an interjection expressing immediate attitude or reaction.",
        "punctuation": f"'{content}' is punctuation marking structure, boundaries, or discourse rhythm.",
    }

    if pos in templates:
        return templates[pos]
    return f"'{content}' is a lexical item contributing grammatical and semantic information in context."


def build_fallback_note(node: Dict) -> str:
    node_type = (node.get("type") or "").strip()
    if node_type == "Sentence":
        return _sentence_note(node)
    if node_type == "Phrase":
        return _phrase_note(node)
    if node_type == "Word":
        return _word_note(node)
    return "This element contributes to the sentence structure and interpreted meaning."
