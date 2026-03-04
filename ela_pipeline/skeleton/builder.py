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
    if token.tag_ == "MD":
        return "modal"
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
                if c.dep_
                in {
                    "aux",
                    "auxpass",
                    "neg",
                    "prt",
                    "dobj",
                    "obj",
                    "iobj",
                    "attr",
                    "acomp",
                    "xcomp",
                    "advmod",
                    "prep",
                    "pobj",
                    "obl",
                    "npadvmod",
                }
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


def _is_weak_phrase_candidate(span, phrase_pos: str) -> bool:
    tokens = [tok for tok in span if not tok.is_space and not tok.is_punct]
    if len(tokens) < 2:
        return True
    if phrase_pos == "prepositional phrase" and len(tokens) < 3:
        return True
    return False


def _phrase_parent_map(spans: List[Tuple[int, int, str]]) -> Dict[int, int | None]:
    parent_by_idx: Dict[int, int | None] = {}
    for idx, (start, end, _) in enumerate(spans):
        best_parent: int | None = None
        best_width: int | None = None
        for candidate_idx, (p_start, p_end, _) in enumerate(spans):
            if candidate_idx == idx:
                continue
            if p_start <= start and end <= p_end and (p_start, p_end) != (start, end):
                width = p_end - p_start
                if best_parent is None or (best_width is not None and width < best_width):
                    best_parent = candidate_idx
                    best_width = width
        parent_by_idx[idx] = best_parent
    return parent_by_idx


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


def _sort_children_by_span(items: List[Dict]) -> List[Dict]:
    return sorted(
        items,
        key=lambda item: (
            int((item.get("source_span") or {}).get("start", 0)),
            int((item.get("source_span") or {}).get("end", 0)),
            0 if item.get("type") == "Word" else 1,
        ),
    )


def _build_phrase_node(
    *,
    idx: int,
    spans: List[Tuple[int, int, str]],
    children_by_idx: Dict[int, List[int]],
    doc,
    sentence_id: str,
    next_id,
) -> Dict:
    start, end, phrase_pos = spans[idx]
    span = doc[start:end]
    phrase_text = span.text.strip()
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

    child_phrase_nodes = [
        _build_phrase_node(
            idx=child_idx,
            spans=spans,
            children_by_idx=children_by_idx,
            doc=doc,
            sentence_id=phrase_id,
            next_id=next_id,
        )
        for child_idx in sorted(children_by_idx.get(idx, []), key=lambda i: (spans[i][0], spans[i][1]))
    ]

    covered_token_ids: set[int] = set()
    for child_idx in children_by_idx.get(idx, []):
        child_start, child_end, _ = spans[child_idx]
        covered_token_ids.update(range(child_start, child_end))

    direct_tokens = [token for token in span if not token.is_space and token.i not in covered_token_ids]
    word_nodes = _build_word_nodes(direct_tokens, parent_id=phrase_id, next_id=next_id)
    phrase_node["linguistic_elements"] = _sort_children_by_span(child_phrase_nodes + word_nodes)
    return phrase_node


def _mark_ref_duplicates(sentence_node: Dict) -> None:
    """Mark duplicate span/content nodes with ref_node_id without changing tree shape."""
    seen: Dict[Tuple[str, int, int, str, str], str] = {}

    def walk(node: Dict) -> None:
        for child in node.get("linguistic_elements", []):
            if not isinstance(child, dict):
                continue
            node_type = str(child.get("type") or "")
            if node_type in {"Phrase", "Word"}:
                span = child.get("source_span") or {}
                key = (
                    node_type,
                    int(span.get("start", -1)),
                    int(span.get("end", -1)),
                    str(child.get("content") or ""),
                    str(child.get("part_of_speech") or ""),
                )
                first_id = seen.get(key)
                if first_id is None:
                    seen[key] = child.get("node_id")
                    child.pop("ref_node_id", None)
                else:
                    child["ref_node_id"] = first_id
            walk(child)

    walk(sentence_node)


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

        phrase_spans: List[Tuple[int, int, str]] = []
        for start, end, phrase_pos in _phrase_candidates(sent):
            span = doc[start:end]
            phrase_text = span.text.strip()
            if not phrase_text:
                continue
            if _is_weak_phrase_candidate(span, phrase_pos):
                continue
            if _is_simple_determiner_np(span, phrase_pos):
                continue
            phrase_spans.append((start, end, phrase_pos))

        parent_by_idx = _phrase_parent_map(phrase_spans)
        children_by_idx: Dict[int, List[int]] = {}
        top_level_indices: List[int] = []
        for idx, parent_idx in parent_by_idx.items():
            if parent_idx is None:
                top_level_indices.append(idx)
                continue
            children_by_idx.setdefault(parent_idx, []).append(idx)

        for idx in sorted(top_level_indices, key=lambda i: (phrase_spans[i][0], phrase_spans[i][1])):
            phrase_node = _build_phrase_node(
                idx=idx,
                spans=phrase_spans,
                children_by_idx=children_by_idx,
                doc=doc,
                sentence_id=sentence_id,
                next_id=next_id,
            )
            sentence_node["linguistic_elements"].append(phrase_node)

        if not sentence_node["linguistic_elements"]:
            # Fallback: attach words directly to sentence.
            sentence_node["linguistic_elements"] = _build_word_nodes(
                sent,
                parent_id=sentence_id,
                next_id=next_id,
            )

        _mark_ref_duplicates(sentence_node)
        output[sent_text] = sentence_node

    return output
