"""Build T5 train/dev/test dataset from book pairs and Wiktionary.

RLE contract architecture:
- Sentence contract: content = spaCy second-level node markers (NOT {{SENTENCE}}),
  service fields (part_of_speech, grammatical_role, tense, aspect, mood, voice,
  tam_construction) from spaCy. No topic_key in contract.
- Word contract: content = actual word (NOT parametrized), service fields from spaCy.
- Phrase contract: content = {{PHRASE}}, part_of_speech inferred from topic_key,
  grammatical_role = "phrase". Trained from phrase-chapter book pairs.

Target: human-written notation (free natural language).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

ENDS_WITH_PUNCT = re.compile(r"[.!?]\s*$")
CROSS_REF_RE = re.compile(
    r"\(see\b|see unit\b|see section\b|see paragraph|explained in paragraph|paragraph[s]?\s+\d",
    re.I,
)
UNIT_PREFIX_RE = re.compile(r"^Unit\s+\d+[^:]*:\s*", re.I)
REGISTER_TAG_RE = re.compile(r"\((NEWS|CONV|ACAD|FICT|SPOKEN|WRITTEN)\)", re.I)
# EGIU-style chapter heading leaking into notes: "Relative clauses 5: …", "Type 2 B …"
CHAPTER_HEADING_RE = re.compile(
    r"^[A-Z][a-z]+(?: [a-z]+)* \d+:",   # "Relative clauses 5:", "Passive voice 3:"
    re.I,
)
# Inline section-reference numbers: COBUILD "8.21 By which…" or GSWE "(2.3.2)"
INLINE_SECTION_RE = re.compile(r"\b\d{1,2}\.\d{2,3}\b|\(\d+\.\d+\.\d+\)")
# GSWE corpus-analysis jargon that has no pedagogical value
CORPUS_JARGON_RE = re.compile(
    r"lexical bundle|in this category are of|most common in (conversation|academic|news|fiction)|"
    r"(conversation|academic|news|fiction|spoken|written) english\b",
    re.I,
)
# Target is a contrast/continuation fragment (book mid-text)
_NOTE_STARTS_BUT_RE = re.compile(
    r"^(But|And|Also|Furthermore|Moreover|Similarly|However|Here|"
    r"In contrast|In addition|For example|For instance|Note that|In fact|In particular)\b",
    re.I,
)
# Target begins with farlex/book metadata label
_NOTE_STARTS_DEF_RE = re.compile(r"^Definition\b|\bDefinition\b")
# Target is a truncated definition ending with colon + terminal punctuation
_NOTE_ENDS_COLON_PERIOD_RE = re.compile(r":\s*[.!?]\s*$")
# Leech scraper artifact: double colon "please: : sit down"
_NOTE_DOUBLE_COLON_RE = re.compile(r":\s*:")
# Leech scraper artifact: trailing ". ."
_NOTE_TRAILING_DOT_DOT_RE = re.compile(r"\.\s+\.\s*$")
# COBUILD PDF OCR artifact: sentence starts with ")" instead of capital letter
# e.g. ")f you want" → "If you want", ")n the case" → "In the case"
_PDF_ARTIFACT_RE = re.compile(r"^\)[A-Za-z]")
# Cambridge Grammar Today: typographic meta-references to book formatting
_META_BOOK_REF_RE = re.compile(r"\b(in bold|are underlined|in italics|in brackets|are shown in|are highlighted)\b", re.I)
# EGIU chapter-heading targets: "Present perfect 2 (I have done) B Compare:..."
_EGIU_CHAPTER_TARGET_RE = re.compile(
    r"^(Present|Past|Future)\s+(perfect|continuous|simple|progressive|tense)\b.*\(I\s+\w",
    re.I,
)
# EGIU grammar-category chapter targets: "Passive 2 (be done / been done) D ..."
_EGIU_CATEGORY_CHAPTER_RE = re.compile(
    r"^[A-Z][a-z]+(?: [a-z]+)?\s+\d+\s*\(",
    re.I,
)
# EGIU chapter-heading content: "Present continuous (I am doing)" used as example sentence
_EGIU_CHAPTER_CONTENT_RE = re.compile(
    r"^(Present|Past|Future)\s+(perfect|continuous|simple|progressive|tense)\b",
    re.I,
)
# Leech NP-structure formula fragments: "[s]) + (modifier[s]) + head+..."
_LEECH_NOTE_FORMULA_RE = re.compile(r"^\[s\]\)")
# Leech notes that are about a specific named verb form (cross-product artifact)
_LEECH_NOTE_SPECIFIC_VERB_RE = re.compile(r"^As (a|an) (regular|irregular)\s+verb,", re.I)
# Leech notes containing an embedded named example (italic example leaked into note text)
_LEECH_NOTE_EXAMPLE_NAME_RE = re.compile(r"\bPaula\b")
# Pronoun person guards
_PERSON_NOTE_FIRST_RE = re.compile(r"\bfirst[\s-]person\b", re.I)
_PERSON_NOTE_SECOND_RE = re.compile(r"\bsecond[\s-]person\b", re.I)
_PERSON_NOTE_THIRD_RE = re.compile(r"\bthird[\s-]person\b", re.I)
_FIRST_PERSON_PRONS: frozenset = frozenset(
    {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"}
)
_SECOND_PERSON_PRONS: frozenset = frozenset(
    {"you", "your", "yours", "yourself", "yourselves"}
)
_THIRD_PERSON_PRONS: frozenset = frozenset({
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "they", "them", "their", "theirs", "themselves", "it", "its", "itself",
})
# Demonstrative guard — also catches deictic reference notes without the word "demonstrative"
_DEMONSTRATIVE_NOTE_RE = re.compile(
    r"\bdemonstrative[s]?\b|\bimmediate\b.{0,20}\breference\b", re.I
)
_DEMONSTRATIVES: frozenset = frozenset({"this", "that", "these", "those"})
# Relative pronoun note in DET topic: "which" can be a determiner OR relative pronoun;
# notes about zero relative pronoun / whom should not pair with a plain determiner
_RELATIVE_PRONOUN_NOTE_RE = re.compile(r"\bzero\s+relative\b|\bwhom\b.{0,50}\bnot\s+common\b", re.I)
# Modal auxiliary guard: non-modal verb paired with a modal-auxiliary note
_LEECH_MODAL_AUX_NOTE_RE = re.compile(r"\bmodal\s+auxiliar", re.I)
_MODAL_VERBS: frozenset = frozenset({"will", "would", "shall", "should", "can", "could", "may", "might", "must"})
# Primary auxiliary verb guard: non-primary verb paired with be/have/do note
_LEECH_PRIMARY_VERB_NOTE_RE = re.compile(
    r"\bprimary\s+verbs?\b.{0,40}\bbe\b|\bbe,?\s*,?\s*have\s+and\s+do\s+are\s+known\s+as\s+primary",
    re.I,
)
_PRIMARY_VERBS: frozenset = frozenset({"be", "have", "do"})
# Primary verb imperative guard: sentence not using be/have/do as imperative
_LEECH_PRIMARY_IMP_NOTE_RE = re.compile(r"\bimperatives?\s+of\s+the\s+primary\s+verbs?\b", re.I)
# Multiword construction entry guard: entry_head names a phrase-level construct
# (phrasal verb, prepositional verb, light verb, prepositional adverb) — the
# example ROOT word cannot stand for the full multi-word unit
_LEECH_MULTIWORD_ENTRY_RE = re.compile(
    r"\b(?:phrasal|prepositional|light)\s+verb[s]?\b|\bprepositional\s+adverb[s]?\b", re.I
)
# Articles guard: non-article determiner paired with an articles-specific note
_LEECH_ARTICLES_NOTE_RE = re.compile(
    r"\bThe articles?\b.{0,40}\ba/an\b|\bmost\s+common\s+determiners?\b", re.I
)
_ARTICLES: frozenset = frozenset({"a", "an", "the"})
# Manner adverb guard: degree adverb (more/most/really) paired with a manner note
_LEECH_MANNER_NOTE_RE = re.compile(r"\bmanner\s+adverb|in\s+such.and.such\s+a\s+manner\b", re.I)
_DEGREE_ADVERBS: frozenset = frozenset(
    {"really", "more", "most", "very", "much", "rather", "considerably", "quite", "fairly", "less", "least",
     "worse", "better", "worst", "best"}
)
# Attributive adjective guard: predicative-only adj paired with attributive-modifier note
_LEECH_ATTRIBUTIVE_NOTE_RE = re.compile(r"\ban?\s+adjective\s+that\s+modif(?:ies|y)\s+a\s+noun\b", re.I)
_PREDICATIVE_ONLY_ADJS: frozenset = frozenset(
    {"afraid", "aware", "alive", "alone", "asleep", "awake", "ashamed", "alike", "aboard"}
)
# Agent noun guard: passive sentence paired with an agent-noun definition note
_AGENT_NOUN_NOTE_RE = re.compile(r"\bagent\s+nouns?\b", re.I)
# Fronted-if-then guard: sentence uses "unless"/"except if" but note is about fronted
# "if"-clause + optional "then" at the beginning of the main clause
_FRONTED_IF_THEN_NOTE_RE = re.compile(
    r"\bif.clause is put first\b.*\bthen is sometimes\b", re.I | re.S
)
# Unless-focus guard: note focuses on "unless" as negative conditional conjunction
# but the example sentence uses "if" (the note only makes sense for unless sentences)
_UNLESS_FOCUS_NOTE_RE = re.compile(r"Another conditional conjunction.{0,60}unless", re.I)
# Non-defining relative clause guard: note describes non-defining RC (comma-delimited)
# but the example sentence has a defining RC (no comma before the relative pronoun)
_NON_DEFINING_RC_NOTE_RE = re.compile(
    r"\bnon.defining\b|\bnon.restrictive\b|\bsimply\s+gives\s+extra\s+information\b",
    re.I,
)
_NON_DEFINING_RC_COMMA_RE = re.compile(r",\s*(who|which|whom|whose|that)\b", re.I)
# Third conditional guard: note is about third conditionals but sentence uses "wish"
_THIRD_COND_NOTE_RE = re.compile(r"\bthird\s+conditional[s]?\b", re.I)
# Cambridge phrase guards
# -ed adjective forms: note says can't use -ed forms before noun, but phrase is not -ed
_CAMBRIDGE_EDFORM_NOTE_RE = re.compile(
    r"\bcan'?t\s+use\s+some\s*-?\s*ed\s+forms?\s+before\s+a\s+noun\b", re.I
)
# "between + pronoun" note but phrase contains no object pronoun
_BETWEEN_PRONOUN_NOTE_RE = re.compile(r"\bbetween\s*[+]\s*pronoun\b", re.I)
# "use between/among" note: the extracted phrase must actually contain that preposition
_USE_BETWEEN_NOTE_RE = re.compile(r"\buse between\b", re.I)
_USE_AMONG_NOTE_RE = re.compile(r"\buse among\b", re.I)
_OBJECT_PRONOUNS: frozenset = frozenset({"me", "us", "you", "him", "her", "it", "them", "whom"})
# Grammatical term label: phrase content is just a label like "verb" or "noun"
_GRAMMAR_TERM_RE = re.compile(
    r"^(?:verb|noun|pronoun|adjective|adverb|determiner|conjunction|preposition|"
    r"article|auxiliary|modal|participle|gerund|infinitive|predicate|subject|object|clause|phrase)s?\s*$",
    re.I,
)
# Book-internal meta-sentence: sentence is cross-referencing another section of the book
_BOOK_META_SENTENCE_RE = re.compile(
    r"\bare listed in paragraphs\b|\bare explained\s+\w+\s+in\s+(Chapter|Section)\b", re.I
)
# Adverb phrase: bare single degree-modifier extracted as head (e.g. "very" from "very well")
_SINGLE_DEGREE_MOD_RE = re.compile(
    r"^(very|too|so|really|right|extremely|quite|fairly|rather)\s*$", re.I
)
# Adverb phrase modifying note: note says adverb phrases modify determiners/NPs/PPs
# but only a single bare adverb was extracted — not the full modifying phrase
_ADV_MODIFY_NOTE_RE = re.compile(
    r"\bto\s+modify\s+(noun\s+phrases?|determiners?|prepositional\s+phrases?|noun\s+groups?)\b",
    re.I,
)
# Comparative mismatch: equal-comparison note should not pair with more/less phrase
_EQUAL_COMPARISON_NOTE_RE = re.compile(
    r"\bequal\s+comparison\b|\bcome after as\b.{0,30}\bbase form\b", re.I | re.S
)
# Comparative clause definition note should not pair with bare "as + adj" (no full clause)
_COMPARATIVE_CLAUSE_DEF_RE = re.compile(r"\bsubordinate\s+clause\s+which\s+modif", re.I)
# -er form note: describes the short comparative ending in -er;
# should not pair with "more/less + word" periphrastic comparatives
_ER_COMPARATIVE_NOTE_RE = re.compile(
    r"\bends?\b.{0,40}\bin\s+er\b|\b-er\s+form\b|\bcomparative\s+form\b.{0,40}\bin\s+er\b",
    re.I,
)
_MORE_LESS_START_RE = re.compile(r"^(more|less)\b", re.I)
_AS_ADJ_ONLY_RE = re.compile(r"^as\s+\w+\s*$", re.I)
# Finite subordinating conjunction at phrase start: phrase is actually a finite clause
_FINITE_SUBORD_CLAUSE_RE = re.compile(
    r"^(because|since|when|although|though|while|after|before|unless|until|once|where|as)\b",
    re.I,
)
# Phrasal prepositional verb note: note describes verb+particle+preposition construction;
# extracted prep phrase is only a fragment of the full multi-word unit
_PHRASAL_PREP_VERB_NOTE_RE = re.compile(
    r"verb\s*\+\s*adverb\s+particle\s*\+\s*preposition|adverb\s+particle\s+before\s+the\s+preposition",
    re.I,
)
# Adjective complementation note: note defines an adjective as requiring an obligatory
# complement ("a word or phrase which is required to complete its meaning"), but
# the extracted phrase is a single bare adjective without any complement
_COMPLEMENTATION_NOTE_RE = re.compile(
    r"\ba\s+word\s+or\s+phrase\s+which\s+is\s+required\s+to\s+complete\s+its\s+meaning\b",
    re.I,
)
# Adverbial clause mobility note: clause-level note about adverbial clause position;
# must not pair with a single-word verb phrase
_ADVERBIAL_CLAUSE_MOBILE_NOTE_RE = re.compile(
    r"\badverbial\s+clauses?\s+are\s+typically\s+mobile\b",
    re.I,
)
# Sequence-of-tenses note: describes tense agreement across a main+subordinate clause pair;
# not appropriate as a target for a single verb phrase contract
_SEQUENCE_OF_TENSES_NOTE_RE = re.compile(
    r"\bsequence\s+of\s+tenses?\b|"
    r"\bpast\s+tense\s+of\s+the\s+subordinate\s+clause\b|"
    r"\bpast\s+tense\s+in\s+a\s+main\s+clause\s+being\s+followed\b",
    re.I,
)
# Third-conditional result clause: "would/could/might have" or contracted forms.
# Absence of this pattern in a conditional sentence means it is NOT a third conditional
# (it is a mixed conditional or unrelated structure).
_PERFECT_MODAL_RE = re.compile(
    r"\b(would|could|might)n?'?t?\s+have\b|\bwould'?ve\b|\bcould'?ve\b|\bmight'?ve\b",
    re.I,
)
# OCR artifact: closing paren surrounded by spaces mid-sentence ("will ) do")
_MID_SENTENCE_PAREN_RE = re.compile(r"\s\)\s")
# Ellipsis characters (Unicode or ASCII triple-dot): incomplete/truncated examples
_ELLIPSIS_RE = re.compile(r"[…]|\.\.\.")
# Duplicate content: same long phrase repeated after a dot (OCR/extraction artifact)
_DUPLICATE_CONTENT_RE = re.compile(r"(.{15,})\.\1", re.S)
# Dialogue prefix: "Person B: ..." meta-dialogue (not an example sentence)
_DIALOGUE_PREFIX_RE = re.compile(r"^Person\s+[A-Z]:", re.I)
# Unclosed parenthesis at end of sentence (extraction artifact: "(present perfect")
_UNCLOSED_PAREN_RE = re.compile(r"\([^)]*$")
# First-person imperative: note says "first-person imperative" → sentence must start let's/us/me
_FIRST_PERSON_IMP_NOTE_RE = re.compile(r"\bfirst[\s-]person\s+imperative\b", re.I)
_LETS_RE = re.compile(r"^\s*let(?:'s|\s+us|\s+me)\b", re.I)
# Adverbial clause topic: sentence must contain a subordinating conjunction
_SUBORD_CONJ_RE = re.compile(
    r"\b(because|since|when|although|though|while|after|before|unless|until|once|if)\b", re.I
)
# By-agent target: note is about the by-phrase / agent role in passive
_BY_AGENT_TARGET_RE = re.compile(
    r"\bagent\b.{0,80}\bby\b|\bby.{0,10}(?:phrase|agent)\b|\bcorresponds\s+to\s+the\s+a(?:gent|dverbial)\b",
    re.I,
)
# Conditional fragment: result-only clause (no if-part, starts with pronoun+would/could/might)
_CONDITIONAL_RESULT_ONLY_RE = re.compile(
    r"^(?:she|he|it|they|i|we|you)\s+(?:would|could|might)\b", re.I
)
# Conditional fragment: if-only clause (no main clause, short)
_IF_ONLY_FRAGMENT_RE = re.compile(r"^(?:if|unless)\b", re.I)
# Wish-focus note: target is specifically about wish/if-only structures
_WISH_FOCUS_NOTE_RE = re.compile(
    r"^wish\b|we\s+also\s+use\s+wish\b|\bthe\s+wish\s+(?:construction|structure|clause)\b",
    re.I,
)
# Reported speech subtype guards
_REPORTED_QUESTION_TARGET_RE = re.compile(r"\breported\s+questions?\b", re.I)
_REPORTED_STATEMENT_TARGET_RE = re.compile(r"\breported\s+statements?\b", re.I)
# Reported question in content: wh-word after a question-reporting verb
_REPORTED_QUESTION_CONTENT_RE = re.compile(
    r"\b(asked|wondered|didn'?t\s+know|wanted\s+to\s+know)\b.{0,40}"
    r"\b(what|who|where|when|why|how|whether)\b|"
    r"^(what|who|where|when|why|how)\s+\w",
    re.I,
)
# Reported statement/command in content: that-clause or to-infinitive after reporting verb
_REPORTED_STATEMENT_CONTENT_RE = re.compile(
    r"\b(said|told|claimed|thought|believed|knew|agreed|felt|stated|mentioned)\s+that\b|"
    r"^that\s+\w",
    re.I,
)
# Irregular comparative note: names specific irregular forms (good/better, bad/worse)
_IRREGULAR_COMPARATIVE_NOTE_RE = re.compile(
    r"\birregular\s+comparative\s+forms?\b|"
    r"\bgood\s*[~→\-]\s*better\b|"
    r"\bbad\s*[~→\-]\s*worse\b",
    re.I,
)
# Unequal comparison note: "clauses of unequal comparison come after older/more/less"
_UNEQUAL_COMPARISON_NOTE_RE = re.compile(r"\bunequal\s+comparison\b", re.I)
# "as + word" at start of phrase (equality comparisons: "as big", "as famous")
_AS_COMPARATIVE_START_RE = re.compile(r"^as\s+\w", re.I)
# Linguistic meta-language: Sentence targets must contain at least one grammatical term
_LINGUISTIC_META_RE = re.compile(
    r"\b(passive|active|voice|tense|aspect|clause|verbal?|noun|adjectival?|adverbial?|"
    r"pronoun|subject|object|infinitive|gerund|participle|modal|auxiliary|conditional|"
    r"relative|subordinate|coordinate|complement|predicate|determiner|prefix|suffix|"
    r"first.person|second.person|third.person|"
    r"indicative|subjunctive|imperative|interrogative|declarative|exclamative|"
    r"progressive|perfect|simple|continuous|future|past|present|"
    r"singular|plural|negat|question|statement|reported|indirect|direct|"
    r"article|conjunction|preposition|interjection|particle|grammatical|"
    r"sentence|phrase|word\s+form|word\s+class|structure|construction|agreement|"
    r"transitive|intransitive|copula|existential|modifier)\b",
    re.I,
)
# Auxiliary verb added before main verb — note applies only to aux/modal words
_AUX_ADDED_BEFORE_NOTE_RE = re.compile(
    r"\bone\s+or\s+more\s+auxiliary\s+verbs?\s+can\s+be\s+added\b", re.I
)
# Adverbs identical in form to adjectives (long, early, hard…) — not "just"/"then"/"somewhere"
_ADJ_IDENTICAL_ADV_NOTE_RE = re.compile(
    r"\bidentical\s+in\s+form\s+to\s+(?:an?\s+)?adject|"
    r"\bsame\s+form\s+as\s+(?:an?\s+)?adjective\b",
    re.I,
)
_ADJ_IDENTICAL_ADVS: frozenset = frozenset({
    "long", "early", "late", "hard", "fast", "high", "low", "far", "near", "deep",
    "straight", "wrong", "right", "wide", "clean", "clear", "fine", "free", "bright",
    "close", "loud", "quick", "sharp", "slow", "sure", "tight",
})
# "Many adjectives are gradable" note — degree modifiers (very/too/more) are not gradable words
_GRADABLE_ADJ_NOTE_RE = re.compile(r"\bmany\s+adjectives?\s+are\s+gradable\b", re.I)
_DEGREE_MODIFIER_WORDS: frozenset = frozenset({
    "very", "too", "so", "quite", "rather", "fairly", "extremely",
    "more", "most", "less", "least", "really",
})
# Adjectival notes that describe phrase-level or adverb-phrase structure, not plain adjectives
_OPTIONAL_MODIFIER_NOTE_RE = re.compile(
    r"\boptional\s+elements?\s+are\s+called\s+modifiers\b", re.I
)
_ADV_HEAD_PHRASE_NOTE_RE = re.compile(r"\bhead\s+of\s+an?\s+adverb\s+phrase\b", re.I)
# Transitive/requires-object note must not pair with known intransitive verbs
_REQUIRES_OBJECT_NOTE_RE = re.compile(r"\brequires?\s+an?\s+object\b", re.I)
_INTRANSITIVE_VERBS: frozenset = frozenset({
    "fail", "go", "come", "arrive", "depart", "sleep", "die", "fall", "rise", "exist",
    "happen", "occur", "appear", "seem", "become", "remain", "wait", "listen",
})
WS_RE = re.compile(r"\s+")


def _if_clause_has_past_perfect(sentence: str) -> bool:
    """True if the if-clause in the sentence uses past perfect (had/hadn't + pp, or 'd + pp)."""
    m = re.search(r"\bif\b([^,;.!?]{2,100}?)(?:,|;|\s+then\b|$)", sentence, re.I | re.S)
    if_clause = m.group(1).strip() if m else ""
    return bool(re.search(r"\bhad(?:n'?t)?\s+\w+|\b'd\s+\w+", if_clause, re.I))

SOURCES: List[Tuple[str, str]] = [
    ("collins_cobuild_english_grammar_2011", "data/reports/collins_cobuild_2011_pairs_clean.jsonl"),
    ("cobuild_english_grammar_2017", "data/reports/cobuild_grammar_pairs_clean.jsonl"),
    ("english_grammar_in_use_5th_2019", "data/reports/english_grammar_in_use_pairs_clean.jsonl"),
    # gswe and lgswe excluded: corpus-analysis text, section numbers, register tags — not pedagogical
    # mysteries_of_english_grammar excluded: academic research text, citations, not pedagogical
    ("farlex_complete_english_grammar_rules_2016", "data/reports/farlex_grammar_2016_pairs.jsonl"),
    ("cambridge_grammar_today", "data/reports/cambridge_grammar_phrase_pairs.jsonl"),
]

WORD_SOURCES: List[Tuple[str, str]] = [
    ("simple_english_wiktionary", "data/reports/simplewiktionary_grammar_pairs.jsonl"),
    ("cambridge_learner_dictionary", "data/reports/cambridge_learner_pairs.jsonl"),
]


PROMPT_TEMPLATE_VERSION = "rle_v7"
TASK_NAME = "generate_linguistic_note"

# Only book chapters whose notes describe sentence-level TAM/construction patterns.
# Word-level chapters (prepositions, modal definitions) are excluded —
# word contracts come exclusively from Wiktionary.
SENTENCE_TOPICS: set[str] = {
    "passive_voice",
    "perfect",
    "progressive",
    "conditional_sentences",
    "relative_clauses",
    "that_clause",
    "wh_question",
    "questions_and_negatives",
    "question_tags",
    "double_be",
    "number_agreement",
    "double_negatives",
    "shadow_pronouns",
}

# Phrase-level chapters → Phrase contracts.
# Maps topic_key → canonical POS of the phrase head.
PHRASE_TOPIC_POS: dict[str, str] = {
    "noun_phrase": "NOUN",
    "verb_phrase": "VERB",
    "adjective_phrase": "ADJ",
    "adverb_phrase": "ADV",
    "prepositional_phrases": "ADP",
    "participle_phrase": "VERB",
    "absolute_phrase": "VERB",
}
PHRASE_TOPICS: set[str] = set(PHRASE_TOPIC_POS.keys())

LEECH_SOURCE: Tuple[str, str] = (
    "leech_glossary_2006",
    "data/reports/leech_glossary_pairs.jsonl",
)
LEECH_WORD_POS_TOPICS: set[str] = {
    "ADJ", "ADV", "ADP", "NOUN", "VERB", "PRON", "DET", "AUX",
    "NUM", "INTJ", "PART", "CCONJ", "SCONJ", "PROPN",
}
LEECH_PHRASE_TOPICS: set[str] = PHRASE_TOPICS | {"comparative_phrase"}

# For Leech Word pairs: prefer the token whose POS matches the topic label so
# that e.g. "this bad weather" for ADJ uses "bad", not ROOT "weather".
LEECH_WORD_TOPIC_POS: dict[str, str] = {k: k for k in (
    "ADJ ADV ADP NOUN VERB PRON DET AUX NUM INTJ PART CCONJ SCONJ PROPN".split()
)}
# Sentence topics present in Leech but not in the book-pair SENTENCE_TOPICS whitelist
LEECH_SENTENCE_TOPICS: set[str] = SENTENCE_TOPICS | {
    "imperative",
    "reported_speech",
    "adverbial_clause",
    "existential",
    "interrogative",
    "subordination",
    "coordination",
    "cleft_construction",
    "inversion",
    "negation",
    "exclamative",
}

# TAM consistency guards: for topics where the grammatical feature is directly
# detectable from spaCy/TAM, reject pairs where the detected value contradicts
# the topic.  This filters farlex contrast-examples (e.g. present-simple sentence
# in a "perfect" chapter) before they corrupt training signal.
TAM_TOPIC_GUARDS: dict[str, Any] = {
    "passive_voice":  lambda s: s.get("voice") == "passive",
    "progressive":    lambda s: s.get("aspect") in {"progressive", "perfect_progressive"},
    "perfect":        lambda s: "perfect" in s.get("aspect", ""),
}

_REL_PRONOUN_RE = re.compile(r"\b(that|which|who|whom|whose|where|when)\b", re.I)
_THAT_SUBORD_RE = re.compile(r"\bthat\b", re.I)
# Target mentions omitted/zero relative pronoun — mismatch if sentence has explicit pronoun
_REL_OMISSION_NOTE_RE = re.compile(
    r"\b(without\s+a\s+relative\s+pronoun|"
    r"relative\s+pronoun\s+(can\s+be\s+)?omit|"
    r"zero\s+relative|"
    r"do\s+not\s+have\s+a\s+relative\s+pronoun|"
    r"can\s+be\s+left\s+out\s+of\s+a\s+relative)\b",
    re.I,
)

# Lexical guards: check the sentence text for required words/patterns.
LEXICAL_TOPIC_GUARDS: dict[str, Any] = {
    "relative_clauses": lambda sent: bool(_REL_PRONOUN_RE.search(sent)),
    "that_clause":      lambda sent: bool(_THAT_SUBORD_RE.search(sent)),
}

# Per-topic row cap for sentence training data.
# Underrepresented topics get a higher cap (or unlimited); high-volume topics
# like relative_clauses are capped lower to prevent them from dominating.
WORD_POS_CAPS: dict[str, int] = {
    "ADV": 200,
    "ADP": 100,
}

SENTENCE_TOPIC_MAX: dict[str, int] = {
    "relative_clauses": 60,
    "passive_voice": 80,
    "perfect": 80,
    "progressive": 80,
    "conditional_sentences": 80,
    "that_clause": 80,
    "wh_question": 120,
    "questions_and_negatives": 120,
    "question_tags": 120,
    "double_be": 120,
    "number_agreement": 120,
    "double_negatives": 120,
    "shadow_pronouns": 120,
}


_LIGATURE_TABLE = str.maketrans({
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "’": "'",   # right single quotation mark (smart apostrophe)
    "‘": "'",   # left single quotation mark
    "“": '"',   # left double quotation mark
    "”": '"',   # right double quotation mark
})


def _norm(s: Any) -> str:
    return WS_RE.sub(" ", str(s or "").translate(_LIGATURE_TABLE).strip())


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("||".join(parts).encode()).hexdigest()[:16]


def _clean_notation(text: str) -> str:
    text = _norm(text)
    text = UNIT_PREFIX_RE.sub("", text)
    return _norm(text)


_TABLE_REF_RE = re.compile(r"^(Table|Figure|Fig\.?|Example)\s+\d", re.I)
_PAGE_NUM_RE = re.compile(r"\b\d{1,4}\s*$")
# Farlex book labels prepended to example sentences: "Conditional: ...", "Truth: ..."
_FARLEX_LABEL_RE = re.compile(r'^[A-Z][a-z]+:\s*["\'“‘]')
# Farlex analytical annotation inside phrase examples: "on the wall — preposition on + ..."
_PHRASE_ANALYSIS_RE = re.compile(
    r"\s[—–]\s*(?:\w+\s+)?"
    r"(auxiliary|preposition|verb|noun|adjective|adverb|gerund|participle|determiner|intensifier|conjunction)\b",
    re.I,
)
# Truncated sentence: starts with unmatched opening quote
_UNMATCHED_OPEN_QUOTE_RE = re.compile(r'^["“](?![^""“”]*["”])')


def _is_valid_sentence(text: str) -> bool:
    text = _norm(text)
    words = text.split()
    if len(words) < 3 or len(words) > 80:
        return False
    if sum(ch.isalpha() for ch in text) < 5:
        return False
    # Prose fragment: starts with lowercase (mid-paragraph extraction)
    if text and text[0].islower():
        return False
    if _PDF_ARTIFACT_RE.match(text):
        return False
    # OCR artifact: closing paren surrounded by spaces ("will ) do")
    if _MID_SENTENCE_PAREN_RE.search(text):
        return False
    # Ellipsis: truncated or partial examples ("I do … and if I did …")
    if _ELLIPSIS_RE.search(text):
        return False
    # Duplicate content: "who have to work.who have to work" (extraction artifact)
    if _DUPLICATE_CONTENT_RE.search(text):
        return False
    # Dialogue prefix: "Person B: ..." meta-dialogue
    if _DIALOGUE_PREFIX_RE.match(text):
        return False
    # Unclosed parenthesis at end: "Situation: ... (present perfect"
    if _UNCLOSED_PAREN_RE.search(text):
        return False
    if _TABLE_REF_RE.match(text):
        return False
    if _PAGE_NUM_RE.search(text):
        return False
    if _FARLEX_LABEL_RE.match(text):
        return False
    if _PHRASE_ANALYSIS_RE.search(text):
        return False
    if _UNMATCHED_OPEN_QUOTE_RE.match(text):
        return False
    if re.search(r"\(as in this example\)|\(as above\)|\(see above\)", text, re.I):
        return False
    if _BOOK_META_SENTENCE_RE.search(text):
        return False
    # Truncated: ends mid-relative-clause "…who was" / "…which had"
    if re.search(
        r"\b(who|which|that|whom)\s+"
        r"(is|are|was|were|had|have|has|will|would|can|could|may|might|shall|should)\s*$",
        text, re.I,
    ):
        return False
    return True


def _is_valid_note(text: str) -> bool:
    text = _norm(text)
    if len(text.split()) < 8:
        return False
    if not ENDS_WITH_PUNCT.search(text):
        return False
    if _PDF_ARTIFACT_RE.match(text):
        return False
    if _META_BOOK_REF_RE.search(text):
        return False
    if CROSS_REF_RE.search(text):
        return False
    if REGISTER_TAG_RE.search(text):
        return False
    if CHAPTER_HEADING_RE.search(text):
        return False
    if INLINE_SECTION_RE.search(text):
        return False
    if CORPUS_JARGON_RE.search(text):
        return False
    if _NOTE_STARTS_BUT_RE.match(text):
        return False
    if _NOTE_STARTS_DEF_RE.search(text):
        return False
    if _NOTE_ENDS_COLON_PERIOD_RE.search(text):
        return False
    if _NOTE_DOUBLE_COLON_RE.search(text):
        return False
    if _NOTE_TRAILING_DOT_DOT_RE.search(text):
        return False
    if _EGIU_CHAPTER_TARGET_RE.match(text):
        return False
    if _EGIU_CATEGORY_CHAPTER_RE.match(text):
        return False
    return True


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _build_node_contract(token: Any, tam_label: str, depth: int = 0, max_depth: int = 2) -> Dict[str, Any]:
    """Recursively build an RLE node contract for a spaCy token.

    Leaf tokens → Word node (content={{WORD}}).
    Tokens with children → Phrase node (content={{PHRASE}}).
    ROOT carries the full TAM label.
    Recursion stops at max_depth to keep inputs within token budget.
    """
    children = sorted(
        [c for c in token.children if not c.is_punct and not c.is_space],
        key=lambda t: t.i,
    )
    has_children = bool(children) and depth < max_depth
    contract: Dict[str, Any] = {
        "node_type": "Phrase" if bool(children) else "Word",
        "content": "{{PHRASE}}" if bool(children) else "{{WORD}}",
        "part_of_speech": token.pos_,
        "grammatical_role": token.dep_,
    }
    if token.dep_ == "ROOT" and tam_label:
        contract["tam_construction"] = tam_label
    if has_children:
        contract["linguistic_elements"] = [
            _build_node_contract(c, tam_label, depth + 1, max_depth) for c in children
        ]
    return contract


def _build_sentence_content(doc: Any, tam_label: str) -> str:
    """Build content field of Sentence contract as serialized child node contracts.

    The Sentence's linguistic_elements are the immediate children of ROOT,
    each represented as a full recursive RLE node contract.
    Specific word forms are not included — only spaCy structural fields.
    """
    root_token = next((t for t in doc if t.dep_ == "ROOT"), None)
    if not root_token:
        return "[]"
    root_contract = _build_node_contract(root_token, tam_label)
    elements = root_contract.get("linguistic_elements", [root_contract])
    return json.dumps(elements, ensure_ascii=False, sort_keys=True)


def _parse_sentence_contract(sentence: str, nlp: Any) -> Tuple[str, Dict[str, Any]]:
    """Return (content_markers, service_fields) for a Sentence node."""
    from ela_pipeline.tam.rules import detect_tam

    doc = nlp(sentence)
    tam = detect_tam(doc)
    label = tam.label or ""
    tense = tam.short_tense or "null"

    voice = "passive" if "passive" in label else "active"
    if "perfect_progressive" in label:
        aspect = "perfect_progressive"
    elif "perfect" in label:
        aspect = "perfect"
    elif "progressive" in label:
        aspect = "progressive"
    else:
        aspect = "simple"

    root_token = next((t for t in doc if t.dep_ == "ROOT"), None)
    root_pos = root_token.pos_ if root_token else "VERB"

    content = _build_sentence_content(doc, label)
    service = {
        "part_of_speech": root_pos,
        "grammatical_role": "ROOT",
        "tense": tense,
        "aspect": aspect,
        "mood": "null",
        "voice": voice,
        "tam_construction": label,
        # Internal flag: popped before writing to output — used to filter VP fragments
        "_has_subject": any(t.dep_ in {"nsubj", "nsubjpass", "expl"} for t in doc),
    }
    return content, service


def _build_sentence_input(content: str, service_fields: Dict[str, Any]) -> str:
    payload = {
        "node_type": "Sentence",
        "content": content,
        "part_of_speech": service_fields.get("part_of_speech", "VERB"),
        "grammatical_role": service_fields.get("grammatical_role", "ROOT"),
        "tense": service_fields.get("tense", "null"),
        "aspect": service_fields.get("aspect", "null"),
        "mood": service_fields.get("mood", "null"),
        "voice": service_fields.get("voice", "null"),
        "tam_construction": service_fields.get("tam_construction", ""),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "task": TASK_NAME,
    }
    return f"task: {TASK_NAME} payload: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def _parse_word_contract(word: str, nlp: Any) -> Dict[str, Any]:
    """Return service fields for a Word node via spaCy."""
    doc = nlp(word)
    token = doc[0] if len(doc) > 0 else None
    return {
        "part_of_speech": token.pos_ if token else "X",
        "grammatical_role": token.dep_ if token else "dep",
        "lemma": token.lemma_ if token else word,
    }


def _build_word_input(word: str, service_fields: Dict[str, Any]) -> str:
    payload = {
        "node_type": "Word",
        "content": word,
        "part_of_speech": service_fields.get("part_of_speech", "X"),
        "grammatical_role": service_fields.get("grammatical_role", "dep"),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "task": TASK_NAME,
    }
    return f"task: {TASK_NAME} payload: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def _build_phrase_input(phrase_text: str, context: str, pos: str, dep: str) -> str:
    payload = {
        "node_type": "Phrase",
        "content": phrase_text,
        "context": context,
        "part_of_speech": pos,
        "grammatical_role": dep,
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "task": TASK_NAME,
    }
    return f"task: {TASK_NAME} payload: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def _build_vp_elements(root_token: Any) -> List[Dict[str, Any]]:
    """Build element list for a verb phrase: only the aux chain + main verb."""
    aux_tokens = sorted(
        [c for c in root_token.children if c.dep_ in {"aux", "auxpass", "neg"}],
        key=lambda t: t.i,
    )
    return [
        {"content": "{{WORD}}", "grammatical_role": t.dep_,
         "node_type": "Word", "part_of_speech": t.pos_}
        for t in (aux_tokens + [root_token])
    ]


def _get_phrase_text(head: Any, topic_key: str) -> str:
    """Extract the actual surface text of the phrase headed by this token."""
    if topic_key == "verb_phrase":
        # Only aux chain + main verb — exclude objects/complements
        aux_tokens = sorted(
            [c for c in head.children if c.dep_ in {"aux", "auxpass", "neg"}],
            key=lambda t: t.i,
        )
        tokens = [t for t in aux_tokens if t.i < head.i] + [head]
        return " ".join(t.text for t in tokens)
    else:
        # Full subtree of the head, left-to-right order
        return " ".join(t.text for t in sorted(head.subtree, key=lambda t: t.i))


def _has_content_children(token: Any) -> bool:
    return any(not c.is_punct and not c.is_space for c in token.children)


def _find_phrase_heads(doc: Any, topic_key: str) -> List[Any]:
    """Return spaCy tokens that head a phrase of the type described by topic_key."""
    heads: List[Any] = []

    if topic_key == "noun_phrase":
        for chunk in doc.noun_chunks:
            heads.append(chunk.root)
        # Fallback when spaCy finds no chunks (fragments, non-standard sentences)
        if not heads:
            for token in doc:
                if token.pos_ in {"NOUN", "PROPN"} and token.dep_ in {
                    "nsubj", "nsubjpass", "dobj", "pobj", "attr", "oprd"
                } and _has_content_children(token):
                    heads.append(token)

    elif topic_key == "verb_phrase":
        root = next((t for t in doc if t.dep_ == "ROOT"), None)
        if root:
            heads.append(root)

    elif topic_key == "prepositional_phrases":
        for token in doc:
            # "ROOT" catches fragment sentences like "In the latter case"
            # SCONJ/prep catches complex prepositions: "because of", "due to"
            if token.pos_ in {"ADP", "SCONJ"} and token.dep_ in {
                "prep", "agent", "dative", "pcomp", "ROOT"
            }:
                heads.append(token)

    elif topic_key == "adjective_phrase":
        for token in doc:
            # Accept VERB with acomp/xcomp (past participles: "relieved to go")
            if token.pos_ in {"ADJ", "VERB"} and token.dep_ in {
                "amod", "acomp", "attr", "oprd", "xcomp"
            }:
                heads.append(token)

    elif topic_key == "adverb_phrase":
        # Any ADV regardless of dep — simple adverbs are valid single-word adverb phrases
        for token in doc:
            if token.pos_ == "ADV":
                heads.append(token)
        # Fallback: adverbial PP (ADP/prep off a VERB) or adverbial clause
        if not heads:
            for token in doc:
                if token.dep_ in {"prep", "advcl"} and token.pos_ in {"ADP", "SCONJ", "VERB"}:
                    heads.append(token)

    elif topic_key in {"participle_phrase", "absolute_phrase"}:
        for token in doc:
            # acl = adjectival clause covers most participial constructions in spaCy
            if token.pos_ == "VERB" and token.dep_ in {
                "relcl", "advcl", "partmod", "acl"
            }:
                heads.append(token)
        # absolute_phrase: also ADJ/NOUN as head of dangling participial ("God willing")
        if topic_key == "absolute_phrase":
            for token in doc:
                if token.pos_ in {"ADJ", "NOUN"} and token.dep_ in {"advcl", "ccomp"}:
                    heads.append(token)

    # Require content children for everything except adverb_phrase and adjective_phrase
    # (where single-word phrases are linguistically valid)
    if topic_key in {"adverb_phrase", "adjective_phrase"}:
        return heads
    return [h for h in heads if _has_content_children(h)]


def _is_valid_leech_note(text: str) -> bool:
    """Lighter note validator for Leech glossary — min 5 words, must end on sentence boundary."""
    text = _norm(text)
    if len(text.split()) < 5:
        return False
    if not ENDS_WITH_PUNCT.search(text):
        return False
    if CROSS_REF_RE.search(text):
        return False
    if re.search(r"[,;:]\s*$", text):
        return False
    if _NOTE_STARTS_BUT_RE.match(text):
        return False
    if _NOTE_STARTS_DEF_RE.search(text):
        return False
    if _NOTE_ENDS_COLON_PERIOD_RE.search(text):
        return False
    if _NOTE_DOUBLE_COLON_RE.search(text):
        return False
    if _NOTE_TRAILING_DOT_DOT_RE.search(text):
        return False
    if _LEECH_NOTE_FORMULA_RE.match(text):
        return False
    if _LEECH_NOTE_SPECIFIC_VERB_RE.match(text):
        return False
    if _LEECH_NOTE_EXAMPLE_NAME_RE.search(text):
        return False
    return True


def _find_phrase_head_leech(doc: Any, topic_key: str) -> Any:
    """Find the phrase head token when the spaCy input IS the phrase (not a full sentence)."""
    if topic_key == "noun_phrase":
        chunks = list(doc.noun_chunks)
        if chunks:
            return chunks[0].root
        for t in doc:
            if t.pos_ in {"NOUN", "PROPN"}:
                return t
    elif topic_key == "verb_phrase":
        root = next((t for t in doc if t.dep_ == "ROOT"), None)
        if root and root.pos_ == "VERB":
            return root
        for t in doc:
            if t.pos_ == "VERB":
                return t
    elif topic_key == "adjective_phrase":
        for t in doc:
            if t.pos_ == "ADJ":
                return t
    elif topic_key == "adverb_phrase":
        for t in doc:
            if t.pos_ == "ADV":
                return t
    elif topic_key == "prepositional_phrases":
        for t in doc:
            if t.pos_ == "ADP":
                return t
    # comparative_phrase, participle_phrase, infinitival_clause, fallback
    return next((t for t in doc if t.dep_ == "ROOT"), doc[0] if len(doc) > 0 else None)


def load_and_filter_phrase_pairs(base_dir: Path) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    for source_id, rel_path in SOURCES:
        path = base_dir / rel_path
        if not path.exists():
            continue
        count_out = 0
        for row in _iter_jsonl(path):
            if row.get("topic_key") not in PHRASE_TOPICS:
                continue
            note = _clean_notation(row.get("notation_text") or "")
            if not _is_valid_note(note):
                continue
            sentence = _norm(row.get("context_text") or "")
            if not _is_valid_sentence(sentence):
                continue
            pairs.append({
                "topic_key": row["topic_key"],
                "note": note,
                "sentence": sentence,
                "source_id": source_id,
                "entry_head": _norm(row.get("entry_head") or ""),
            })
            count_out += 1
        if count_out:
            print(f"  {source_id} (phrase): {count_out} passed filter")
    return pairs


def build_phrase_rows(pairs: List[Dict[str, Any]], nlp: Any, max_per_target: int = 4) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    target_counts: Dict[str, int] = {}
    skipped_no_phrase = 0

    for pair in pairs:
        doc = nlp(pair["sentence"])
        heads = _find_phrase_heads(doc, pair["topic_key"])
        if not heads:
            skipped_no_phrase += 1
            continue

        target_text = pair["note"]
        target_key = hashlib.sha1(target_text.encode()).hexdigest()
        if target_counts.get(target_key, 0) >= max_per_target:
            continue

        for head in heads[:2]:  # at most 2 phrases per sentence to avoid over-sampling
            if pair["topic_key"] == "verb_phrase":
                elements = _build_vp_elements(head)
            else:
                head_contract = _build_node_contract(head, "", depth=0, max_depth=2)
                elements = head_contract.get("linguistic_elements")
                # Leaf heads (no children) — valid for single-word adj/adv phrases
                if not elements:
                    elements = [{"content": "{{WORD}}", "grammatical_role": head.dep_,
                                 "node_type": "Word", "part_of_speech": head.pos_}]
            if not elements:
                continue
            phrase_text = _get_phrase_text(head, pair["topic_key"])
            # Drop phrases that are book-internal citations (section refs, table labels).
            # INLINE_SECTION_RE covers "3.12" style; the broader pattern below
            # also catches "4.6.4" and parenthetical "(2.4.7)" forms.
            _CITATION_IN_PHRASE = re.compile(r"\(\s*\d+[\.\d]+\s*\)|\b\d+\.\d+[\.\d]*")
            if (INLINE_SECTION_RE.search(phrase_text)
                    or _CITATION_IN_PHRASE.search(phrase_text)
                    or _TABLE_REF_RE.match(phrase_text)):
                continue
            # Drop phrase content that is just a grammatical term label (e.g. "verb")
            if _GRAMMAR_TERM_RE.match(phrase_text):
                continue
            # Cambridge "-ed forms before a noun" note must not pair with non-ed heads
            if _CAMBRIDGE_EDFORM_NOTE_RE.search(target_text):
                if not head.text.lower().endswith("ed"):
                    continue
            # "between + pronoun" note must not pair with a phrase lacking an object pronoun
            if _BETWEEN_PRONOUN_NOTE_RE.search(target_text):
                if not set(phrase_text.lower().split()).intersection(_OBJECT_PRONOUNS):
                    continue
            # "use between/among" note: phrase must contain that specific preposition
            if _USE_BETWEEN_NOTE_RE.search(target_text) and "between" not in phrase_text.lower():
                continue
            if _USE_AMONG_NOTE_RE.search(target_text) and "among" not in phrase_text.lower():
                continue
            # Single degree modifier in adverb_phrase is not a full adverb phrase
            if pair["topic_key"] == "adverb_phrase" and _SINGLE_DEGREE_MOD_RE.match(phrase_text):
                continue
            # Adverb-modifies-X note with a single bare adverb: phrase is incomplete
            if pair["topic_key"] == "adverb_phrase" and _ADV_MODIFY_NOTE_RE.search(target_text):
                if " " not in phrase_text.strip():
                    continue
            # Finite subordinating clause extracted as participle/adverb phrase
            if pair["topic_key"] in {"participle_phrase", "adverb_phrase"} and _FINITE_SUBORD_CLAUSE_RE.match(phrase_text):
                continue
            # Phrasal prepositional verb note: extracted prep phrase is a fragment
            if pair["topic_key"] == "prepositional_phrases" and _PHRASAL_PREP_VERB_NOTE_RE.search(target_text):
                continue
            # Sequence-of-tenses note must not pair with a single verb phrase
            if pair["topic_key"] == "verb_phrase" and _SEQUENCE_OF_TENSES_NOTE_RE.search(target_text):
                continue
            # Adverbial clause mobility note is sentence-level, not verb-phrase-level
            if pair["topic_key"] == "verb_phrase" and _ADVERBIAL_CLAUSE_MOBILE_NOTE_RE.search(target_text):
                continue
            # Complementation note needs a phrase with a visible complement
            if _COMPLEMENTATION_NOTE_RE.search(target_text) and " " not in phrase_text.strip():
                continue
            context = json.dumps(elements, ensure_ascii=False, sort_keys=True)
            input_text = _build_phrase_input(phrase_text, context, head.pos_, head.dep_)

            dedup_key = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            target_counts[target_key] = target_counts.get(target_key, 0) + 1

            rows.append({
                "id": _stable_id(pair["source_id"], pair["sentence"], phrase_text, context, target_text),
                "input": input_text,
                "target": target_text,
                "node_type": "Phrase",
                "source_id": pair["source_id"],
                "sentence_text": pair["sentence"],
                "entry_head": pair["entry_head"],
                "topic_key": pair["topic_key"],
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                "service_fields": {"part_of_speech": head.pos_, "grammatical_role": head.dep_},
            })

            if target_counts.get(target_key, 0) >= max_per_target:
                break

    if skipped_no_phrase:
        print(f"  (phrase) skipped {skipped_no_phrase} pairs with no matching phrase head")
    return rows


def load_and_filter_pairs(base_dir: Path) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    for source_id, rel_path in SOURCES:
        path = base_dir / rel_path
        if not path.exists():
            print(f"  SKIP (not found): {path}")
            continue
        count_in = count_out = 0
        for row in _iter_jsonl(path):
            count_in += 1
            if row.get("topic_key") not in SENTENCE_TOPICS:
                continue
            sentence = _norm(row.get("context_text") or "")
            note = _clean_notation(row.get("notation_text") or "")
            if not _is_valid_sentence(sentence):
                continue
            if not _is_valid_note(note):
                continue
            pairs.append({
                "sentence": sentence,
                "note": note,
                "topic_key": row.get("topic_key", ""),
                "source_id": source_id,
                "entry_head": _norm(row.get("entry_head") or ""),
            })
            count_out += 1
        print(f"  {source_id}: {count_in} → {count_out} passed filter")
    return pairs


def build_sentence_rows(
    pairs: List[Dict[str, Any]],
    nlp: Any,
    max_per_target: int = 4,
    topic_max: Dict[str, int] | None = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    target_counts: Dict[str, int] = {}
    topic_row_counts: Dict[str, int] = {}
    for pair in pairs:
        topic_key = pair.get("topic_key", "")
        if topic_max is not None:
            cap = topic_max.get(topic_key, max_per_target * 20)
            if topic_row_counts.get(topic_key, 0) >= cap:
                continue

        content, service = _parse_sentence_contract(pair["sentence"], nlp)
        has_subject = service.pop("_has_subject", True)

        # Reject non-sentences: phrases / fragments that lack a finite verb
        # (spaCy ROOT would be ADP, NOUN, ADJ, etc. rather than VERB/AUX).
        if service.get("part_of_speech") not in {"VERB", "AUX"}:
            continue

        # Reject VP fragments: passive verb phrases extracted without a subject
        # ("have been found", "will be sent", "be handed down").
        if not has_subject:
            continue

        # TAM consistency guard: reject pairs where the detected grammatical
        # feature contradicts the topic label (e.g. present-simple sentence in
        # the "perfect" chapter — it's a contrast example, not a teaching example).
        guard = TAM_TOPIC_GUARDS.get(topic_key)
        if guard is not None and not guard(service):
            continue

        lex_guard = LEXICAL_TOPIC_GUARDS.get(topic_key)
        if lex_guard is not None and not lex_guard(pair["sentence"]):
            continue

        target_text = pair["note"]

        # Sentence target must contain linguistic meta-language; if it contains
        # none it is a concrete example sentence used as a note (book artifact).
        if not _LINGUISTIC_META_RE.search(target_text):
            continue

        # Relative clause omission guard: drop pairs where target talks about
        # omitting the relative pronoun but the sentence has an explicit one.
        if topic_key == "relative_clauses" and _REL_OMISSION_NOTE_RE.search(target_text):
            if _REL_PRONOUN_RE.search(pair["sentence"]):
                continue

        # Non-defining RC guard: note describes non-defining (comma-delimited) RC
        # but the example sentence uses a defining (no comma) relative clause.
        if topic_key == "relative_clauses" and _NON_DEFINING_RC_NOTE_RE.search(target_text):
            if not _NON_DEFINING_RC_COMMA_RE.search(pair["sentence"]):
                continue

        # Fronted-if-then guard: note is about fronted "if"-clause + optional "then",
        # but sentence uses "unless" or "except if" (a different conditional form).
        if topic_key == "conditional_sentences" and _FRONTED_IF_THEN_NOTE_RE.search(target_text):
            s_lower = pair["sentence"].lower()
            if "unless" in s_lower or "except if" in s_lower:
                continue

        # Unless-focus guard: note focuses on "unless" as a negative conditional
        # conjunction, but the sentence is a plain "if"-clause example.
        if topic_key == "conditional_sentences" and _UNLESS_FOCUS_NOTE_RE.search(target_text):
            if "unless" not in pair["sentence"].lower():
                continue

        # Third conditional guard: note describes the third conditional (past
        # hypothetical) but sentence uses "wish"/"if only" (wish-structure) or is
        # a mixed conditional (if-clause + plain modal result, no "modal have").
        if topic_key == "conditional_sentences" and _THIRD_COND_NOTE_RE.search(target_text):
            if re.search(r"\bwish\b|\bif\s+only\b", pair["sentence"], re.I):
                continue
            if re.search(r"\bif\b", pair["sentence"], re.I):
                if not _PERFECT_MODAL_RE.search(pair["sentence"]):
                    continue
                if not _if_clause_has_past_perfect(pair["sentence"]):
                    continue
            else:
                if not _PERFECT_MODAL_RE.search(pair["sentence"]):
                    continue

        # Wish-focus guard: target is specifically about wish/if-only structures
        if topic_key == "conditional_sentences" and _WISH_FOCUS_NOTE_RE.search(target_text):
            if not re.search(r"\bwish\b|\bif\s+only\b", pair["sentence"], re.I):
                continue

        # Reported speech subtype guards
        if topic_key == "reported_speech":
            if _REPORTED_QUESTION_TARGET_RE.search(target_text) and _REPORTED_STATEMENT_CONTENT_RE.search(pair["sentence"]):
                continue
            if _REPORTED_STATEMENT_TARGET_RE.search(target_text) and _REPORTED_QUESTION_CONTENT_RE.search(pair["sentence"]):
                continue

        # By-agent guard: note is about the agent/by-phrase role but sentence has no "by"
        if topic_key == "passive_voice" and _BY_AGENT_TARGET_RE.search(target_text):
            if "by" not in pair["sentence"].lower().split():
                continue

        # Agent noun guard: notes defining agent nouns (employer/teacher/manager)
        # must not be paired with passive sentences.
        if _AGENT_NOUN_NOTE_RE.search(target_text):
            continue

        # Primary verb imperative guard: note is about "be/have/do" as imperatives
        # but sentence uses a different verb in imperative form.
        if topic_key == "imperative" and _LEECH_PRIMARY_IMP_NOTE_RE.search(target_text):
            if not re.search(r"^\s*(be|have|do|don'?t\s+(be|have|do))\b", pair["sentence"], re.I):
                continue

        # First-person imperative guard: note says "first-person imperative"
        # (urges action by both speaker and hearer) → sentence must start with "let's/us/me".
        if topic_key == "imperative" and _FIRST_PERSON_IMP_NOTE_RE.search(target_text):
            if not _LETS_RE.match(pair["sentence"]):
                continue

        input_text = _build_sentence_input(content, service)

        dedup_key = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        target_key = hashlib.sha1(target_text.encode()).hexdigest()
        if target_counts.get(target_key, 0) >= max_per_target:
            continue
        target_counts[target_key] = target_counts.get(target_key, 0) + 1

        topic_row_counts[topic_key] = topic_row_counts.get(topic_key, 0) + 1

        rows.append({
            "id": _stable_id(pair["source_id"], pair["sentence"], target_text),
            "input": input_text,
            "target": target_text,
            "node_type": "Sentence",
            "source_id": pair["source_id"],
            "sentence_text": pair["sentence"],
            "entry_head": pair["entry_head"],
            "topic_key": topic_key,
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "service_fields": service,
        })
    return rows


_ENTRY_POS_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _entry_bare(entry_head: str) -> str:
    """Strip trailing POS label in parens: 'take away (preposition)' → 'take away'."""
    return _ENTRY_POS_PAREN_RE.sub("", entry_head).strip().lower()


def load_and_filter_word_pairs(base_dir: Path) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    for source_id, rel_path in WORD_SOURCES:
        path = base_dir / rel_path
        if not path.exists():
            print(f"  SKIP (not found): {path}")
            continue
        count_in = count_out = 0
        for row in _iter_jsonl(path):
            count_in += 1
            if row.get("pair_method") not in {"wiktionary_defn_v1", "cambridge_learner_defn_v1"}:
                continue
            word = _norm(row.get("context_text") or "")
            note = _clean_notation(row.get("notation_text") or "")
            if not word or len(word.split()) > 5:
                continue
            if len(note.split()) < 5 or not ENDS_WITH_PUNCT.search(note):
                continue
            if CROSS_REF_RE.search(note):
                continue
            # Validate that context_text matches the entry_head bare form exactly.
            # Drops four classes of mismatch identified in QA analysis:
            #   1. Multiword context ('as if', 'in front', 'take away') — spaCy would
            #      pick only ROOT, so content gets truncated to a single token
            #   2. Multiword entry, single-word context ('take' for 'take away')
            #   3. Hyphenated compound entries ('twenty' for 'twenty-five')
            #   4. Inflected/derived entries where bare form != context
            #      ('going', 'granted', 'failing' — spaCy lemmatises to base form)
            bare = _entry_bare(_norm(row.get("entry_head") or ""))
            word_lower = word.lower()
            if " " in word_lower:
                continue   # multiword context → not a single-word Word contract
            if " " in bare and word_lower != bare:
                continue   # multiword entry, context is only a fragment
            if "-" in bare:
                continue   # hyphenated compound (twenty-five, eighty-one)
            if bare and bare != word_lower:
                continue   # inflected or unrelated entry (going, granted, etc.)
            pairs.append({
                "word": word,
                "note": note,
                "source_id": source_id,
                "entry_head": _norm(row.get("entry_head") or ""),
            })
            count_out += 1
        print(f"  {source_id} (word): {count_in} → {count_out} passed filter")
    return pairs


def build_word_rows(pairs: List[Dict[str, Any]], nlp: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    pos_counts: Counter = Counter()
    for pair in pairs:
        service = _parse_word_contract(pair["word"], nlp)
        service.pop("lemma", None)  # discard lemma — use entry word as-is
        word_content = pair["word"]
        input_text = _build_word_input(word_content, service)
        target_text = pair["note"]

        dedup_key = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        pos = service.get("part_of_speech", "")
        cap = WORD_POS_CAPS.get(pos)
        if cap is not None and pos_counts[pos] >= cap:
            continue
        pos_counts[pos] += 1

        rows.append({
            "id": _stable_id(pair["source_id"], pair["word"], target_text),
            "input": input_text,
            "target": target_text,
            "node_type": "Word",
            "source_id": pair["source_id"],
            "sentence_text": pair["word"],
            "entry_head": pair["entry_head"],
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "service_fields": service,
        })
    return rows


def build_leech_rows(
    base_dir: Path, nlp: Any
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Build (sentence_rows, phrase_rows, word_rows) from Leech glossary pairs.

    Unlike the book-pair pipeline, Leech examples ARE the linguistic unit —
    not context sentences to extract from — so contracts are built directly
    from example_text without phrase-head search in a larger sentence.
    """
    source_id, rel_path = LEECH_SOURCE
    path = base_dir / rel_path
    if not path.exists():
        print(f"  SKIP Leech (not found): {path}")
        return [], [], []

    sent_rows: List[Dict[str, Any]] = []
    phrase_rows: List[Dict[str, Any]] = []
    word_rows: List[Dict[str, Any]] = []
    seen: set = set()
    pos_counts: Counter = Counter()

    for pair in _iter_jsonl(path):
        note = _norm(pair.get("note", ""))
        if not _is_valid_leech_note(note):
            continue
        example = _norm(pair.get("example_text", ""))
        if not example:
            continue
        topic_key = pair.get("topic_key", "")
        entry_head = pair.get("entry_head", "")

        if topic_key in LEECH_SENTENCE_TOPICS:
            if not _is_valid_sentence(example):
                continue
            lex_guard = LEXICAL_TOPIC_GUARDS.get(topic_key)
            if lex_guard is not None and not lex_guard(example):
                continue
            content, service = _parse_sentence_contract(example, nlp)
            has_subject = service.pop("_has_subject", True)
            if service.get("part_of_speech") not in {"VERB", "AUX"}:
                continue
            # VP fragment without a subject ("have been found", "will be sent")
            if not has_subject:
                continue
            guard = TAM_TOPIC_GUARDS.get(topic_key)
            if guard is not None and not guard(service):
                continue
            target_text = note
            # Sentence target must contain linguistic meta-language
            if not _LINGUISTIC_META_RE.search(target_text):
                continue
            if topic_key == "relative_clauses" and _REL_OMISSION_NOTE_RE.search(target_text):
                if _REL_PRONOUN_RE.search(example):
                    continue
            if topic_key == "relative_clauses" and _NON_DEFINING_RC_NOTE_RE.search(target_text):
                if not _NON_DEFINING_RC_COMMA_RE.search(example):
                    continue
            if topic_key == "conditional_sentences" and _FRONTED_IF_THEN_NOTE_RE.search(target_text):
                s_lower = example.lower()
                if "unless" in s_lower or "except if" in s_lower:
                    continue
            if topic_key == "conditional_sentences" and _UNLESS_FOCUS_NOTE_RE.search(target_text):
                if "unless" not in example.lower():
                    continue
            if topic_key == "conditional_sentences" and _THIRD_COND_NOTE_RE.search(target_text):
                if re.search(r"\bwish\b|\bif\s+only\b", example, re.I):
                    continue
                if re.search(r"\bif\b", example, re.I):
                    if not _PERFECT_MODAL_RE.search(example):
                        continue
                    if not _if_clause_has_past_perfect(example):
                        continue
                else:
                    if not _PERFECT_MODAL_RE.search(example):
                        continue
            # Wish-focus guard: target is specifically about wish/if-only structures
            if topic_key == "conditional_sentences" and _WISH_FOCUS_NOTE_RE.search(target_text):
                if not re.search(r"\bwish\b|\bif\s+only\b", example, re.I):
                    continue
            # Conditional result-only fragment: "she would be furious" (no if-clause)
            if topic_key == "conditional_sentences" and _CONDITIONAL_RESULT_ONLY_RE.match(example):
                if not re.search(r"\bif\b|\bunless\b", example, re.I):
                    continue
            # Conditional if-only fragment: "If the principal knew about it" (no main clause)
            if topic_key == "conditional_sentences" and _IF_ONLY_FRAGMENT_RE.match(example):
                if "," not in example and len(example.split()) <= 10:
                    continue
            # By-agent guard: note about agent/by-phrase but sentence has no "by"
            if topic_key == "passive_voice" and _BY_AGENT_TARGET_RE.search(target_text):
                if "by" not in example.lower().split():
                    continue
            if _AGENT_NOUN_NOTE_RE.search(target_text):
                continue
            if topic_key == "imperative" and _LEECH_PRIMARY_IMP_NOTE_RE.search(target_text):
                if not re.search(r"^\s*(be|have|do|don'?t\s+(be|have|do))\b", example, re.I):
                    continue
            # First-person imperative: sentence must start with "let's/us/me"
            if topic_key == "imperative" and _FIRST_PERSON_IMP_NOTE_RE.search(target_text):
                if not _LETS_RE.match(example):
                    continue
            # Adverbial clause topic: question sentences are not adverbial clauses
            if topic_key == "adverbial_clause" and example.rstrip().endswith("?"):
                continue
            # Adverbial clause topic: sentence must contain a subordinating conjunction
            if topic_key == "adverbial_clause" and not _SUBORD_CONJ_RE.search(example):
                continue
            # Interrogative topic: sentence must be a question
            if topic_key == "interrogative" and "?" not in example:
                continue
            # Reported speech subtype guards
            if topic_key == "reported_speech":
                if _REPORTED_QUESTION_TARGET_RE.search(target_text) and _REPORTED_STATEMENT_CONTENT_RE.search(example):
                    continue
                if _REPORTED_STATEMENT_TARGET_RE.search(target_text) and _REPORTED_QUESTION_CONTENT_RE.search(example):
                    continue
            input_text = _build_sentence_input(content, service)
            dk = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
            if dk in seen:
                continue
            seen.add(dk)
            sent_rows.append({
                "id": _stable_id(source_id, example, target_text),
                "input": input_text,
                "target": target_text,
                "node_type": "Sentence",
                "source_id": source_id,
                "sentence_text": example,
                "entry_head": entry_head,
                "topic_key": topic_key,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                "service_fields": service,
            })

        elif topic_key in LEECH_PHRASE_TOPICS:
            doc = nlp(example)
            # Reject fragments that parse as sentences (ROOT=VERB/AUX with ≥2 tokens):
            # they are incomplete sentences, not phrases.
            root = next((t for t in doc if t.dep_ == "ROOT"), None)
            if root and root.pos_ in {"VERB", "AUX"} and len(doc) >= 2:
                continue
            head = _find_phrase_head_leech(doc, topic_key)
            if head is None:
                continue
            if topic_key == "verb_phrase":
                elements = _build_vp_elements(head)
            else:
                head_contract = _build_node_contract(head, "", depth=0, max_depth=2)
                elements = head_contract.get("linguistic_elements") or [
                    {"content": "{{WORD}}", "grammatical_role": head.dep_,
                     "node_type": "Word", "part_of_speech": head.pos_}
                ]
            if not elements:
                continue
            phrase_text = (
                _get_phrase_text(head, topic_key) if topic_key in PHRASE_TOPICS else example
            )
            if _GRAMMAR_TERM_RE.match(phrase_text):
                continue
            if _CAMBRIDGE_EDFORM_NOTE_RE.search(note):
                if not head.text.lower().endswith("ed"):
                    continue
            if _BETWEEN_PRONOUN_NOTE_RE.search(note):
                if not set(phrase_text.lower().split()).intersection(_OBJECT_PRONOUNS):
                    continue
            if _USE_BETWEEN_NOTE_RE.search(note) and "between" not in phrase_text.lower():
                continue
            if _USE_AMONG_NOTE_RE.search(note) and "among" not in phrase_text.lower():
                continue
            # Single degree modifier in adverb_phrase is not a full adverb phrase
            if topic_key == "adverb_phrase" and _SINGLE_DEGREE_MOD_RE.match(phrase_text):
                continue
            # Adverb-modifies-X note with a single bare adverb: phrase is incomplete
            if topic_key == "adverb_phrase" and _ADV_MODIFY_NOTE_RE.search(note):
                if " " not in phrase_text.strip():
                    continue
            # Finite subordinating clause extracted as participle/adverb phrase
            if topic_key in {"participle_phrase", "adverb_phrase"} and _FINITE_SUBORD_CLAUSE_RE.match(phrase_text):
                continue
            # Phrasal prepositional verb note: extracted prep phrase is a fragment
            if topic_key == "prepositional_phrases" and _PHRASAL_PREP_VERB_NOTE_RE.search(note):
                continue
            # Sequence-of-tenses note must not pair with a single verb phrase
            if topic_key == "verb_phrase" and _SEQUENCE_OF_TENSES_NOTE_RE.search(note):
                continue
            # Adverbial clause mobility note is sentence-level, not verb-phrase-level
            if topic_key == "verb_phrase" and _ADVERBIAL_CLAUSE_MOBILE_NOTE_RE.search(note):
                continue
            # Complementation note needs a phrase with a visible complement
            if _COMPLEMENTATION_NOTE_RE.search(note) and " " not in phrase_text.strip():
                continue
            # Comparative phrase mismatch guards (Leech comparative_phrase topic)
            if topic_key == "comparative_phrase":
                if _EQUAL_COMPARISON_NOTE_RE.search(note) and _MORE_LESS_START_RE.match(phrase_text):
                    continue
                # "as big/famous/many" must not get an unequal-comparison note
                if _UNEQUAL_COMPARISON_NOTE_RE.search(note) and _AS_COMPARATIVE_START_RE.match(phrase_text):
                    continue
                # "more/less + adj" or "as + adj" must not get a comparative-clause-def note
                if _COMPARATIVE_CLAUSE_DEF_RE.search(note) and (
                    _AS_ADJ_ONLY_RE.match(phrase_text) or _MORE_LESS_START_RE.match(phrase_text)
                ):
                    continue
                # "more/less + adj" must not get an irregular comparative note (good→better)
                if _IRREGULAR_COMPARATIVE_NOTE_RE.search(note) and _MORE_LESS_START_RE.match(phrase_text):
                    continue
                if _ER_COMPARATIVE_NOTE_RE.search(note) and _MORE_LESS_START_RE.match(phrase_text):
                    continue
            context = json.dumps(elements, ensure_ascii=False, sort_keys=True)
            pos = PHRASE_TOPIC_POS.get(topic_key, head.pos_)
            input_text = _build_phrase_input(phrase_text, context, pos, head.dep_)
            target_text = note
            dk = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
            if dk in seen:
                continue
            seen.add(dk)
            phrase_rows.append({
                "id": _stable_id(source_id, example, phrase_text, target_text),
                "input": input_text,
                "target": target_text,
                "node_type": "Phrase",
                "source_id": source_id,
                "sentence_text": example,
                "entry_head": entry_head,
                "topic_key": topic_key,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                "service_fields": {"part_of_speech": pos, "grammatical_role": head.dep_},
            })

        elif topic_key in LEECH_WORD_POS_TOPICS:
            # Drop entries whose entry_head names a multi-word construction
            # (phrasal verb, prepositional verb, light verb, prepositional adverb).
            # spaCy picks only the ROOT token, so the content would be just the verb
            # or preposition — not the full unit the note describes.
            if _LEECH_MULTIWORD_ENTRY_RE.search(entry_head):
                continue
            doc = nlp(example)
            # Prefer a token whose POS matches the topic label (e.g. "this bad
            # weather" for ADJ → "bad", not ROOT "weather").  Fall back to ROOT,
            # then doc[0] for single-token fragments.
            expected_pos = LEECH_WORD_TOPIC_POS.get(topic_key)
            word_token = (
                next((t for t in doc if t.pos_ == expected_pos), None)
                or next((t for t in doc if t.dep_ == "ROOT"), doc[0])
            )
            # If the best token still doesn't match the topic's expected POS,
            # the example is a cross-pair (e.g. "tall" in the ADV entry,
            # "third" in the NUM entry as an adjective).  Drop it.
            if expected_pos and word_token.pos_ != expected_pos:
                continue
            service = {
                "part_of_speech": word_token.pos_,
                "grammatical_role": word_token.dep_,
            }
            word_content = word_token.lemma_ or example
            wl = word_content.lower()
            # Entry-head mismatch: lemma doesn't match the single-word entry bare form
            # (catches malformed lemmas like "rockie" from "Rockies")
            bare_entry = _entry_bare(entry_head).lower()
            if bare_entry and " " not in bare_entry and wl != bare_entry:
                continue
            # Pronoun person guard: reject cross-product person mismatches
            if topic_key == "PRON":
                if _PERSON_NOTE_FIRST_RE.search(note) and wl not in _FIRST_PERSON_PRONS:
                    continue
                if _PERSON_NOTE_SECOND_RE.search(note) and wl not in _SECOND_PERSON_PRONS:
                    continue
                if _PERSON_NOTE_THIRD_RE.search(note) and wl not in _THIRD_PERSON_PRONS:
                    continue
            # Demonstrative guard: relative/interrogative determiners (whose, which)
            # must not be paired with notes about demonstratives (this/that/these/those)
            if topic_key == "DET" and _DEMONSTRATIVE_NOTE_RE.search(note):
                if word_content.lower() not in _DEMONSTRATIVES:
                    continue
            # Articles guard: non-article determiners (some, whose, which…) must not
            # be paired with notes specifically about articles a/an/the.
            if topic_key == "DET" and _LEECH_ARTICLES_NOTE_RE.search(note):
                if word_content.lower() not in _ARTICLES:
                    continue
            # Relative pronoun note in DET topic: "which" used as a determiner should
            # not be paired with notes that discuss zero relative pronouns or "whom".
            if topic_key == "DET" and _RELATIVE_PRONOUN_NOTE_RE.search(note):
                continue
            # Modal auxiliary guard: non-modal verbs must not be paired with
            # notes that define or describe modal auxiliaries.
            if topic_key in {"VERB", "AUX"} and _LEECH_MODAL_AUX_NOTE_RE.search(note):
                if wl not in _MODAL_VERBS:
                    continue
            # Primary verb guard: non-primary verbs (not be/have/do) must not be
            # paired with notes that define primary auxiliary verbs.
            if topic_key in {"VERB", "AUX"} and _LEECH_PRIMARY_VERB_NOTE_RE.search(note):
                if wl not in _PRIMARY_VERBS:
                    continue
            # Auxiliary-added-before-main-verb note: only applies to aux/modal words
            if topic_key in {"VERB", "AUX"} and _AUX_ADDED_BEFORE_NOTE_RE.search(note):
                if wl not in _MODAL_VERBS and wl not in _PRIMARY_VERBS:
                    continue
            # Transitive/requires-object note must not pair with intransitive verbs
            if topic_key == "VERB" and _REQUIRES_OBJECT_NOTE_RE.search(note):
                if wl in _INTRANSITIVE_VERBS:
                    continue
            # Manner adverb guard: degree adverbs (more/most/really/worse…) must not be
            # paired with manner-adverb notes (which answer "How?").
            if topic_key == "ADV" and _LEECH_MANNER_NOTE_RE.search(note):
                if wl in _DEGREE_ADVERBS:
                    continue
            # Adj-identical adverb guard: note says adverb is identical in form to
            # adjective — only applies to actual adj-identical adverbs (long, early…)
            if topic_key == "ADV" and _ADJ_IDENTICAL_ADV_NOTE_RE.search(note):
                if wl not in _ADJ_IDENTICAL_ADVS:
                    continue
            # Gradable-words note: degree modifiers (very/too/more…) are not themselves
            # gradable words — they modify gradable words
            if topic_key == "ADV" and _GRADABLE_ADJ_NOTE_RE.search(note):
                if wl in _DEGREE_MODIFIER_WORDS:
                    continue
            # Attributive adjective guard: predicative-only adjectives (afraid,
            # alone…) must not be paired with notes defining attributive use.
            if topic_key == "ADJ" and _LEECH_ATTRIBUTIVE_NOTE_RE.search(note):
                if wl in _PREDICATIVE_ONLY_ADJS:
                    continue
            # Comparative clause in adj phrase: phrase-level concept, not a word
            if topic_key == "ADJ" and _COMPARATIVE_CLAUSE_DEF_RE.search(note):
                continue
            # Adverb phrase structural notes don't apply to a plain adjective word
            if topic_key == "ADJ" and (
                _OPTIONAL_MODIFIER_NOTE_RE.search(note) or _ADV_HEAD_PHRASE_NOTE_RE.search(note)
            ):
                continue
            input_text = _build_word_input(word_content, service)
            target_text = note
            dk = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
            if dk in seen:
                continue
            seen.add(dk)
            pos = service.get("part_of_speech", "")
            cap = WORD_POS_CAPS.get(pos)
            if cap is not None and pos_counts[pos] >= cap:
                continue
            pos_counts[pos] += 1
            word_rows.append({
                "id": _stable_id(source_id, example, target_text),
                "input": input_text,
                "target": target_text,
                "node_type": "Word",
                "source_id": source_id,
                "sentence_text": example,
                "entry_head": entry_head,
                "topic_key": topic_key,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                "service_fields": service,
            })

    print(
        f"  leech_glossary_2006: {len(sent_rows)} Sentence, "
        f"{len(phrase_rows)} Phrase, {len(word_rows)} Word rows"
    )
    return sent_rows, phrase_rows, word_rows


