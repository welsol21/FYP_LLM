"""Shared pedagogical grammar taxonomy and note blueprint helpers."""

from __future__ import annotations

from .class_taxonomy import normalize_grammar_class_id

from typing import Any


PEDAGOGICAL_CLASS_SPECS: dict[str, dict[str, str]] = {
    "present_simple_affirmative": {
        "cefr_level": "A1",
        "elementary_text": "Identify the present simple statement and its basic meaning.",
        "intermediate_text": "Explain present simple form, subject-verb agreement, and its routine meaning.",
        "advanced_text": "Describe how the present simple encodes habitual or general meaning in context.",
    },
    "present_simple_negative": {
        "cefr_level": "A1",
        "elementary_text": "Identify the present simple negative statement.",
        "intermediate_text": "Explain present simple negation and the role of the auxiliary pattern.",
        "advanced_text": "Describe how present simple negation changes polarity while preserving routine meaning.",
    },
    "past_simple_affirmative": {
        "cefr_level": "A2",
        "elementary_text": "Identify the past simple statement and the finished past action.",
        "intermediate_text": "Explain past simple verb form and completed past-time meaning.",
        "advanced_text": "Describe how the past simple places the event in a finished narrative timeline.",
    },
    "past_simple_negative": {
        "cefr_level": "A2",
        "elementary_text": "Identify the past simple negative statement.",
        "intermediate_text": "Explain past simple negation and the completed past-time meaning.",
        "advanced_text": "Describe how the clause negates a finished past event in context.",
    },
    "present_continuous": {
        "cefr_level": "A2",
        "elementary_text": "Identify the present continuous form and ongoing action.",
        "intermediate_text": "Explain the be + -ing pattern and its ongoing meaning.",
        "advanced_text": "Describe how the present continuous presents a current, unfolding event.",
    },
    "present_simple_question": {
        "cefr_level": "A1",
        "elementary_text": "Identify the present simple question form.",
        "intermediate_text": "Explain how the auxiliary do forms a present simple question.",
        "advanced_text": "Describe how the question uses auxiliary inversion to ask for present-time information.",
    },
    "copular_clause": {
        "cefr_level": "A1",
        "elementary_text": "Identify the be-clause and the basic link between subject and complement.",
        "intermediate_text": "Explain how the copular verb connects the subject to a description or identity.",
        "advanced_text": "Describe the clause as a copular structure that links subject and complement meaning.",
    },
    "noun_phrase_reference": {
        "cefr_level": "A1",
        "elementary_text": "Identify this noun phrase as one unit that names a person, thing, or idea.",
        "intermediate_text": "Explain how this noun phrase groups words together to identify one referent.",
        "advanced_text": "Describe how the noun phrase packages its referent as one grammatical unit in context.",
    },
    "proper_name_phrase": {
        "cefr_level": "A1",
        "elementary_text": "Identify this phrase as a proper name.",
        "intermediate_text": "Explain how this proper-name phrase identifies a specific person, place, or title.",
        "advanced_text": "Describe how the proper-name phrase fixes reference to a unique named entity in context.",
    },
    "prepositional_relation_phrase": {
        "cefr_level": "A2",
        "elementary_text": "Identify this prepositional phrase and the relation it adds.",
        "intermediate_text": "Explain how this prepositional phrase links its object to the rest of the clause.",
        "advanced_text": "Describe the semantic relation encoded by this prepositional phrase in context.",
    },
    "pronoun_reference": {
        "cefr_level": "A1",
        "elementary_text": "Identify the pronoun and who or what it refers to.",
        "intermediate_text": "Explain how this pronoun stands in for a noun phrase in context.",
        "advanced_text": "Describe how the pronoun maintains reference without repeating the full noun phrase.",
    },
    "proper_noun_name": {
        "cefr_level": "A1",
        "elementary_text": "Identify this word as a proper name.",
        "intermediate_text": "Explain how this proper noun names a specific person, place, or title.",
        "advanced_text": "Describe how the proper noun fixes reference to a unique named entity.",
    },
    "common_noun_lexeme": {
        "cefr_level": "A1",
        "elementary_text": "Identify this word as a noun naming a person, thing, or idea.",
        "intermediate_text": "Explain how this noun contributes the main naming meaning in its phrase.",
        "advanced_text": "Describe how the noun anchors the lexical meaning of the noun phrase.",
    },
    "preposition_linker": {
        "cefr_level": "A1",
        "elementary_text": "Identify the preposition that links this element to another part of the clause.",
        "intermediate_text": "Explain how this preposition marks a relation such as direction, place, time, or source.",
        "advanced_text": "Describe how the preposition encodes the semantic link between its complement and the larger clause.",
    },
    "article_determiner": {
        "cefr_level": "A1",
        "elementary_text": "Identify the article or determiner in this position.",
        "intermediate_text": "Explain how this determiner helps mark reference in the noun phrase.",
        "advanced_text": "Describe how the determiner constrains reference and information status in the noun phrase.",
    },
    "adjective_modifier": {
        "cefr_level": "A1",
        "elementary_text": "Identify the adjective that describes a noun.",
        "intermediate_text": "Explain how this adjective adds descriptive meaning to the noun phrase.",
        "advanced_text": "Describe how the adjective modifies the noun by adding qualitative information.",
    },
    "adverb_modifier": {
        "cefr_level": "A2",
        "elementary_text": "Identify the adverb that adds extra information to the action or clause.",
        "intermediate_text": "Explain how this adverb modifies the verb, adjective, or whole clause.",
        "advanced_text": "Describe how the adverb adjusts manner, degree, time, or speaker stance in context.",
    },
    "punctuation_marker": {
        "cefr_level": "A1",
        "elementary_text": "Identify this punctuation mark and where it separates parts of the sentence.",
        "intermediate_text": "Explain how this punctuation mark organizes sentence structure and reading flow.",
        "advanced_text": "Describe how punctuation contributes to clause boundary signaling and discourse rhythm.",
    },
    "present_perfect_affirmative": {
        "cefr_level": "B1",
        "elementary_text": "Identify the present perfect form and the link between past action and present relevance.",
        "intermediate_text": "Explain the have + past participle pattern and its present-result meaning.",
        "advanced_text": "Describe how the present perfect connects an earlier event to the current reference point.",
    },
    "present_perfect_negative": {
        "cefr_level": "B1",
        "elementary_text": "Identify the present perfect negative form.",
        "intermediate_text": "Explain how present perfect negation marks the absence of a relevant past event.",
        "advanced_text": "Describe how negative present perfect blocks an expected prior event with present relevance.",
    },
    "relative_clause": {
        "cefr_level": "B1",
        "elementary_text": "Identify the relative clause as extra information about a noun.",
        "intermediate_text": "Explain how the relative clause modifies a noun and adds defining information.",
        "advanced_text": "Describe the relative clause as an embedded modifier that refines the noun phrase reference.",
    },
    "future_will": {
        "cefr_level": "A2",
        "elementary_text": "Identify the future form with will.",
        "intermediate_text": "Explain how will + base verb expresses future meaning.",
        "advanced_text": "Describe how will projects an event forward from the present reference point.",
    },
    "future_going_to": {
        "cefr_level": "A2",
        "elementary_text": "Identify the be going to future form.",
        "intermediate_text": "Explain how be going to + infinitive expresses a future plan or expectation.",
        "advanced_text": "Describe how be going to presents an intended or expected future event.",
    },
    "modal_can_ability": {
        "cefr_level": "A2",
        "elementary_text": "Identify can as a modal of ability.",
        "intermediate_text": "Explain how can + base verb expresses ability.",
        "advanced_text": "Describe how the modal can encodes practical or general ability in context.",
    },
    "modal_should_advice": {
        "cefr_level": "B1",
        "elementary_text": "Identify should as advice or recommendation.",
        "intermediate_text": "Explain how should + base verb gives advice.",
        "advanced_text": "Describe how should marks speaker stance and recommendation rather than factual description.",
    },
    "past_perfect": {
        "cefr_level": "B2",
        "elementary_text": "Identify the past perfect form.",
        "intermediate_text": "Explain how had + past participle marks an earlier past event.",
        "advanced_text": "Describe how the past perfect orders one past event before another reference point in the past.",
    },
    "passive_voice": {
        "cefr_level": "B2",
        "elementary_text": "Identify the passive construction.",
        "intermediate_text": "Explain how the passive shifts focus from the doer to the affected thing.",
        "advanced_text": "Describe how passive voice backgrounds the agent and foregrounds the affected participant.",
    },
    "modal_perfect": {
        "cefr_level": "C1",
        "elementary_text": "Identify the modal perfect form.",
        "intermediate_text": "Explain how modal + have + past participle evaluates a past event.",
        "advanced_text": "Describe how the modal perfect expresses stance, inference, criticism, or regret about a completed past event.",
    },
    "future_perfect": {
        "cefr_level": "C2",
        "elementary_text": "Identify the future perfect form.",
        "intermediate_text": "Explain how will have + past participle marks completion before a future reference point.",
        "advanced_text": "Describe how the future perfect projects a completed event into a structured future timeline.",
    },
}


