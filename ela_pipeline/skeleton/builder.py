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


PHRASE_DEP_ROLE_MAP = {
    "nsubj": "subject",
    "nsubjpass": "subject",
    "csubj": "subject",
    "csubjpass": "subject",
    "obj": "object",
    "dobj": "object",
    "iobj": "object",
    "pobj": "object",
    "attr": "complement",
    "acomp": "complement",
    "oprd": "complement",
    "appos": "modifier",
    "amod": "modifier",
    "nmod": "modifier",
    "advmod": "adjunct",
    "advcl": "adjunct",
    "obl": "adjunct",
}

WORD_DEP_ROLE_MAP = {
    "ROOT": "predicate",
    "nsubj": "subject",
    "nsubjpass": "subject",
    "csubj": "subject",
    "csubjpass": "subject",
    "obj": "object",
    "dobj": "object",
    "iobj": "object",
    "pobj": "object",
    "attr": "complement",
    "acomp": "complement",
    "oprd": "complement",
    "amod": "modifier",
    "nmod": "modifier",
    "advmod": "adjunct",
    "advcl": "adjunct",
    "det": "determiner",
    "aux": "auxiliary",
    "auxpass": "auxiliary",
    "prep": "linker",
    "cc": "coordinator",
    "conj": "conjunct",
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


def _word_aspect(token) -> str:
    if token.pos_ not in {"VERB", "AUX"}:
        return "null"
    if token.tag_ == "VBG":
        return "progressive"
    if token.tag_ == "VBN":
        return "perfect"
    return "simple"


def _word_mood(token) -> str:
    if token.pos_ not in {"VERB", "AUX"}:
        return "null"
    mood = token.morph.get("Mood")
    if mood:
        return mood[0].lower()
    return "indicative" if "Fin" in token.morph.get("VerbForm") else "null"


def _word_voice(token) -> str:
    if token.pos_ not in {"VERB", "AUX"}:
        return "null"
    if token.dep_ == "auxpass":
        return "passive"
    return "active"


def _word_finiteness(token) -> str:
    if token.pos_ not in {"VERB", "AUX"}:
        return "null"
    return "finite" if "Fin" in token.morph.get("VerbForm") else "non-finite"


def _word_aux_function(token) -> str:
    if token.pos_ != "AUX":
        return "null"
    if token.tag_ == "MD":
        return "modal_auxiliary"
    if token.lemma_.lower() == "have":
        return "perfect_auxiliary"
    if token.dep_ == "auxpass":
        return "passive_auxiliary"
    if token.lemma_.lower() == "be" and token.head.tag_ == "VBG":
        return "progressive_auxiliary"
    return "auxiliary"


def _word_features(token) -> Dict[str, str]:
    feature_map = {
        "number": token.morph.get("Number"),
        "person": token.morph.get("Person"),
        "case": token.morph.get("Case"),
        "degree": token.morph.get("Degree"),
        "definiteness": token.morph.get("Definite"),
        "verb_form": token.morph.get("VerbForm"),
        "gender": token.morph.get("Gender"),
        "tense_feature": token.morph.get("Tense"),
    }
    return {k: (v[0].lower() if v else "null") for k, v in feature_map.items()}


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


def _with_metadata(node: Dict, *, node_id: str, parent_id: str | None, start: int, end: int) -> Dict:
    node["node_id"] = node_id
    node["parent_id"] = parent_id
    node["source_span"] = {"start": int(start), "end": int(end)}
    return node


def _word_role(token) -> str:
    return WORD_DEP_ROLE_MAP.get(token.dep_, "other")


def _span_head_token(span):
    span_token_ids = {t.i for t in span}
    for token in span:
        if token.i in span_token_ids and token.head.i not in span_token_ids:
            return token
    for token in span:
        if token.dep_ == "ROOT":
            return token
    for token in span:
        if not token.is_space:
            return token
    return None


def _phrase_role(span, phrase_pos: str) -> str:
    if phrase_pos == "verb phrase":
        return "predicate"
    head = _span_head_token(span)
    if head is None:
        return "other"
    return PHRASE_DEP_ROLE_MAP.get(head.dep_, "modifier")


def _is_simple_determiner_np(span, phrase_pos: str) -> bool:
    if phrase_pos != "noun phrase":
        return False

    tokens = [t for t in span if not t.is_space]
    if len(tokens) < 2:
        return False
    if tokens[0].pos_ != "DET":
        return False

    allowed_pos = {"DET", "ADJ", "NUM", "NOUN", "PROPN"}
    return all(tok.pos_ in allowed_pos for tok in tokens)


def _build_word_nodes(span, *, parent_id: str, next_id) -> List[Dict]:
    words: List[Dict] = []
    entries: List[Tuple[object, Dict]] = []
    for token in span:
        if token.is_space:
            continue
        word_node = blank_node(
            "Word",
            token.text,
            WORD_POS_MAP.get(token.pos_, "other"),
            tense=_word_tense(token),
        )
        word_node["aspect"] = _word_aspect(token)
        word_node["mood"] = _word_mood(token)
        word_node["voice"] = _word_voice(token)
        word_node["finiteness"] = _word_finiteness(token)
        word_node["aux_function"] = _word_aux_function(token)
        word_node["features"] = _word_features(token)
        _with_metadata(
            word_node,
            node_id=next_id(),
            parent_id=parent_id,
            start=token.idx,
            end=token.idx + len(token.text),
        )
        word_node["grammatical_role"] = _word_role(token)
        word_node["dep_label"] = token.dep_
        word_node["head_id"] = None
        words.append(word_node)
        entries.append((token, word_node))

    token_to_id = {token.i: node["node_id"] for token, node in entries}
    for token, node in entries:
        if token.head.i in token_to_id and token.head.i != token.i:
            node["head_id"] = token_to_id[token.head.i]

    return words


def build_skeleton(text: str, nlp) -> Dict[str, Dict]:
    doc = nlp(text)
    output: Dict[str, Dict] = {}
    seq = 0

    def next_id() -> str:
        nonlocal seq
        seq += 1
        return f"n{seq}"

    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not sent_text:
            continue

        sentence_node = blank_node("Sentence", sent_text, "sentence", tense="null")
        sentence_id = next_id()
        _with_metadata(
            sentence_node,
            node_id=sentence_id,
            parent_id=None,
            start=sent.start_char,
            end=sent.end_char,
        )
        sentence_node["grammatical_role"] = "clause"

        for start, end, phrase_pos in _phrase_candidates(sent):
            span = doc[start:end]
            phrase_text = span.text.strip()
            if not phrase_text:
                continue
            if _is_simple_determiner_np(span, phrase_pos):
                continue

            phrase_node = blank_node("Phrase", phrase_text, phrase_pos, tense="null")
            phrase_id = next_id()
            _with_metadata(
                phrase_node,
                node_id=phrase_id,
                parent_id=sentence_id,
                start=span.start_char,
                end=span.end_char,
            )
            phrase_node["grammatical_role"] = _phrase_role(span, phrase_pos)
            phrase_node["linguistic_elements"] = _build_word_nodes(
                span,
                parent_id=phrase_id,
                next_id=next_id,
            )

            # Contract rule: do not emit one-word phrases.
            if len(phrase_node["linguistic_elements"]) < 2:
                continue

            sentence_node["linguistic_elements"].append(phrase_node)

        if not sentence_node["linguistic_elements"]:
            # Fallback: single phrase with all non-space tokens when sentence has at least 2 tokens.
            phrase_node = blank_node("Phrase", sent_text, "clause", tense="null")
            phrase_id = next_id()
            _with_metadata(
                phrase_node,
                node_id=phrase_id,
                parent_id=sentence_id,
                start=sent.start_char,
                end=sent.end_char,
            )
            phrase_node["grammatical_role"] = "predicate"
            phrase_node["linguistic_elements"] = _build_word_nodes(
                sent,
                parent_id=phrase_id,
                next_id=next_id,
            )
            if len(phrase_node["linguistic_elements"]) >= 2:
                sentence_node["linguistic_elements"].append(phrase_node)

        output[sent_text] = sentence_node

    return output