def split_rows(rows: List[Dict[str, Any]], seed: int = 42) -> Tuple[List, List, List]:
    rng = random.Random(seed)
    by_source: Dict[str, List] = defaultdict(list)
    for row in rows:
        by_source[row["source_id"]].append(row)

    train, dev, test = [], [], []
    for source_rows in by_source.values():
        rng.shuffle(source_rows)
        n = len(source_rows)
        n_dev = max(1, int(n * 0.1))
        n_test = max(1, int(n * 0.1))
        test.extend(source_rows[:n_test])
        dev.extend(source_rows[n_test: n_test + n_dev])
        train.extend(source_rows[n_test + n_dev:])
    return train, dev, test


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_review_csv(path: Path, all_rows: List[Dict[str, Any]]) -> None:
    """Export a human-review CSV with a readable content column.

    For Sentence rows: content = sentence_text (original sentence).
    For Phrase rows:   content = payload["content"] (extracted phrase text).
    For Word rows:     content = sentence_text (the word itself).
    """
    import csv

    def _extract_content(row: Dict[str, Any]) -> str:
        node_type = row.get("node_type", "")
        if node_type == "Sentence":
            return row.get("sentence_text", "")
        # Phrase and Word: parse payload["content"] (single word or extracted phrase text).
        # For Leech Word rows sentence_text is the full example, not the word itself.
        input_text = row.get("input", "")
        try:
            payload_str = input_text.split("payload: ", 1)[1]
            payload = json.loads(payload_str)
            return payload.get("content", row.get("sentence_text", ""))
        except Exception:
            return row.get("sentence_text", "")

    fieldnames = [
        "id", "split", "source_id", "node_type", "topic_key",
        "entry_head", "content", "sentence_text", "target",
        "not_correct", "issue_category", "reason",
        "node_type_not_correct", "node_type_comment",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                "id": row.get("id", ""),
                "split": row.get("_split", ""),
                "source_id": row.get("source_id", ""),
                "node_type": row.get("node_type", ""),
                "topic_key": row.get("topic_key", ""),
                "entry_head": row.get("entry_head", ""),
                "content": _extract_content(row),
                "sentence_text": row.get("sentence_text", ""),
                "target": row.get("target", ""),
                "not_correct": "",
                "issue_category": "",
                "reason": "",
                "node_type_not_correct": "",
                "node_type_comment": "",
            })


