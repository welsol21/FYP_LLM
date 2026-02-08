"""Build contract-compliant skeleton JSON from text using spaCy."""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ela_pipeline.contract import blank_node


WORD_POS_MAP = {
    "NOUN": "noun",
    "PROPN": "proper noun",
    "PRON": "pronoun",
    "VERB": "verb",
    "AUX": "auxiliary verb",
    "ADJ": "adjective",
    "ADV": "adverb",
    "ADP": "preposition",
    "DET": "article",
    "CCONJ": "coordinating conjunction",
    "SCONJ": "subordinating conjunction",
    "PART": "particle",
    "NUM": "numeral",
    "INTJ": "interjection",
    "PUNCT": "punctuation",
    "X": "other",
}


def _word_tense(token) -> str:
    morph = token.morph
    verb_form = morph.get("VerbForm")
    tense = morph.get("Tense")

    if "Part" in verb_form:
        if token.tag_ == "VBG":
            return "present participle"
        if token.tag_ == "VBN":
            return "past participle"
        return "participle"
    if "Fin" in verb_form:
        if "Past" in tense:
            return "past"
        if "Pres" in tense:
            return "present"
    return "null"


def _phrase_candidates(sent) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    seen: Set[Tuple[int, int]] = set()

    for chunk in sent.noun_chunks:
        key = (chunk.start, chunk.end)
        if key not in seen:
            spans.append((chunk.start, chunk.end, "noun phrase"))
            seen.add(key)

    for token in sent:
        if token.dep_ == "ROOT" and token.pos_ in {"VERB", "AUX"}:
            left_indices = [token.i] + [
                c.i for c in token.children if c.dep_ in {"aux", "auxpass", "neg", "prt"}
            ]
            right_indices = [token.i] + [
                c.i
                for c in token.children
                if c.dep_ in {"aux", "auxpass", "neg", "prt", "dobj", "obj", "iobj", "attr", "acomp", "xcomp", "advmod"}
            ]

            start = min(left_indices)
            end = max(right_indices) + 1
            key = (start, end)
            if key not in seen:
                spans.append((start, end, "verb phrase"))
                seen.add(key)

    for token in sent:
        if token.pos_ == "ADP":
            start = token.i
            end = token.right_edge.i + 1
            key = (start, end)
            if key not in seen and end > start:
                spans.append((start, end, "prepositional phrase"))
                seen.add(key)

    spans.sort(key=lambda s: (s[0], s[1]))
    return spans


def build_skeleton(text: str, nlp) -> Dict[str, Dict]:
    doc = nlp(text)
    output: Dict[str, Dict] = {}

    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not sent_text:
            continue

        sentence_node = blank_node("Sentence", sent_text, "sentence", tense="null")

        for start, end, phrase_pos in _phrase_candidates(sent):
            span = doc[start:end]
            phrase_text = span.text.strip()
            if not phrase_text:
                continue

            phrase_node = blank_node("Phrase", phrase_text, phrase_pos, tense="null")
            for token in span:
                if token.is_space:
                    continue
                word_node = blank_node(
                    "Word",
                    token.text,
                    WORD_POS_MAP.get(token.pos_, "other"),
                    tense=_word_tense(token),
                )
                phrase_node["linguistic_elements"].append(word_node)

            sentence_node["linguistic_elements"].append(phrase_node)

        if not sentence_node["linguistic_elements"]:
            # Fallback: single phrase with all non-space tokens
            phrase_node = blank_node("Phrase", sent_text, "clause", tense="null")
            for token in sent:
                if token.is_space:
                    continue
                word_node = blank_node(
                    "Word",
                    token.text,
                    WORD_POS_MAP.get(token.pos_, "other"),
                    tense=_word_tense(token),
                )
                phrase_node["linguistic_elements"].append(word_node)
            sentence_node["linguistic_elements"].append(phrase_node)

        output[sent_text] = sentence_node

    return output
