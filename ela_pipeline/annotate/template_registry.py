"""Deterministic template registry and hierarchical context matching."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from ela_pipeline.validation.notes_quality import sanitize_note

REGISTRY_VERSION = "v2"

MODAL_AUX = {"should", "could", "would", "might", "may", "must", "can", "will", "shall"}
POSSESSIVES = {"my", "your", "his", "her", "our", "their", "its"}

_TOKEN_RE = re.compile(r"[A-Za-z']+")


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(_norm(text))


def _has_pair(text: str, left: str, right: str) -> bool:
    return left in text and right in text


def _has_question_mark(text: str) -> bool:
    return "?" in str(text or "")


def _has_question_tag(text: str) -> bool:
    lowered = _norm(text)
    if "?" not in str(text or ""):
        return False
    return bool(
        re.search(
            r",\s*(?:am|is|are|was|were|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must)"
            r"(?:n't| not)?\s+[a-z']+\s*\?$",
            lowered,
        )
    )


def _looks_wh_question(text: str) -> bool:
    lowered = _norm(text)
    return _has_question_mark(text) and bool(
        re.match(r"^(who|what|when|where|why|how|which|whom|whose)\b", lowered)
    )


def _looks_yes_no_question(text: str) -> bool:
    lowered = _norm(text)
    return _has_question_mark(text) and bool(
        re.match(
            r"^(am|is|are|was|were|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must)\b",
            lowered,
        )
    )


def _looks_do_support_yes_no_question(text: str) -> bool:
    lowered = _norm(text)
    return _has_question_mark(text) and bool(re.match(r"^(do|does|did)\b", lowered))


def _is_existential_there(text: str) -> bool:
    lowered = _norm(text)
    return bool(re.match(r"^there\s+(is|are|was|were|has been|have been|had been|will be|would be)\b", lowered))


def _is_extraposition_it_that(text: str) -> bool:
    lowered = _norm(text)
    return bool(re.match(r"^it\s+(is|was|seems|appears|became|becomes|remains)\b", lowered)) and " that " in f" {lowered} "


def _is_it_cleft(text: str) -> bool:
    lowered = _norm(text)
    return bool(re.match(r"^it\s+(is|was)\b", lowered)) and (" who " in f" {lowered} " or " that " in f" {lowered} ")


def _is_imperative(text: str) -> bool:
    lowered = _norm(text)
    if not lowered or _has_question_mark(text):
        return False
    if lowered.startswith(("please ", "do not ", "don't ")):
        return True
    toks = _tokens(lowered)
    if not toks:
        return False
    return toks[0] in {
        "be",
        "come",
        "consider",
        "do",
        "go",
        "keep",
        "let",
        "look",
        "make",
        "please",
        "remember",
        "stop",
        "take",
        "tell",
        "try",
        "use",
        "wait",
        "write",
    }


def _is_exclamative(text: str) -> bool:
    lowered = _norm(text)
    raw = str(text or "")
    return raw.endswith("!") or lowered.startswith(("what ", "how "))


def _has_that_clause(text: str) -> bool:
    lowered = _norm(text)
    return " that " in f" {lowered} "


def _has_wh_clause(text: str) -> bool:
    lowered = _norm(text)
    return bool(re.search(r"\b(who|what|when|where|why|how|which|whether|if)\b", lowered))


def _has_if_clause(text: str) -> bool:
    lowered = _norm(text)
    return lowered.startswith("if ") or " if " in f" {lowered} "


def _has_modal(text: str) -> bool:
    toks = _tokens(text)
    return any(tok in MODAL_AUX for tok in toks)


def _has_perfect(text: str) -> bool:
    lowered = _norm(text)
    return bool(re.search(r"\b(has|have|had)\s+\w+(ed|en|n)\b", lowered))


def _has_progressive(text: str) -> bool:
    lowered = _norm(text)
    return bool(re.search(r"\b(am|is|are|was|were|be|been|being)\s+\w+ing\b", lowered))


def _has_passive(text: str) -> bool:
    lowered = _norm(text)
    return bool(re.search(r"\b(am|is|are|was|were|be|been|being|get|gets|got)\s+\w+(ed|en|n)\b", lowered))


def _is_relative_clause(text: str) -> bool:
    lowered = _norm(text)
    return bool(re.search(r"\b(who|whom|whose|which|that|where|when)\b", lowered))


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
    if level == "phrase" and pos in {"phrasal verb", "idiom", "collocation", "clause chunk"}:
        # Keep deterministic template coverage for richer phrase types by mapping
        # them into the existing verb-phrase template lattice.
        pos = "verb phrase"
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

TEMPLATE_VARIANTS.update(
    {
        "SENT_DECLARATIVE": [
            "This sentence is a declarative clause used to present information or make a statement.",
            "The sentence has declarative clause structure, which is the default pattern for statements.",
            "This sentence uses declarative word order to present a statement rather than a question or command.",
        ],
        "SENT_ACTIVE_VOICE": [
            "This sentence uses the active voice, so the subject is presented as the doer or experiencer of the process.",
            "The clause is active rather than passive: the subject is linked directly to the event.",
            "This sentence stays in the active voice instead of promoting an object into subject position.",
        ],
        "SENT_NEGATION_GENERAL": [
            "This sentence includes clause-level negation, which makes the proposition negative rather than affirmative.",
            "The clause is negative: a negator is used to deny or reverse the positive statement.",
            "This sentence marks negation at clause level, changing the polarity of the statement.",
        ],
        "SENT_NEGATION_DO_SUPPORT": [
            "This sentence uses do-support to carry negation in a clause without another auxiliary.",
            "Negation here is built with do-support, because the main verb cannot take 'not' by itself.",
            "The clause uses an auxiliary form of 'do' to support negation.",
        ],
        "SENT_NEGATION_AUXILIARY": [
            "This sentence expresses negation through an auxiliary or modal rather than through do-support.",
            "The negative meaning is attached to an auxiliary element in the clause.",
            "This clause uses an auxiliary-based negative pattern instead of plain do-support.",
        ],
        "SENT_MODAL_PERFECT": [
            "This sentence uses a modal perfect form to express regret or criticism about a past unrealized action.",
            "The sentence shows modal perfect meaning, often evaluating what should have happened in the past.",
            "This sentence encodes modal perfect interpretation about a past action that did not occur as expected.",
        ],
        "SENT_MODAL_GENERAL": [
            "This sentence uses a modal auxiliary to add meaning such as possibility, necessity, prediction, or obligation.",
            "A modal auxiliary shapes the speaker's stance toward the event in this clause.",
            "This clause includes modal meaning through an auxiliary like can, may, must, or will.",
        ],
        "SENT_PERFECT_GENERAL": [
            "This sentence uses the perfect to connect an earlier event or state to a later reference point.",
            "The perfect construction looks back from a reference time to something already completed or still relevant.",
            "This clause uses a perfect form to relate two time points rather than presenting an event as simple and isolated.",
        ],
        "SENT_PROGRESSIVE_GENERAL": [
            "This sentence uses the progressive to present the situation as ongoing, developing, or in progress.",
            "The progressive construction views the event from the inside as something continuing through time.",
            "This clause uses a progressive form rather than presenting the event as a simple whole.",
        ],
        "SENT_QUESTION_WH": [
            "This sentence is a wh-question, so it asks for specific missing information rather than just yes or no.",
            "The clause is built as a wh-question, with a question word directing the kind of information requested.",
            "This sentence uses a wh-word to ask for a specific piece of information.",
        ],
        "SENT_QUESTION_WH_DO_SUPPORT": [
            "This wh-question uses do-support because the clause has no other auxiliary available for inversion.",
            "The sentence combines a wh-question pattern with do-support in the auxiliary position.",
            "This wh-question relies on do-support to build the interrogative structure.",
        ],
        "SENT_QUESTION_YES_NO_AUX": [
            "This sentence is a yes/no question built through subject-auxiliary inversion.",
            "The clause forms a yes/no question by placing the auxiliary before the subject.",
            "This sentence asks for confirmation rather than specific information, using inversion to form the question.",
        ],
        "SENT_QUESTION_YES_NO_DO_SUPPORT": [
            "This yes/no question uses do-support because the main verb cannot invert on its own.",
            "The sentence forms a yes/no question with an auxiliary form of 'do'.",
            "This clause uses do-support plus inversion to create a yes/no question.",
        ],
        "SENT_QUESTION_TAG": [
            "This sentence ends with a question tag, which turns a statement into a request for confirmation or response.",
            "The clause uses a question tag: an auxiliary and pronoun are added after the main statement.",
            "This sentence adds a question tag to check agreement, confirmation, or involvement from the listener.",
        ],
        "SENT_EXISTENTIAL_THERE": [
            "This sentence uses existential there to introduce the existence or presence of something.",
            "The clause uses existential there to present something as existing, appearing, or being present.",
            "This sentence begins with existential there, which introduces a new entity into the discourse.",
        ],
        "SENT_EXISTENTIAL_THERE_AGREEMENT": [
            "This existential clause shows agreement between the verb and the notional subject that follows there.",
            "In existential there constructions, the verb agrees with the noun phrase that comes after it.",
            "This sentence uses existential there and shows how agreement depends on the following noun phrase.",
        ],
        "SENT_EXISTENTIAL_THERE_QUESTION": [
            "This sentence turns an existential there construction into a question through inversion.",
            "The clause is an interrogative version of existential there, asking whether something exists or is present.",
            "This sentence combines existential there with question structure.",
        ],
        "SENT_NOUN_CLAUSE_THAT": [
            "This sentence contains a that-clause used as a content clause inside a larger clause.",
            "The clause includes a that-clause which packages a proposition as the content of another verb or predicate.",
            "This sentence uses a that-clause to turn a statement into a clause-level content unit.",
        ],
        "SENT_NOUN_CLAUSE_WH": [
            "This sentence contains a wh-clause functioning as a content clause inside the larger structure.",
            "The clause includes an embedded wh-clause that represents information as a clause-level object or complement.",
            "This sentence uses a wh-clause not as a direct question, but as embedded clause content.",
        ],
        "SENT_EXTRAPOSITION_IT_THAT": [
            "This sentence uses preparatory it and shifts the that-clause to a later position in the sentence.",
            "The clause uses extraposition: 'it' appears in subject position while the heavier that-clause is postponed.",
            "This sentence delays a that-clause by using preparatory it as a structural placeholder.",
        ],
        "SENT_PASSIVE_GENERAL": [
            "This sentence uses the passive voice, so the affected participant is foregrounded rather than the doer.",
            "The clause is passive: the subject receives the action instead of performing it.",
            "This sentence uses a passive construction to focus on the affected entity or result.",
        ],
        "SENT_PASSIVE_AGENTLESS": [
            "This sentence uses an agentless passive, leaving the doer unstated because it is unknown, unimportant, or obvious.",
            "The clause is passive and omits the performer of the action.",
            "This passive sentence focuses on the result or affected participant without naming the agent.",
        ],
        "SENT_PASSIVE_REPORTING_IT": [
            "This sentence uses a reporting passive with preparatory it to present information impersonally.",
            "The clause combines passive reporting with preparatory it, creating a detached reporting structure.",
            "This sentence uses an impersonal passive reporting pattern instead of naming an explicit reporter.",
        ],
        "SENT_PASSIVE_PROGRESSIVE": [
            "This sentence combines passive voice with progressive aspect to show an ongoing affected process.",
            "The clause is progressive passive, viewing a passive event as unfolding through time.",
            "This sentence uses a passive progressive form rather than a simple passive.",
        ],
        "SENT_PASSIVE_PERFECT": [
            "This sentence combines passive voice with the perfect to connect a completed affected event to a reference point.",
            "The clause is a perfect passive construction rather than a simple active or simple passive clause.",
            "This sentence uses a passive perfect form to look back on an earlier affected event.",
        ],
        "SENT_TIME_CLAUSE_FUTURE_REFERENCE": [
            "This sentence uses a time clause to refer to the future, even though the subordinate clause often stays in a present form.",
            "The clause shows future reference through a time subordinate clause rather than by using will in both clauses.",
            "This sentence uses a future-oriented time clause, where English usually avoids a full future form in the subordinate clause.",
        ],
        "SENT_CONDITIONAL_GENERAL": [
            "This sentence is conditional: it links a condition with a result rather than presenting a simple independent fact.",
            "The clause expresses a condition-result relation between two linked parts of the sentence.",
            "This sentence uses a conditional structure to show how one situation depends on another.",
        ],
        "SENT_CONDITIONAL_PRESENT_MODAL": [
            "This sentence uses a conditional pattern with a present condition and a modal result.",
            "The clause links a present or general condition to a result expressed with a modal auxiliary.",
            "This sentence builds a conditional meaning through an if-clause and a modal main clause.",
        ],
        "SENT_CONDITIONAL_FIRST": [
            "This sentence is a first conditional, presenting a realistic future possibility and its result.",
            "The clause uses a first conditional pattern to connect a likely future condition with a likely result.",
            "This sentence uses the first conditional to talk about a possible future outcome.",
        ],
        "SENT_CONDITIONAL_SECOND": [
            "This sentence is a second conditional, used for unreal, remote, or hypothetical situations.",
            "The clause uses a second conditional pattern to discuss a hypothetical present or future situation.",
            "This sentence presents a non-factual or unlikely condition and its imagined result.",
        ],
        "SENT_CONDITIONAL_THIRD": [
            "This sentence is a third conditional, referring to an unreal past condition and its unrealized result.",
            "The clause uses a third conditional pattern to imagine a different past and its consequence.",
            "This sentence presents a counterfactual past condition with a counterfactual result.",
        ],
        "SENT_CONDITIONAL_ZERO": [
            "This sentence is a zero conditional, expressing a general truth, rule, or regular consequence.",
            "The clause uses a zero conditional pattern for predictable or habitual relations.",
            "This sentence links a condition and result as a general fact rather than a one-time event.",
        ],
        "SENT_CONDITIONAL_COUNTERFACTUAL": [
            "This sentence uses a counterfactual conditional to describe an unreal situation.",
            "The clause presents a condition that is contrary to fact rather than open or factual.",
            "This sentence uses conditional structure for a situation the speaker treats as unreal.",
        ],
        "SENT_CONDITIONAL_COUNTERFACTUAL_PAST": [
            "This sentence uses a past counterfactual conditional to imagine a different past outcome.",
            "The clause refers to an unreal past condition and a result that did not happen.",
            "This sentence expresses a counterfactual past relationship between condition and result.",
        ],
        "SENT_CONDITIONAL_FACTUAL": [
            "This sentence uses a factual conditional, where the speaker treats the condition as open or real rather than unreal.",
            "The clause presents a condition-result relation without marking the condition as counterfactual.",
            "This sentence uses conditional structure for a factual or realistic relation.",
        ],
        "SENT_CONDITIONAL_NECESSARY_CONDITION": [
            "This sentence expresses a necessary-condition relation rather than a simple if-then prediction.",
            "The clause marks one situation as required for another to hold.",
            "This sentence uses conditional structure to state a necessary condition.",
        ],
        "SENT_CONDITIONAL_CONCESSIVE": [
            "This sentence uses a concessive conditional such as even if, where the main result holds despite the condition.",
            "The clause combines conditional structure with concession rather than simple dependence.",
            "This sentence uses a concessive conditional to show that the result remains true whatever the condition is.",
        ],
        "SENT_CONDITIONAL_FORMAL_SHOULD": [
            "This sentence uses a formal conditional pattern with should in the if-clause.",
            "The clause uses a formal should-conditional instead of a more neutral if-clause pattern.",
            "This sentence marks a formal conditional meaning through should in the subordinate clause.",
        ],
        "SENT_CONDITIONAL_IMPERATIVE_RESULT": [
            "This sentence uses a conditional whose result clause is an imperative rather than a statement.",
            "The clause links a condition to a command or instruction in the main clause.",
            "This sentence combines conditional structure with an imperative result.",
        ],
        "SENT_CONDITIONAL_PREDICTIVE": [
            "This sentence uses a predictive conditional to connect a condition with a likely future result.",
            "The clause presents a condition and predicts the consequence if it is met.",
            "This sentence uses conditional structure to forecast an outcome.",
        ],
        "SENT_CLEFT_IT": [
            "This sentence uses an it-cleft to foreground one element and give it special informational focus.",
            "The clause is an it-cleft, which highlights a particular constituent rather than leaving the sentence unmarked.",
            "This sentence uses cleft structure to place focus on one selected part of the message.",
        ],
        "SENT_IMPERATIVE": [
            "This sentence is imperative, so it gives a command, instruction, invitation, or directive.",
            "The clause uses imperative structure rather than making a statement or asking a question.",
            "This sentence is built as an imperative, typically with an implied subject rather than an overt one.",
        ],
        "SENT_EXCLAMATIVE": [
            "This sentence is exclamative, so it expresses strong reaction or evaluation rather than simple statement.",
            "The clause uses exclamative structure to add emphasis or emotional force.",
            "This sentence is built as an exclamative rather than an ordinary declarative clause.",
        ],
        "PHRASE_PP_GENERAL": [
            "This phrase is a prepositional phrase headed by a preposition and followed by its complement.",
            "The phrase forms a prepositional phrase, linking its complement to the wider clause.",
            "This phrase uses a preposition to build a relation between its complement and another part of the sentence.",
        ],
        "PHRASE_PP_LOCATION": [
            "This phrase is a prepositional phrase expressing location or spatial position.",
            "The phrase functions as a locative prepositional phrase in the sentence.",
            "This prepositional phrase locates something in space rather than in time or cause.",
        ],
        "PHRASE_PP_TIME": [
            "This phrase is a prepositional phrase expressing time or temporal setting.",
            "The phrase functions as a temporal prepositional phrase in the clause.",
            "This prepositional phrase places the event in time rather than in space.",
        ],
        "PHRASE_PP_SOURCE": [
            "This phrase is a prepositional phrase expressing source or origin.",
            "The phrase functions as a source-oriented prepositional phrase in the sentence.",
            "This prepositional phrase marks where something comes from or originates.",
        ],
        "PHRASE_PP_PURPOSE": [
            "This phrase is a prepositional phrase expressing purpose or intended use.",
            "The phrase functions as a purpose-related prepositional phrase in the clause.",
            "This prepositional phrase marks what something is for rather than where or when.",
        ],
        "PHRASE_PP_AGENT": [
            "This phrase is a prepositional phrase marking the agent or performer, especially in passive constructions.",
            "The phrase functions as an agent phrase, identifying who performs the action.",
            "This prepositional phrase marks the performer rather than the affected participant.",
        ],
        "PHRASE_PP_MEANS": [
            "This phrase is a prepositional phrase expressing means, method, or instrument.",
            "The phrase functions as a means-related prepositional phrase in the clause.",
            "This prepositional phrase shows how something is done rather than where or when it happens.",
        ],
        "PHRASE_PP_ASSOCIATION": [
            "This phrase is a prepositional phrase expressing association, accompaniment, or relation.",
            "The phrase functions as an associative prepositional phrase in the clause.",
            "This prepositional phrase links one participant or thing with another.",
        ],
        "PHRASE_RELATIVE_CLAUSE": [
            "This phrase is a relative clause modifying a noun or noun phrase.",
            "The phrase functions as a relative clause that adds information about a noun.",
            "This relative clause is attached to a nominal expression and helps identify or describe it.",
        ],
        "PHRASE_RELATIVE_CLAUSE_RESTRICTIVE": [
            "This phrase is a restrictive relative clause, so it helps identify which person or thing is meant.",
            "The relative clause is restrictive: it narrows the reference of the noun it modifies.",
            "This phrase uses a restrictive relative clause to define the noun more precisely.",
        ],
        "PHRASE_RELATIVE_CLAUSE_NONRESTRICTIVE": [
            "This phrase is a non-restrictive relative clause, so it adds extra information instead of identifying the noun.",
            "The relative clause is non-restrictive: it comments on the noun rather than narrowing its reference.",
            "This phrase uses a non-restrictive relative clause to add supplementary information.",
        ],
        "PHRASE_RELATIVE_CLAUSE_STRANDED_PREP": [
            "This phrase is a relative clause with a stranded preposition left later in the clause.",
            "The relative clause keeps the preposition inside the clause rather than moving it before the relative marker.",
            "This phrase uses preposition stranding inside a relative clause.",
        ],
        "PHRASE_RELATIVE_CLAUSE_FRONTED_PREP": [
            "This phrase is a relative clause with a fronted preposition placed before the relative marker.",
            "The relative clause moves the preposition to the front of the relative construction.",
            "This phrase uses a fronted-preposition relative clause rather than preposition stranding.",
        ],
        "PHRASE_VP_GENERAL": [
            "This phrase is a verb phrase built around a lexical verb and any auxiliaries, complements, or modifiers.",
            "The phrase functions as a verb phrase rather than as a noun phrase or prepositional phrase.",
            "This verbal phrase organizes the core verbal material of the clause.",
        ],
        "PHRASE_VP_PHRASAL_VERB": [
            "This phrase is a phrasal verb, where the verb combines with a particle to create a unit of meaning.",
            "The phrase functions as a phrasal verb rather than a simple verb plus ordinary adverb.",
            "This verb phrase includes a particle that forms part of the verbal unit.",
        ],
        "PHRASE_VP_COLLOCATION": [
            "This phrase is a fixed or semi-fixed verbal collocation rather than a freely combined phrase.",
            "The verb phrase works as a recurring collocational unit in English usage.",
            "This phrase shows a conventional verb-based combination rather than an arbitrary wording choice.",
        ],
        "PHRASE_VP_MODAL": [
            "This phrase is a modal or semi-modal verb phrase expressing stance such as ability, necessity, or prediction.",
            "The verb phrase includes modal meaning rather than just lexical event meaning.",
            "This phrase uses a modal or semi-modal element to shape how the event is interpreted.",
        ],
        "PHRASE_VP_PROGRESSIVE": [
            "This phrase is a progressive verb phrase presenting the event as ongoing or in progress.",
            "The verbal phrase uses progressive aspect rather than a simple form.",
            "This phrase views the event from the inside as something continuing through time.",
        ],
        "PHRASE_VP_PERFECT": [
            "This phrase is a perfect verb phrase linking an earlier event to a later reference point.",
            "The verbal phrase uses the perfect rather than a simple tense form.",
            "This phrase looks back from a reference time to something already completed or still relevant.",
        ],
        "PHRASE_VP_PERFECT_PROGRESSIVE": [
            "This phrase combines perfect and progressive meaning in the same verb phrase.",
            "The verbal phrase is perfect progressive, linking earlier time with ongoing duration.",
            "This phrase combines retrospective reference with an ongoing viewpoint.",
        ],
        "PHRASE_VP_PASSIVE": [
            "This phrase is a passive verb phrase, foregrounding the affected participant rather than the doer.",
            "The verbal phrase uses passive voice instead of presenting the subject as the agent.",
            "This phrase builds passive meaning inside the verb phrase.",
        ],
        "PHRASE_VP_INFINITIVE": [
            "This phrase is an infinitive verb phrase, so it uses a non-finite verbal form rather than a finite clause.",
            "The verbal phrase is infinitival, functioning as a non-finite unit in the larger sentence.",
            "This phrase uses an infinitive construction rather than a fully finite clause.",
        ],
        "PHRASE_VP_ING_NONFINITE": [
            "This phrase is a non-finite -ing verb phrase rather than a finite clause.",
            "The verbal phrase uses an -ing form to build a non-finite construction.",
            "This phrase is an -ing verb phrase functioning as a non-finite unit in the sentence.",
        ],
    }
)

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
    raw_content = str(node.get("content") or "")
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
        if template_id == "SENT_DECLARATIVE":
            return not _has_question_mark(raw_content) and not _is_imperative(raw_content) and not _is_exclamative(raw_content)
        if template_id == "SENT_ACTIVE_VOICE":
            return not _has_passive(raw_content)
        if template_id == "SENT_NEGATION_GENERAL":
            return " not " in f" {content} " or "n't" in content
        if template_id == "SENT_NEGATION_DO_SUPPORT":
            return bool(re.search(r"\b(do|does|did)\s+not\b", content)) or bool(re.search(r"\b(do|does|did)n't\b", content))
        if template_id == "SENT_NEGATION_AUXILIARY":
            return (" not " in f" {content} " or "n't" in content) and _has_modal(raw_content)
        if template_id == "SENT_MODAL_PERFECT":
            return _tam(node) == "modal_perfect" or (_has_modal(raw_content) and _has_perfect(raw_content))
        if template_id == "SENT_MODAL_GENERAL":
            return _has_modal(raw_content)
        if template_id == "SENT_PERFECT_GENERAL":
            return _has_perfect(raw_content)
        if template_id == "SENT_PROGRESSIVE_GENERAL":
            return _has_progressive(raw_content)
        if template_id == "SENT_QUESTION_WH":
            return _looks_wh_question(raw_content)
        if template_id == "SENT_QUESTION_WH_DO_SUPPORT":
            return _looks_wh_question(raw_content) and bool(re.search(r"\b(do|does|did)\b", content))
        if template_id == "SENT_QUESTION_YES_NO_AUX":
            return _looks_yes_no_question(raw_content)
        if template_id == "SENT_QUESTION_YES_NO_DO_SUPPORT":
            return _looks_do_support_yes_no_question(raw_content)
        if template_id == "SENT_QUESTION_TAG":
            return _has_question_tag(raw_content)
        if template_id in {"SENT_EXISTENTIAL_THERE", "SENT_EXISTENTIAL_THERE_AGREEMENT"}:
            return _is_existential_there(raw_content)
        if template_id == "SENT_EXISTENTIAL_THERE_QUESTION":
            return _has_question_mark(raw_content) and "there" in toks
        if template_id == "SENT_NOUN_CLAUSE_THAT":
            return _has_that_clause(raw_content)
        if template_id == "SENT_NOUN_CLAUSE_WH":
            return _has_wh_clause(raw_content) and not _looks_wh_question(raw_content)
        if template_id == "SENT_EXTRAPOSITION_IT_THAT":
            return _is_extraposition_it_that(raw_content)
        if template_id in {
            "SENT_PASSIVE_GENERAL",
            "SENT_PASSIVE_AGENTLESS",
            "SENT_PASSIVE_REPORTING_IT",
            "SENT_PASSIVE_PROGRESSIVE",
            "SENT_PASSIVE_PERFECT",
        }:
            if not _has_passive(raw_content):
                return False
            if template_id == "SENT_PASSIVE_AGENTLESS":
                return " by " not in f" {content} "
            if template_id == "SENT_PASSIVE_REPORTING_IT":
                return _is_extraposition_it_that(raw_content) or raw_content.lower().startswith("it ")
            if template_id == "SENT_PASSIVE_PROGRESSIVE":
                return _has_progressive(raw_content)
            if template_id == "SENT_PASSIVE_PERFECT":
                return _has_perfect(raw_content)
            return True
        if template_id == "SENT_TIME_CLAUSE_FUTURE_REFERENCE":
            return first in {"when", "before", "after", "until", "once", "as", "while"}
        if template_id.startswith("SENT_CONDITIONAL_"):
            if not _has_if_clause(raw_content):
                return False
            if template_id == "SENT_CONDITIONAL_PRESENT_MODAL":
                return _has_modal(raw_content)
            if template_id == "SENT_CONDITIONAL_SECOND":
                return " would " in f" {content} " or "could " in content or "might " in content
            if template_id == "SENT_CONDITIONAL_THIRD":
                return "would have" in content or "could have" in content or "might have" in content
            if template_id == "SENT_CONDITIONAL_ZERO":
                return " will " not in f" {content} " and " would " not in f" {content} "
            if template_id == "SENT_CONDITIONAL_CONCESSIVE":
                return "even if" in content
            if template_id == "SENT_CONDITIONAL_FORMAL_SHOULD":
                return raw_content.lower().startswith("should ")
            if template_id == "SENT_CONDITIONAL_IMPERATIVE_RESULT":
                return "if " in content and "!" in raw_content
            return True
        if template_id == "SENT_CLEFT_IT":
            return _is_it_cleft(raw_content)
        if template_id == "SENT_IMPERATIVE":
            return _is_imperative(raw_content)
        if template_id == "SENT_EXCLAMATIVE":
            return _is_exclamative(raw_content)
        return template_id == "SENTENCE_FINITE_CLAUSE"

    if level == "phrase":
        verbal_phrase_like = {"verb phrase", "phrasal verb", "idiom", "collocation", "clause chunk"}
        if template_id == "PP_TIME_BEFORE_ING":
            return "prepositional phrase" in pos and first == "before" and any(t.endswith("ing") for t in toks[1:])
        if template_id == "PP_GENERAL_LINKING":
            return "prepositional phrase" in pos
        if template_id.startswith("PHRASE_PP_"):
            if "prepositional phrase" not in pos:
                return False
            if template_id == "PHRASE_PP_LOCATION":
                return first in {"at", "in", "on", "under", "over", "near", "behind", "beside", "inside", "outside"}
            if template_id == "PHRASE_PP_TIME":
                return first in {"at", "on", "in", "during", "after", "before", "since", "until"}
            if template_id == "PHRASE_PP_SOURCE":
                return first in {"from", "out", "off"}
            if template_id == "PHRASE_PP_PURPOSE":
                return first in {"for", "to"}
            if template_id == "PHRASE_PP_AGENT":
                return first == "by"
            if template_id == "PHRASE_PP_MEANS":
                return first in {"by", "with", "through"}
            if template_id == "PHRASE_PP_ASSOCIATION":
                return first in {"with", "without", "together"}
            return True
        if template_id == "NP_POSSESSIVE":
            return "noun phrase" in pos and any(t in POSSESSIVES for t in toks)
        if template_id == "NP_DETERMINER_NOUN":
            return "noun phrase" in pos
        if template_id == "VP_MODAL_PERFECT":
            return pos in verbal_phrase_like and tam == "modal_perfect"
        if template_id in {"VP_AUXILIARY", "VP_PARTICIPLE"}:
            return pos in verbal_phrase_like
        if template_id.startswith("PHRASE_RELATIVE_CLAUSE"):
            if "relative clause" not in pos and not _is_relative_clause(raw_content):
                return False
            if template_id == "PHRASE_RELATIVE_CLAUSE_STRANDED_PREP":
                return bool(re.search(r"\b(who|which|that)\b.*\b(at|for|to|with|about|of|in|on|from)\b$", content))
            if template_id == "PHRASE_RELATIVE_CLAUSE_FRONTED_PREP":
                return bool(re.match(r"^(at|for|to|with|about|of|in|on|from)\s+(which|whom)\b", content))
            if template_id == "PHRASE_RELATIVE_CLAUSE_NONRESTRICTIVE":
                return raw_content.startswith(",") or raw_content.endswith(",")
            return True
        if template_id.startswith("PHRASE_VP_"):
            if pos not in verbal_phrase_like:
                return False
            if template_id == "PHRASE_VP_PHRASAL_VERB":
                return "phrasal verb" in pos or len(toks) >= 2 and toks[-1] in {"up", "out", "off", "in", "on", "away", "back", "down"}
            if template_id == "PHRASE_VP_COLLOCATION":
                return "collocation" in pos or "idiom" in pos
            if template_id == "PHRASE_VP_MODAL":
                return _has_modal(raw_content) or first in {"have", "has", "had", "need", "ought"}
            if template_id == "PHRASE_VP_PROGRESSIVE":
                return _has_progressive(raw_content)
            if template_id == "PHRASE_VP_PERFECT":
                return _has_perfect(raw_content)
            if template_id == "PHRASE_VP_PERFECT_PROGRESSIVE":
                return _has_perfect(raw_content) and _has_progressive(raw_content)
            if template_id == "PHRASE_VP_PASSIVE":
                return _has_passive(raw_content)
            if template_id == "PHRASE_VP_INFINITIVE":
                return first == "to" or raw_content.lower().startswith("to ")
            if template_id == "PHRASE_VP_ING_NONFINITE":
                return first.endswith("ing") or any(tok.endswith("ing") for tok in toks)
            return True
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


def all_template_ids() -> List[str]:
    ids = set(TEMPLATE_VARIANTS.keys())
    ids.update({"CLAUSE_SUBORDINATE_TIME", "CLAUSE_SUBORDINATE_REASON", "CLAUSE_SUBORDINATE_CONCESSION"})
    return sorted(ids)
