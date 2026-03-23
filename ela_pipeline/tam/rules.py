"""Deterministic TAM rules for sentence and phrase levels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from ela_pipeline.constants import BE_FORMS, FUTURE_MODALS, HAVE_FORMS, NEGATIONS


@dataclass
class TamResult:
    tense: str
    aspect: str
    voice: str
    modal: str
    polarity: str
    mood: str
    finiteness: str
    construction: str

    @property
    def label(self) -> str:
        modal_part = f" modal={self.modal}" if self.modal else ""
        return f"{self.tense} {self.aspect} {self.voice}{modal_part} {self.polarity}".strip()

    @property
    def short_tense(self) -> str:
        if self.tense == "none":
            return "null"
        if self.aspect == "simple":
            return self.tense
        return f"{self.tense} {self.aspect}".strip()


def _token_seq(tokens: Iterable) -> List:
    return [t for t in tokens if not t.is_space]


def detect_tam(tokens: Iterable) -> TamResult:
    seq = _token_seq(tokens)
    lowered = [t.lemma_.lower() for t in seq]
    finite_markers = [t for t in seq if "Fin" in t.morph.get("VerbForm") or t.tag_ == "MD"]

    modal = ""
    for t in seq:
        if t.tag_ == "MD":
            modal = t.lemma_.lower()
            break

    has_neg = any(t.dep_ == "neg" or t.lower_ in NEGATIONS for t in seq)
    has_vbn = any(t.tag_ == "VBN" for t in seq)
    has_vbg = any(t.tag_ == "VBG" for t in seq)
    has_be = any(l in BE_FORMS for l in lowered)
    has_have = any(l in HAVE_FORMS for l in lowered)

    passive = any(t.dep_ == "auxpass" for t in seq) or (has_be and has_vbn)
    voice = "passive" if passive else "active"

    perfect = has_have and has_vbn
    progressive = (has_be and has_vbg) or ("being" in [t.lower_ for t in seq] and has_vbn)

    if perfect and progressive:
        aspect = "perfect_progressive"
    elif perfect:
        aspect = "perfect"
    elif progressive:
        aspect = "progressive"
    else:
        aspect = "simple"

    future = any(m in FUTURE_MODALS for m in lowered) or modal in FUTURE_MODALS
    if future:
        tense = "future"
    elif modal and has_have and has_vbn:
        # Modal perfect (e.g., "should have trusted") is not past perfect (had + VBN).
        tense = "none"
    else:
        head = finite_markers[0] if finite_markers else (seq[0] if seq else None)
        if head is None:
            tense = "none"
        elif "Past" in head.morph.get("Tense"):
            tense = "past"
        elif "Pres" in head.morph.get("Tense"):
            tense = "present"
        else:
            tense = "none"

    polarity = "negative" if has_neg else "affirmative"
    mood = "modal" if modal else "indicative"
    finiteness = "finite" if finite_markers else "non-finite"
    construction = "none"
    if modal and perfect and not future:
        construction = "modal_perfect"
    elif perfect and tense == "past" and not modal:
        construction = "past_perfect"
    elif perfect and tense == "present" and not modal:
        construction = "present_perfect"
    elif perfect and future:
        construction = "future_perfect"
    return TamResult(
        tense=tense,
        aspect=aspect,
        voice=voice,
        modal=modal,
        polarity=polarity,
        mood=mood,
        finiteness=finiteness,
        construction=construction,
    )


def apply_tam(contract_doc: dict, nlp) -> dict:
    """Apply TAM to sentence and all phrase nodes in-place."""

    def _apply_phrase_tam_recursive(node: dict) -> None:
        for child in node.get("linguistic_elements", []):
            if not isinstance(child, dict):
                continue
            if child.get("type") == "Phrase":
                phrase_text = child.get("content", "")
                phrase_doc = nlp(phrase_text)
                phrase_sent = next(phrase_doc.sents, phrase_doc[:])
                phrase_tam = detect_tam(phrase_sent)
                child["tense"] = phrase_tam.short_tense
                child["aspect"] = phrase_tam.aspect
                child["voice"] = phrase_tam.voice
                child["mood"] = phrase_tam.mood
                child["finiteness"] = phrase_tam.finiteness
                child["tam_construction"] = phrase_tam.construction
            _apply_phrase_tam_recursive(child)

    for sent_text, sentence_node in contract_doc.items():
        doc = nlp(sent_text)
        sent = next(doc.sents, doc[:])

        sentence_tam = detect_tam(sent)
        sentence_node["tense"] = sentence_tam.short_tense
        sentence_node["aspect"] = sentence_tam.aspect
        sentence_node["voice"] = sentence_tam.voice
        sentence_node["mood"] = sentence_tam.mood
        sentence_node["finiteness"] = sentence_tam.finiteness
        sentence_node["tam_construction"] = sentence_tam.construction

        _apply_phrase_tam_recursive(sentence_node)

    return contract_doc
