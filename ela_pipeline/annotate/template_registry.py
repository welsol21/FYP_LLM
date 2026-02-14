"""Deterministic template registry and hierarchical context matching."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from ela_pipeline.validation.notes_quality import sanitize_note

REGISTRY_VERSION = "v1"

MODAL_AUX = {"should", "could", "would", "might", "may", "must", "can", "will", "shall"}
POSSESSIVES = {"my", "your", "his", "her", "our", "their", "its"}

_TOKEN_RE = re.compile(r"[A-Za-z']+")


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(_norm(text))


def _dep(node: Dict[str, object]) -> str:
    dep = _norm(node.get("dep_label") or node.get("grammatical_role") or "dep")
    if dep in {"aux", "poss", "det", "prep", "dobj", "pobj", "object", "root", "predicate", "modifier", "clause"}:
        return dep
    return "dep"


def _tam(node: Dict[str, object]) -> str:
    mood = _norm(node.get("mood"))
    aspect = _norm(node.get("aspect"))
    if mood == "modal" and aspect == "perfect":
        return "modal_perfect"
    return "none"


def _lex_class(node: Dict[str, object]) -> str:
    level = _norm(node.get("type"))
    content = _norm(node.get("content"))
    toks = _tokens(content)
    first = toks[0] if toks else "generic"
    pos = _norm(node.get("part_of_speech"))

    if level == "word":
        tense = _norm(node.get("tense"))
        if pos == "auxiliary verb" and first in MODAL_AUX:
            return "modal_aux"
        if pos == "auxiliary verb" and first == "have":
            return "have_aux"
        if pos == "article" and first == "the":
            return "def_article"
        if pos == "pronoun" and (_dep(node) == "poss" or first in POSSESSIVES):
            return "possessive"
        if pos == "verb" and (first.endswith("ing") or "present participle" in tense):
            return "ing_form"
        if pos == "verb" and "participle" in tense:
            return "participle_form"
        return "generic"

    if level == "phrase":
        if "noun phrase" in pos and any(t in POSSESSIVES for t in toks):
            return "possessive"
        if first == "before" and any(t.endswith("ing") for t in toks[1:]):
            return "before_ing"
        return "generic"

    if level == "sentence":
        if first in {"before", "after", "when", "while"}:
            return "time_subordinator"
        if first in {"because", "since", "as"}:
            return "reason_subordinator"
        if first in {"although", "though"}:
            return "concession_subordinator"
        return "generic"

    return "generic"


def build_context_keys(node: Dict[str, object]) -> Dict[str, str]:
    level = _norm(node.get("type"))
    pos = _norm(node.get("part_of_speech"))
    dep = _dep(node)
    tam = _tam(node)
    lex = _lex_class(node)
    return {
        "l1": f"{level}|{pos}|{dep}|{tam}|{lex}",
        "l2": f"{level}|{pos}|{dep}|{lex}",
        "l3": f"{level}|{pos}",
        "l4": level,
    }


REGISTRY_L1: Dict[str, str] = {
    "sentence|sentence|clause|none|time_subordinator": "CLAUSE_SUBORDINATE_TIME",
    "sentence|sentence|clause|none|reason_subordinator": "CLAUSE_SUBORDINATE_REASON",
    "sentence|sentence|clause|none|concession_subordinator": "CLAUSE_SUBORDINATE_CONCESSION",
    "phrase|verb phrase|predicate|modal_perfect|generic": "VP_MODAL_PERFECT",
    "phrase|verb phrase|predicate|none|generic": "VP_AUXILIARY",
    "phrase|verb phrase|dep|modal_perfect|generic": "VP_MODAL_PERFECT",
    "phrase|verb phrase|dep|none|generic": "VP_AUXILIARY",
    "phrase|noun phrase|object|none|possessive": "NP_POSSESSIVE",
    "phrase|noun phrase|object|none|generic": "NP_DETERMINER_NOUN",
    "phrase|noun phrase|dep|none|possessive": "NP_POSSESSIVE",
    "phrase|noun phrase|dep|none|generic": "NP_DETERMINER_NOUN",
    "phrase|prepositional phrase|modifier|none|before_ing": "PP_TIME_BEFORE_ING",
    "phrase|prepositional phrase|prep|none|before_ing": "PP_TIME_BEFORE_ING",
    "phrase|prepositional phrase|modifier|none|generic": "PP_GENERAL_LINKING",
    "phrase|prepositional phrase|prep|none|generic": "PP_GENERAL_LINKING",
    "word|auxiliary verb|aux|none|modal_aux": "WORD_AUX_MODAL",
    "word|auxiliary verb|aux|none|have_aux": "WORD_AUX_HAVE",
    "word|auxiliary verb|aux|none|generic": "WORD_AUX_GENERAL",
    "word|verb|root|none|ing_form": "WORD_VERB_ING",
    "word|verb|root|none|participle_form": "WORD_VERB_PARTICIPLE",
    "word|verb|root|none|generic": "WORD_VERB_FINITE",
    "word|verb|dep|none|ing_form": "WORD_VERB_ING",
    "word|verb|dep|none|participle_form": "WORD_VERB_PARTICIPLE",
    "word|verb|dep|none|generic": "WORD_VERB_FINITE",
    "word|pronoun|poss|none|possessive": "WORD_PRONOUN_POSSESSIVE",
    "word|preposition|prep|none|generic": "WORD_PREPOSITION",
    "word|adjective|dep|none|generic": "WORD_ADJECTIVE",
    "word|adjective|amod|none|generic": "WORD_ADJECTIVE",
    "word|adverb|dep|none|generic": "WORD_ADVERB",
    "word|adverb|advmod|none|generic": "WORD_ADVERB",
}

REGISTRY_L2: Dict[str, str] = {
    "sentence|sentence|clause|time_subordinator": "CLAUSE_SUBORDINATE_TIME",
    "sentence|sentence|clause|reason_subordinator": "CLAUSE_SUBORDINATE_REASON",
    "sentence|sentence|clause|concession_subordinator": "CLAUSE_SUBORDINATE_CONCESSION",
    "sentence|sentence|clause|generic": "SENTENCE_FINITE_CLAUSE",
    "phrase|verb phrase|predicate|generic": "VP_AUXILIARY",
    "phrase|verb phrase|dep|generic": "VP_AUXILIARY",
    "phrase|noun phrase|object|possessive": "NP_POSSESSIVE",
    "phrase|noun phrase|dep|possessive": "NP_POSSESSIVE",
    "phrase|noun phrase|object|generic": "NP_DETERMINER_NOUN",
    "phrase|noun phrase|dep|generic": "NP_DETERMINER_NOUN",
    "phrase|prepositional phrase|modifier|before_ing": "PP_TIME_BEFORE_ING",
    "phrase|prepositional phrase|prep|before_ing": "PP_TIME_BEFORE_ING",
    "phrase|prepositional phrase|modifier|generic": "PP_GENERAL_LINKING",
    "phrase|prepositional phrase|prep|generic": "PP_GENERAL_LINKING",
    "word|auxiliary verb|aux|modal_aux": "WORD_AUX_MODAL",
    "word|auxiliary verb|aux|have_aux": "WORD_AUX_HAVE",
    "word|auxiliary verb|aux|generic": "WORD_AUX_GENERAL",
    "word|verb|root|ing_form": "WORD_VERB_ING",
    "word|verb|dep|ing_form": "WORD_VERB_ING",
    "word|verb|root|participle_form": "WORD_VERB_PARTICIPLE",
    "word|verb|dep|participle_form": "WORD_VERB_PARTICIPLE",
    "word|verb|root|generic": "WORD_VERB_FINITE",
    "word|verb|dep|generic": "WORD_VERB_FINITE",
    "word|pronoun|poss|possessive": "WORD_PRONOUN_POSSESSIVE",
    "word|noun|dobj|generic": "WORD_NOUN_COMMON",
    "word|noun|pobj|generic": "WORD_NOUN_COMMON",
    "word|noun|object|generic": "WORD_NOUN_COMMON",
    "word|article|det|def_article": "WORD_ARTICLE_DEFINITE",
    "word|preposition|prep|generic": "WORD_PREPOSITION",
    "word|adjective|dep|generic": "WORD_ADJECTIVE",
    "word|adjective|amod|generic": "WORD_ADJECTIVE",
    "word|adverb|dep|generic": "WORD_ADVERB",
    "word|adverb|advmod|generic": "WORD_ADVERB",
}

REGISTRY_L3: Dict[str, str] = {
    "sentence|sentence": "SENTENCE_FINITE_CLAUSE",
    "phrase|verb phrase": "VP_AUXILIARY",
    "phrase|noun phrase": "NP_DETERMINER_NOUN",
    "phrase|prepositional phrase": "PP_GENERAL_LINKING",
    "word|auxiliary verb": "WORD_AUX_HAVE",
    "word|verb": "WORD_VERB_FINITE",
    "word|pronoun": "WORD_PRONOUN_POSSESSIVE",
    "word|noun": "WORD_NOUN_COMMON",
    "word|proper noun": "WORD_NOUN_COMMON",
    "word|article": "WORD_ARTICLE_DEFINITE",
    "word|preposition": "WORD_PREPOSITION",
    "word|adjective": "WORD_ADJECTIVE",
    "word|adverb": "WORD_ADVERB",
}

REGISTRY_L4: Dict[str, str] = {
    "sentence": "SENTENCE_FINITE_CLAUSE",
    "phrase": "PP_GENERAL_LINKING",
    "word": "WORD_NOUN_COMMON",
}

TEMPLATE_VARIANTS: Dict[str, List[str]] = {
    "SENTENCE_FINITE_CLAUSE": [
        "This sentence forms a finite clause that expresses a complete proposition.",
        "The sentence is a finite clause with a complete clause-level meaning.",
        "This sentence functions as a complete finite clause in context.",
        "This sentence encodes a full proposition through a finite clause structure.",
        "The sentence presents a complete finite clause with one main proposition.",
    ],
    "CLAUSE_SUBORDINATE_TIME": [
        "This sentence contains a time subclause that situates the main event.",
        "The sentence uses a subordinate time relation to anchor the event.",
        "This sentence marks temporal sequencing through a subordinate clause.",
        "A subordinate time clause organizes when the main event is interpreted.",
        "This sentence includes a temporal subclause that frames the main clause.",
    ],
    "CLAUSE_SUBORDINATE_REASON": [
        "This sentence includes a subordinate clause that expresses a reason.",
        "A reason subclause explains why the main event holds.",
        "This sentence marks causation through a subordinate reason clause.",
        "The clause structure contains a reason relation for the main event.",
        "A subordinate reason clause provides motivation for the main statement.",
    ],
    "CLAUSE_SUBORDINATE_CONCESSION": [
        "This sentence uses a concessive subclause contrasting with the main clause.",
        "A subordinate concession clause introduces contrast to the main event.",
        "This sentence marks concession while preserving the main-clause claim.",
        "The clause structure includes a concessive relation to the main statement.",
        "A concession subclause adds contrast against the core clause meaning.",
    ],
    "VP_MODAL_PERFECT": [
        "The phrase '{content}' is a verb phrase with modal meaning and perfect aspect.",
        "This phrase uses a modal plus perfect construction in the verbal group.",
        "The phrase '{content}' marks modality through a perfect verb phrase pattern.",
        "This verb phrase combines a modal auxiliary with a perfect construction.",
        "The phrase '{content}' is a modal-perfect verb phrase in clause structure.",
    ],
    "VP_AUXILIARY": [
        "The phrase '{content}' is a verb phrase supported by an auxiliary pattern.",
        "This phrase functions as a verb phrase with auxiliary-driven verbal structure.",
        "The phrase '{content}' forms a verb phrase centered on auxiliary support.",
        "This verb phrase uses an auxiliary to organize verbal grammar.",
        "The phrase '{content}' is a verbal phrase with auxiliary structure.",
    ],
    "VP_PARTICIPLE": [
        "The phrase '{content}' is a verb phrase built around a participle form.",
        "This phrase functions as a participial verb phrase in context.",
        "The phrase '{content}' uses a participle as the verbal center.",
        "This verb phrase is organized around participial verbal morphology.",
        "The phrase '{content}' forms a participle-based verbal phrase.",
    ],
    "NP_POSSESSIVE": [
        "The phrase '{content}' is a noun phrase with a possessive relation.",
        "This phrase functions as a possessive noun phrase in the clause.",
        "The phrase '{content}' marks possession inside a noun phrase.",
        "This noun phrase uses a possessive element to identify reference.",
        "The phrase '{content}' forms a possessive noun phrase pattern.",
    ],
    "NP_DETERMINER_NOUN": [
        "The phrase '{content}' is a noun phrase built from determiner and noun.",
        "This phrase functions as a noun phrase with a nominal head.",
        "The phrase '{content}' forms a determiner-plus-noun phrase pattern.",
        "This noun phrase combines nominal reference with phrase-level structure.",
        "The phrase '{content}' is a noun phrase centered on a noun head.",
    ],
    "PP_TIME_BEFORE_ING": [
        "The phrase '{content}' marks time with 'before' plus an -ing form.",
        "This phrase is a time prepositional phrase built with 'before' and -ing.",
        "The phrase '{content}' introduces temporal sequencing via 'before' + V-ing.",
        "This prepositional phrase uses 'before' to mark time relation in the clause.",
        "The phrase '{content}' functions as a temporal prepositional modifier.",
    ],
    "PP_GENERAL_LINKING": [
        "The phrase '{content}' is a prepositional phrase linking a complement to the clause.",
        "This phrase functions as a prepositional linker inside sentence structure.",
        "The phrase '{content}' introduces a relation through prepositional structure.",
        "This prepositional phrase connects a complement to another clause element.",
        "The phrase '{content}' acts as a prepositional modifier in context.",
    ],
    "WORD_AUX_MODAL": [
        "'{content}' is a modal auxiliary expressing stance or obligation in the verb phrase.",
        "'{content}' functions as a modal auxiliary in the verbal group.",
        "As a word, '{content}' is a modal auxiliary supporting verb meaning.",
        "'{content}' is an auxiliary modal that marks speaker-oriented modality.",
        "This word, '{content}', is a modal auxiliary within clause grammar.",
    ],
    "WORD_AUX_HAVE": [
        "'{content}' is auxiliary 'have' supporting a perfect verbal construction.",
        "This word, '{content}', functions as perfect auxiliary 'have'.",
        "'{content}' serves as auxiliary 'have' in the verbal group.",
        "As a word, '{content}' marks perfect construction through auxiliary use.",
        "'{content}' is an auxiliary form of 'have' in clause structure.",
    ],
    "WORD_AUX_GENERAL": [
        "'{content}' is an auxiliary verb supporting tense, aspect, mood, or voice.",
        "This word, '{content}', functions as an auxiliary in the verbal group.",
        "'{content}' supports clause grammar as an auxiliary verb form.",
        "As a word, '{content}' is an auxiliary that helps structure the verb phrase.",
        "'{content}' serves as an auxiliary verb in this construction.",
    ],
    "WORD_VERB_PARTICIPLE": [
        "'{content}' is a participle verb form in the verbal construction.",
        "This word, '{content}', functions as a participial verb form.",
        "'{content}' contributes participle morphology to the verb group.",
        "As a word, '{content}' is a participle in clause-level verbal grammar.",
        "'{content}' is used as a participial verb element in context.",
    ],
    "WORD_PRONOUN_POSSESSIVE": [
        "'{content}' is a possessive pronoun or determiner in a noun phrase.",
        "This word, '{content}', marks possession inside the noun phrase.",
        "'{content}' functions as a possessive form modifying nominal reference.",
        "As a word, '{content}' contributes possessive reference in the phrase.",
        "'{content}' is a possessive pronoun/determiner in clause structure.",
    ],
    "WORD_NOUN_COMMON": [
        "'{content}' is a common noun naming an entity in context.",
        "This word, '{content}', functions as a common noun in the clause.",
        "'{content}' serves as a noun that introduces lexical reference.",
        "As a word, '{content}' is a common noun with nominal function.",
        "'{content}' contributes entity reference as a common noun.",
    ],
    "WORD_ARTICLE_DEFINITE": [
        "'{content}' is the definite article introducing an identifiable noun reference.",
        "This word, '{content}', functions as a definite determiner.",
        "'{content}' marks definiteness for the following noun phrase.",
        "As a word, '{content}' is a definite article in nominal structure.",
        "'{content}' contributes definite reference in the noun phrase.",
    ],
    "WORD_PREPOSITION": [
        "'{content}' is a preposition linking a complement to another element.",
        "This word, '{content}', functions as a prepositional linker in the clause.",
        "'{content}' introduces a prepositional relation in context.",
        "As a word, '{content}' is a preposition connecting phrase elements.",
        "'{content}' serves as a preposition in clause-level structure.",
    ],
    "WORD_VERB_ING": [
        "'{content}' is an -ing verb form with non-finite function.",
        "This word, '{content}', functions as a non-finite -ing verb form.",
        "'{content}' contributes an -ing verbal form to the phrase.",
        "As a word, '{content}' is an -ing form in non-finite verb use.",
        "'{content}' is used as a gerund-participle form in context.",
    ],
    "WORD_VERB_FINITE": [
        "'{content}' is a finite verb form functioning as part of the clause predicate.",
        "This word, '{content}', functions as a finite verb in clause structure.",
        "'{content}' contributes finite verbal meaning to the clause.",
        "As a word, '{content}' is a finite verb form in context.",
        "'{content}' serves as a finite verb in the sentence.",
    ],
    "WORD_ADJECTIVE": [
        "'{content}' is an adjective describing a noun or complement in context.",
        "This word, '{content}', functions as an adjective in the clause.",
        "'{content}' contributes descriptive adjectival meaning in the phrase.",
        "As a word, '{content}' is an adjective with modifying function.",
        "'{content}' serves as an adjective in sentence structure.",
    ],
    "WORD_ADVERB": [
        "'{content}' is an adverb modifying a verb, adjective, or clause element.",
        "This word, '{content}', functions as an adverb in context.",
        "'{content}' contributes adverbial meaning to the clause.",
        "As a word, '{content}' is an adverb with modifying function.",
        "'{content}' serves as an adverbial modifier in the sentence.",
    ],
}

SENTENCE_MODAL_PERFECT_VARIANTS: List[str] = [
    "This sentence uses a modal perfect form to express regret or criticism about a past unrealized action.",
    "The sentence shows modal perfect meaning, often evaluating what should have happened in the past.",
    "This sentence encodes modal perfect interpretation about a past action that did not occur as expected.",
]


@dataclass(frozen=True)
class TemplateSelection:
    level: str
    template_id: Optional[str]
    matched_key: Optional[str]
    registry_version: str
    context_key_l1: str
    context_key_l2: str
    context_key_l3: str


def select_template(node: Dict[str, object]) -> TemplateSelection:
    keys = build_context_keys(node)
    if keys["l1"] in REGISTRY_L1:
        return TemplateSelection(
            level="L1_EXACT",
            template_id=REGISTRY_L1[keys["l1"]],
            matched_key=keys["l1"],
            registry_version=REGISTRY_VERSION,
            context_key_l1=keys["l1"],
            context_key_l2=keys["l2"],
            context_key_l3=keys["l3"],
        )
    if keys["l2"] in REGISTRY_L2:
        return TemplateSelection(
            level="L2_DROP_TAM",
            template_id=REGISTRY_L2[keys["l2"]],
            matched_key=keys["l2"],
            registry_version=REGISTRY_VERSION,
            context_key_l1=keys["l1"],
            context_key_l2=keys["l2"],
            context_key_l3=keys["l3"],
        )
    if keys["l3"] in REGISTRY_L3:
        return TemplateSelection(
            level="L3_LEVEL_POS",
            template_id=REGISTRY_L3[keys["l3"]],
            matched_key=keys["l3"],
            registry_version=REGISTRY_VERSION,
            context_key_l1=keys["l1"],
            context_key_l2=keys["l2"],
            context_key_l3=keys["l3"],
        )
    level = keys["l4"]
    return TemplateSelection(
        level="L4_FALLBACK",
        template_id=REGISTRY_L4.get(level),
        matched_key=level,
        registry_version=REGISTRY_VERSION,
        context_key_l1=keys["l1"],
        context_key_l2=keys["l2"],
        context_key_l3=keys["l3"],
    )


def select_template_candidates(node: Dict[str, object]) -> List[TemplateSelection]:
    keys = build_context_keys(node)
    out: List[TemplateSelection] = []
    if keys["l1"] in REGISTRY_L1:
        out.append(
            TemplateSelection(
                level="L1_EXACT",
                template_id=REGISTRY_L1[keys["l1"]],
                matched_key=keys["l1"],
                registry_version=REGISTRY_VERSION,
                context_key_l1=keys["l1"],
                context_key_l2=keys["l2"],
                context_key_l3=keys["l3"],
            )
        )
    if keys["l2"] in REGISTRY_L2:
        out.append(
            TemplateSelection(
                level="L2_DROP_TAM",
                template_id=REGISTRY_L2[keys["l2"]],
                matched_key=keys["l2"],
                registry_version=REGISTRY_VERSION,
                context_key_l1=keys["l1"],
                context_key_l2=keys["l2"],
                context_key_l3=keys["l3"],
            )
        )
    if keys["l3"] in REGISTRY_L3:
        out.append(
            TemplateSelection(
                level="L3_LEVEL_POS",
                template_id=REGISTRY_L3[keys["l3"]],
                matched_key=keys["l3"],
                registry_version=REGISTRY_VERSION,
                context_key_l1=keys["l1"],
                context_key_l2=keys["l2"],
                context_key_l3=keys["l3"],
            )
        )
    out.append(
        TemplateSelection(
            level="L4_FALLBACK",
            template_id=REGISTRY_L4.get(keys["l4"]),
            matched_key=keys["l4"],
            registry_version=REGISTRY_VERSION,
            context_key_l1=keys["l1"],
            context_key_l2=keys["l2"],
            context_key_l3=keys["l3"],
        )
    )
    uniq: List[TemplateSelection] = []
    seen = set()
    for item in out:
        key = (item.level, item.template_id, item.matched_key)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def is_template_semantically_compatible(node: Dict[str, object], template_id: str) -> bool:
    level = _norm(node.get("type"))
    pos = _norm(node.get("part_of_speech"))
    dep = _dep(node)
    content = _norm(node.get("content"))
    toks = _tokens(content)
    first = toks[0] if toks else ""
    tam = _tam(node)

    if not template_id:
        return False

    if level == "sentence":
        if template_id == "CLAUSE_SUBORDINATE_CONCESSION":
            return first in {"although", "though", "even"}
        if template_id == "CLAUSE_SUBORDINATE_REASON":
            return first in {"because", "since", "as"}
        if template_id == "CLAUSE_SUBORDINATE_TIME":
            return first in {"before", "after", "when", "while"}
        return template_id == "SENTENCE_FINITE_CLAUSE"

    if level == "phrase":
        if template_id == "PP_TIME_BEFORE_ING":
            return "prepositional phrase" in pos and first == "before" and any(t.endswith("ing") for t in toks[1:])
        if template_id == "PP_GENERAL_LINKING":
            return "prepositional phrase" in pos
        if template_id == "NP_POSSESSIVE":
            return "noun phrase" in pos and any(t in POSSESSIVES for t in toks)
        if template_id == "NP_DETERMINER_NOUN":
            return "noun phrase" in pos
        if template_id == "VP_MODAL_PERFECT":
            return "verb phrase" in pos and tam == "modal_perfect"
        if template_id in {"VP_AUXILIARY", "VP_PARTICIPLE"}:
            return "verb phrase" in pos
        return True

    if level == "word":
        if template_id == "WORD_AUX_MODAL":
            return pos == "auxiliary verb" and first in MODAL_AUX
        if template_id == "WORD_AUX_HAVE":
            return pos == "auxiliary verb" and first == "have"
        if template_id == "WORD_AUX_GENERAL":
            return pos == "auxiliary verb"
        if template_id == "WORD_VERB_ING":
            tense = _norm(node.get("tense"))
            return pos == "verb" and (first.endswith("ing") or "present participle" in tense)
        if template_id == "WORD_VERB_PARTICIPLE":
            tense = _norm(node.get("tense"))
            return pos == "verb" and "participle" in tense
        if template_id == "WORD_VERB_FINITE":
            tense = _norm(node.get("tense"))
            return pos == "verb" and "participle" not in tense
        if template_id == "WORD_PRONOUN_POSSESSIVE":
            return pos == "pronoun" and (dep == "poss" or first in POSSESSIVES)
        if template_id == "WORD_NOUN_COMMON":
            return pos in {"noun", "proper noun"}
        if template_id == "WORD_ARTICLE_DEFINITE":
            return pos in {"article", "determiner"} and first == "the"
        if template_id == "WORD_PREPOSITION":
            return pos == "preposition"
        if template_id == "WORD_ADJECTIVE":
            return pos == "adjective"
        if template_id == "WORD_ADVERB":
            return pos == "adverb"
        return True

    return True


def _variant_index(template_id: str, content: str, matched_key: str, modulo: int) -> int:
    payload = f"{template_id}|{_norm(content)}|{matched_key}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(digest[:8], 16) % max(1, modulo)


def render_template_note(template_id: str, node: Dict[str, object], matched_key: str) -> str:
    if template_id == "SENTENCE_FINITE_CLAUSE" and _tam(node) == "modal_perfect":
        idx = _variant_index(template_id, str(node.get("content", "")), matched_key or "", len(SENTENCE_MODAL_PERFECT_VARIANTS))
        return sanitize_note(SENTENCE_MODAL_PERFECT_VARIANTS[idx])
    variants = TEMPLATE_VARIANTS.get(template_id) or []
    if not variants:
        return ""
    content = str(node.get("content", "")).strip()
    idx = _variant_index(template_id, content, matched_key or "", len(variants))
    raw = variants[idx].format(content=content)
    return sanitize_note(raw)