def main() -> None:
    parser = argparse.ArgumentParser(description="Build T5 RLE v1 dataset")
    parser.add_argument("--base-dir", default="/home/vlad/Dev/FYP_LLM")
    parser.add_argument("--output-dir", default="/home/vlad/Dev/FYP_LLM/data/processed_t5_v35_book_pairs")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    output_dir = Path(args.output_dir)

    from ela_pipeline.parse.spacy_parser import load_nlp
    print("Loading spaCy model...")
    nlp = load_nlp(args.spacy_model)

    print("Loading and filtering sentence pairs...")
    pairs = load_and_filter_pairs(base_dir)
    print(f"  Total: {len(pairs)}")

    print("Building Sentence rows...")
    sentence_rows = build_sentence_rows(pairs, nlp, topic_max=SENTENCE_TOPIC_MAX)
    print(f"  Sentence rows after dedup+cap: {len(sentence_rows)}")

    print("Loading and filtering Phrase pairs...")
    phrase_pairs = load_and_filter_phrase_pairs(base_dir)
    print(f"  Phrase pairs: {len(phrase_pairs)}")
    phrase_rows = build_phrase_rows(phrase_pairs, nlp)
    print(f"  Phrase rows after dedup+cap: {len(phrase_rows)}")

    print("Loading and filtering Word pairs...")
    word_pairs = load_and_filter_word_pairs(base_dir)
    print(f"  Word pairs: {len(word_pairs)}")
    word_rows = build_word_rows(word_pairs, nlp)
    print(f"  Word rows after dedup: {len(word_rows)}")

    print("Building Leech glossary rows...")
    leech_sent, leech_phrase, leech_word = build_leech_rows(base_dir, nlp)
    sentence_rows += leech_sent
    phrase_rows += leech_phrase
    word_rows += leech_word
    print(f"  Sentence total (incl. Leech): {len(sentence_rows)}")
    print(f"  Phrase total (incl. Leech):   {len(phrase_rows)}")
    print(f"  Word total (incl. Leech):     {len(word_rows)}")

    rows = sentence_rows + phrase_rows + word_rows
    train, dev, test = split_rows(rows, seed=args.seed)
    all_rows = train + dev + test

    node_counts = dict(Counter(r["node_type"] for r in all_rows))
    source_counts = dict(Counter(r["source_id"] for r in all_rows))
    topic_counts = dict(
        sorted(Counter(r.get("topic_key", "") for r in sentence_rows).items(), key=lambda x: -x[1])
    )

    stats = {
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "total": len(all_rows),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "node_counts": node_counts,
        "sources": source_counts,
        "sentence_topic_counts": topic_counts,
    }

    # Tag rows with their split for the review CSV
    for r in train:
        r["_split"] = "train"
    for r in dev:
        r["_split"] = "dev"
    for r in test:
        r["_split"] = "test"

    write_jsonl(output_dir / "train.jsonl", train)
    write_jsonl(output_dir / "dev.jsonl", dev)
    write_jsonl(output_dir / "test.jsonl", test)
    write_jsonl(output_dir / "all.jsonl", all_rows)
    write_json(output_dir / "stats.json", stats)

    review_csv_path = output_dir / "v35_review.csv"
    write_review_csv(review_csv_path, all_rows)
    print(f"\nReview CSV written to: {review_csv_path}")

    print(json.dumps(stats, ensure_ascii=False, indent=2))

    # Print a few examples
    print("\n--- Sample Sentence input ---")
    for r in sentence_rows[:2]:
        print(f"  input : {r['input'][:200]}")
        print(f"  target: {r['target'][:100]}")
        print()
    print("--- Sample Phrase input ---")
    for r in phrase_rows[:2]:
        print(f"  input : {r['input'][:200]}")
        print(f"  target: {r['target'][:100]}")
        print()
    print("--- Sample Word input ---")
    for r in word_rows[:2]:
        print(f"  input : {r['input'][:200]}")
        print(f"  target: {r['target'][:100]}")
        print()


if __name__ == "__main__":
    main()
