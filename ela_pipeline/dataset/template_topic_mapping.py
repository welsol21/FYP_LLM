"""Shared topic-to-template mapping for projected note corpora."""

from __future__ import annotations

from typing import Final


SENTENCE_TOPIC_TO_TEMPLATE: Final[dict[str, str]] = {
    "declarative": "SENT_DECLARATIVE",
    "active": "SENT_ACTIVE_VOICE",
    "negative clause": "SENT_NEGATION_GENERAL",
    "do-support negative clause": "SENT_NEGATION_DO_SUPPORT",
    "negation and modals": "SENT_NEGATION_AUXILIARY",
    "modal": "SENT_MODAL_GENERAL",
    "perfect": "SENT_PERFECT_GENERAL",
    "progressive": "SENT_PROGRESSIVE_GENERAL",
    "yes-no question": "SENT_QUESTION_YES_NO_AUX",
    "yes-no question with be": "SENT_QUESTION_YES_NO_AUX",
    "yes_no_question": "SENT_QUESTION_YES_NO_AUX",
    "do-support yes-no question": "SENT_QUESTION_YES_NO_DO_SUPPORT",
    "wh-question": "SENT_QUESTION_WH",
    "wh_question": "SENT_QUESTION_WH",
    "wh-interrogatives": "SENT_QUESTION_WH",
    "wh-question with do-support": "SENT_QUESTION_WH_DO_SUPPORT",
    "question tags": "SENT_QUESTION_TAG",
    "question tag": "SENT_QUESTION_TAG",
    "question_tag": "SENT_QUESTION_TAG",
    "existential there": "SENT_EXISTENTIAL_THERE",
    "existential there basic": "SENT_EXISTENTIAL_THERE",
    "existential there agreement": "SENT_EXISTENTIAL_THERE_AGREEMENT",
    "existential there yes-no question": "SENT_EXISTENTIAL_THERE_QUESTION",
    "that-clause noun clause": "SENT_NOUN_CLAUSE_THAT",
    "that_clause": "SENT_NOUN_CLAUSE_THAT",
    "that clause": "SENT_NOUN_CLAUSE_THAT",
    "shifted that-clause": "SENT_EXTRAPOSITION_IT_THAT",
    "it extraposition that clause": "SENT_EXTRAPOSITION_IT_THAT",
    "wh-clause noun clause": "SENT_NOUN_CLAUSE_WH",
    "wh clause": "SENT_NOUN_CLAUSE_WH",
    "passive voice": "SENT_PASSIVE_GENERAL",
    "general passive voice": "SENT_PASSIVE_GENERAL",
    "passive": "SENT_PASSIVE_GENERAL",
    "passive without performer": "SENT_PASSIVE_AGENTLESS",
    "passive reporting it structure": "SENT_PASSIVE_REPORTING_IT",
    "passive progressive": "SENT_PASSIVE_PROGRESSIVE",
    "passive perfect": "SENT_PASSIVE_PERFECT",
    "future time clause": "SENT_TIME_CLAUSE_FUTURE_REFERENCE",
    "general conditional clause": "SENT_CONDITIONAL_GENERAL",
    "conditional": "SENT_CONDITIONAL_GENERAL",
    "conditional sentence": "SENT_CONDITIONAL_GENERAL",
    "conditional sentences": "SENT_CONDITIONAL_GENERAL",
    "present possibility conditional": "SENT_CONDITIONAL_PRESENT_MODAL",
    "first conditional": "SENT_CONDITIONAL_FIRST",
    "second conditional": "SENT_CONDITIONAL_SECOND",
    "third conditional": "SENT_CONDITIONAL_THIRD",
    "zero conditional": "SENT_CONDITIONAL_ZERO",
    "counterfactual conditionals": "SENT_CONDITIONAL_COUNTERFACTUAL",
    "counterfactual past conditional": "SENT_CONDITIONAL_COUNTERFACTUAL_PAST",
    "factual conditionals": "SENT_CONDITIONAL_FACTUAL",
    "necessary-condition clause": "SENT_CONDITIONAL_NECESSARY_CONDITION",
    "even if clause": "SENT_CONDITIONAL_CONCESSIVE",
    "formal should conditional": "SENT_CONDITIONAL_FORMAL_SHOULD",
    "conditional directives": "SENT_CONDITIONAL_IMPERATIVE_RESULT",
    "conditional with imperative result": "SENT_CONDITIONAL_IMPERATIVE_RESULT",
    "predictive conditionals": "SENT_CONDITIONAL_PREDICTIVE",
    "it cleft": "SENT_CLEFT_IT",
    "it cleft adverbial focus": "SENT_CLEFT_IT",
    "all cleft": "SENT_CLEFT_IT",
    "what cleft": "SENT_CLEFT_IT",
    "cleft sentence": "SENT_CLEFT_IT",
    "questions and negatives": "SENT_NEGATION_GENERAL",
    "questions and negatives basic": "SENT_NEGATION_GENERAL",
    "active": "SENT_ACTIVE_VOICE",
    "imperative": "SENT_IMPERATIVE",
    "imperatives": "SENT_IMPERATIVE",
    "exclamative": "SENT_EXCLAMATIVE",
    "exclamatives": "SENT_EXCLAMATIVE",
}