def humanize_grammar_class_id(class_id: str) -> str:
    raw = str(class_id or "").strip()
    if not raw:
        return "core grammar pattern"
    return raw.replace("_", " ")


def build_note_blueprints(
    *,
    grammar_classes: list[str] | None,
    cefr_level: str | None = None,
    node_type: str | None = None,
    content: str | None = None,
    grammatical_role: str | None = None,
    tam_construction: str | None = None,
) -> dict[str, str]:
    class_ids = [
        normalize_grammar_class_id(str(class_id).strip())
        for class_id in (grammar_classes or [])
        if str(class_id).strip()
    ]
    primary_class = next((class_id for class_id in class_ids if class_id in PEDAGOGICAL_CLASS_SPECS), "")
    if primary_class:
        spec = PEDAGOGICAL_CLASS_SPECS[primary_class]
        role = str(grammatical_role or "").strip().lower()
        role_hint = role.replace("_", " ") if role else "grammar slot"
        snippet = str(content or "").strip()
        snippet = " ".join(snippet.split())
        if len(snippet) > 72:
            snippet = f"{snippet[:69].rstrip()}..."
        elementary = str(spec["elementary_text"]).strip()
        intermediate = str(spec["intermediate_text"]).strip()
        advanced = str(spec["advanced_text"]).strip()
        if snippet:
            intermediate = f"{intermediate} Here, '{snippet}' functions as {role_hint}."
            advanced = f"{advanced} In this sentence, '{snippet}' fills the {role_hint} role."
        return {
            "elementary_text": elementary,
            "intermediate_text": intermediate,
            "advanced_text": advanced,
        }
    return {}


def class_cefr_level(class_id: str) -> str | None:
    spec = PEDAGOGICAL_CLASS_SPECS.get(normalize_grammar_class_id(str(class_id or "").strip()))
    if not isinstance(spec, dict):
        return None
    value = str(spec.get("cefr_level") or "").strip().upper()
    return value or None
