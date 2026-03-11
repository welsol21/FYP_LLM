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


def _node_subject_label(node_type: str | None) -> str:
    normalized = str(node_type or "").strip().lower()
    if normalized == "sentence":
        return "This sentence"
    if normalized == "phrase":
        return "This phrase"
    if normalized == "word":
        return "This word"
    return "This node"


def _instruction_to_explanation(text: str, *, subject: str) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    for prefix in ("Identify ", "Explain ", "Describe "):
        if src.startswith(prefix):
            tail = src[len(prefix) :].strip()
            if tail.endswith("."):
                tail = tail[:-1].rstrip()
            if tail and tail[0].isalpha():
                tail = tail[0].lower() + tail[1:]
            return f"{subject} shows {tail}."
    return src


_INVALID_ROLE_HINTS = {"", "other", "unknown", "null", "none", "grammar slot"}


def _normalize_role_hint(role: str | None) -> str:
    value = str(role or "").strip().lower().replace("_", " ")
    if value in _INVALID_ROLE_HINTS:
        return ""
    return value


def _word_form_override(
    *,
    primary_class: str,
    node_type: str | None,
    part_of_speech: str | None,
    tense: str | None,
) -> dict[str, str] | None:
    if str(node_type or "").strip().lower() != "word":
        return None
    pos = str(part_of_speech or "").strip().lower()
    tense_value = str(tense or "").strip().lower()
    finite_clause_classes = {
        "present_simple_affirmative",
        "present_simple_negative",
        "present_simple_question",
        "past_simple_affirmative",
        "past_simple_negative",
        "present_continuous",
        "present_perfect_affirmative",
        "present_perfect_negative",
        "future_will",
        "future_going_to",
        "modal_can_ability",
        "modal_should_advice",
        "past_perfect",
        "passive_voice",
        "modal_perfect",
        "future_perfect",
        "copular_clause",
        "relative_clause",
    }
    if primary_class not in finite_clause_classes or pos not in {"verb", "auxiliary verb"}:
        return None

    if tense_value == "past participle":
        return {
            "elementary_text": "This word is a past participle form.",
            "intermediate_text": (
                "This word is a past participle, so it does not mark a finite tense by itself. "
                "It usually contributes to a perfect, passive, or reduced-clause pattern."
            ),
            "advanced_text": (
                "This word realizes non-finite past-participle morphology and contributes to perfect, passive, "
                "or reduced-clause structure rather than serving as an independent finite tense marker."
            ),
        }
    if tense_value == "present participle":
        return {
            "elementary_text": "This word is an -ing participle form.",
            "intermediate_text": (
                "This word is a present participle, so it usually contributes to a progressive or non-finite pattern "
                "instead of functioning as an independent finite tense form."
            ),
            "advanced_text": (
                "This word realizes non-finite -ing morphology and contributes to progressive aspect or clause "
                "compression rather than standing alone as a finite tense marker."
            ),
        }
    return None


def build_note_blueprints(
    *,
    grammar_classes: list[str] | None,
    cefr_level: str | None = None,
    node_type: str | None = None,
    content: str | None = None,
    grammatical_role: str | None = None,
    tam_construction: str | None = None,
    part_of_speech: str | None = None,
    tense: str | None = None,
) -> dict[str, str]:
    class_ids = [
        normalize_grammar_class_id(str(class_id).strip())
        for class_id in (grammar_classes or [])
        if str(class_id).strip()
    ]
    primary_class = next((class_id for class_id in class_ids if class_id in PEDAGOGICAL_CLASS_SPECS), "")
    if primary_class:
        spec = PEDAGOGICAL_CLASS_SPECS[primary_class]
        subject = _node_subject_label(node_type)
        role_hint = _normalize_role_hint(grammatical_role)
        snippet = str(content or "").strip()
        snippet = " ".join(snippet.split())
        if len(snippet) > 72:
            snippet = f"{snippet[:69].rstrip()}..."
        override = _word_form_override(
            primary_class=primary_class,
            node_type=node_type,
            part_of_speech=part_of_speech,
            tense=tense,
        )
        if override:
            return override
        elementary = _instruction_to_explanation(str(spec["elementary_text"]).strip(), subject=subject)
        intermediate = _instruction_to_explanation(str(spec["intermediate_text"]).strip(), subject=subject)
        advanced = _instruction_to_explanation(str(spec["advanced_text"]).strip(), subject=subject)
        if snippet and role_hint:
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