PHRASE_TOPIC_TO_TEMPLATE: Final[dict[str, str]] = {
    "prepositional phrase": "PHRASE_PP_GENERAL",
    "prepositional phrases": "PHRASE_PP_GENERAL",
    "preposition": "PHRASE_PP_GENERAL",
    "prepositions": "PHRASE_PP_GENERAL",
    "pp_location": "PHRASE_PP_LOCATION",
    "pp_time": "PHRASE_PP_TIME",
    "pp_source": "PHRASE_PP_SOURCE",
    "pp_purpose": "PHRASE_PP_PURPOSE",
    "pp_agent": "PHRASE_PP_AGENT",
    "pp_means": "PHRASE_PP_MEANS",
    "pp_association": "PHRASE_PP_ASSOCIATION",
    "pp_general_relation": "PHRASE_PP_GENERAL",
    "relative clause": "PHRASE_RELATIVE_CLAUSE",
    "relative clauses": "PHRASE_RELATIVE_CLAUSE",
    "relative clauses 1": "PHRASE_RELATIVE_CLAUSE",
    "relative clauses 2": "PHRASE_RELATIVE_CLAUSE",
    "relative clauses 5": "PHRASE_RELATIVE_CLAUSE",
    "restrictive relative clauses": "PHRASE_RELATIVE_CLAUSE_RESTRICTIVE",
    "non-restrictive relative clauses": "PHRASE_RELATIVE_CLAUSE_NONRESTRICTIVE",
    "stranded preposition relative clause": "PHRASE_RELATIVE_CLAUSE_STRANDED_PREP",
    "fronted preposition relative clause": "PHRASE_RELATIVE_CLAUSE_FRONTED_PREP",
    "verb phrase": "PHRASE_VP_GENERAL",
    "phrasal verb": "PHRASE_VP_PHRASAL_VERB",
    "collocation": "PHRASE_VP_COLLOCATION",
    "modal": "PHRASE_VP_MODAL",
    "progressive": "PHRASE_VP_PROGRESSIVE",
    "perfect": "PHRASE_VP_PERFECT",
    "perfect_progressive": "PHRASE_VP_PERFECT_PROGRESSIVE",
    "passive": "PHRASE_VP_PASSIVE",
    "infinitive": "PHRASE_VP_INFINITIVE",
    "ing_participle": "PHRASE_VP_ING_NONFINITE",
}


def normalize_note_topic(topic: str) -> str:
    return " ".join(str(topic or "").strip().lower().replace("_", " ").split())


def topic_to_template_id(level: str, topic: str) -> str:
    norm_level = str(level or "").strip().lower()
    norm_topic = normalize_note_topic(topic)
    if not norm_topic:
        return ""

    if norm_level == "sentence":
        return SENTENCE_TOPIC_TO_TEMPLATE.get(norm_topic, "")

    if norm_level == "phrase":
        if norm_topic.startswith("preposition:"):
            return "PHRASE_PP_GENERAL"
        return PHRASE_TOPIC_TO_TEMPLATE.get(norm_topic, "")

    return ""
