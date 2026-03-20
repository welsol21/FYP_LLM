"""Build contract-compliant skeleton JSON from text using spaCy."""

from __future__ import annotations

import json
from pathlib import Path
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

# Deterministic dependency-driven phrase shaping:
# build phrase spans from parser structure, not from ad-hoc token tails.
VP_DIRECT_CHILD_DEPS = {
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
VP_SUBTREE_CHILD_DEPS = {"prep", "obl", "xcomp", "ccomp", "advcl"}
_DEFAULT_CLAUSE_HEAD_DEPS = {
    "root",
    "conj",
    "advcl",
    "ccomp",
    "xcomp",
    "acl",
    "relcl",
}
_DEFAULT_PHRASAL_PREP_LEMMA_PAIRS = {
    ("look", "after"),
    ("come", "across"),
    ("run", "into"),
    ("get", "over"),
    ("put", "off"),
    ("turn", "down"),
    ("go", "on"),
    ("carry", "out"),
    ("set", "up"),
    ("take", "off"),
    ("find", "out"),
    ("make", "up"),
}

_DEFAULT_IDIOM_PATTERNS = {
    ("kick", "the", "bucket"),
    ("break", "the", "ice"),
    ("piece", "of", "cake"),
    ("under", "the", "weather"),
    ("spill", "the", "beans"),
    ("hit", "the", "sack"),
}

_DEFAULT_COLLOCATION_VERB_OBJECT_LEMMA_PAIRS = {
    ("make", "decision"),
    ("take", "risk"),
    ("pay", "attention"),
    ("raise", "baton"),
    ("reach", "conclusion"),
    ("draw", "attention"),
    ("have", "impact"),
    ("conduct", "research"),
    ("set", "goal"),
    ("meet", "requirement"),
    ("file", "complaint"),
    ("provide", "support"),
    ("cause", "problem"),
}

_PHRASE_PATTERNS_CONFIG_PATH = Path(__file__).with_name("phrase_patterns.json")


def _normalize_string_set(value: object, *, uppercase: bool = False) -> Set[str]:
    if not isinstance(value, list):
        return set()
    out: Set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        out.add(text.upper() if uppercase else text.lower())
    return out


def _normalize_tuple_set(value: object, *, width: int | None = None) -> Set[Tuple[str, ...]]:
    if not isinstance(value, list):
        return set()
    out: Set[Tuple[str, ...]] = set()
    for row in value:
        if not isinstance(row, list):
            continue
        if width is not None and len(row) != width:
            continue
        if len(row) < 2:
            continue
        parts: List[str] = []
        for item in row:
            text = str(item or "").strip().lower()
            if not text:
                parts = []
                break
            parts.append(text)
        if width is None and parts:
            out.add(tuple(parts))
        elif width is not None and len(parts) == width:
            out.add(tuple(parts))
    return out


def _load_phrase_patterns() -> Dict[str, Set]:
    config: Dict[str, object] = {}
    if _PHRASE_PATTERNS_CONFIG_PATH.is_file():
        try:
            loaded = json.loads(_PHRASE_PATTERNS_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config = loaded
        except Exception:
            config = {}

    clause_head_deps = _normalize_string_set(config.get("clause_head_deps"))
    phrasal_pairs = _normalize_tuple_set(config.get("phrasal_prep_lemma_pairs"), width=2)
    idioms = _normalize_tuple_set(config.get("idiom_patterns"))
    collocations = _normalize_tuple_set(config.get("collocation_verb_object_lemma_pairs"), width=2)

    return {
        "clause_head_deps": clause_head_deps if clause_head_deps else set(_DEFAULT_CLAUSE_HEAD_DEPS),
        "phrasal_pairs": phrasal_pairs if phrasal_pairs else set(_DEFAULT_PHRASAL_PREP_LEMMA_PAIRS),
        "idioms": idioms if idioms else set(_DEFAULT_IDIOM_PATTERNS),
        "collocations": collocations if collocations else set(_DEFAULT_COLLOCATION_VERB_OBJECT_LEMMA_PAIRS),
    }


_PHRASE_PATTERNS = _load_phrase_patterns()
CLAUSE_HEAD_DEPS = _PHRASE_PATTERNS["clause_head_deps"]
PHRASAL_PREP_LEMMA_PAIRS = _PHRASE_PATTERNS["phrasal_pairs"]
IDIOM_PATTERNS = _PHRASE_PATTERNS["idioms"]
COLLOCATION_VERB_OBJECT_LEMMA_PAIRS = _PHRASE_PATTERNS["collocations"]


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
    seen: Set[Tuple[int, int, str]] = set()

    def add_span(start: int, end: int, phrase_type: str) -> None:
        if end <= start:
            return
        item = (int(start), int(end), str(phrase_type))
        if item in seen:
            return
        seen.add(item)
        spans.append(item)

    # 1) Idioms (contiguous lemma/text pattern match)
    token_window = [tok for tok in sent if not tok.is_space and not tok.is_punct]
    for size in sorted({len(p) for p in IDIOM_PATTERNS}, reverse=True):
        if size <= 0 or len(token_window) < size:
            continue
        for i in range(0, len(token_window) - size + 1):
            chunk = token_window[i : i + size]
            if chunk[-1].i + 1 - chunk[0].i != size:
                continue
            lemmas = tuple(tok.lemma_.lower() for tok in chunk)
            lowers = tuple(tok.lower_ for tok in chunk)
            if lemmas in IDIOM_PATTERNS or lowers in IDIOM_PATTERNS:
                add_span(chunk[0].i, chunk[-1].i + 1, "idiom")

    # 2) Phrasal verbs
    for token in sent:
        if token.pos_ not in {"VERB", "AUX"}:
            continue
        particles = [child for child in token.children if child.dep_ == "prt"]
        if particles:
            token_ids = {token.i, *(child.i for child in particles)}
            add_span(min(token_ids), max(token_ids) + 1, "phrasal verb")
        for child in token.children:
            if child.dep_ != "prep":
                continue
            pair = (token.lemma_.lower(), child.lemma_.lower())
            if pair in PHRASAL_PREP_LEMMA_PAIRS:
                add_span(min(token.i, child.i), max(token.i, child.i) + 1, "phrasal verb")

    # 3) Verb-object collocations
    for token in sent:
        if token.pos_ not in {"VERB", "AUX"}:
            continue
        for child in token.children:
            if child.dep_ not in {"dobj", "obj", "attr", "oprd", "pobj"}:
                continue
            pair = (token.lemma_.lower(), child.lemma_.lower())
            if pair in COLLOCATION_VERB_OBJECT_LEMMA_PAIRS:
                add_span(min(token.i, child.left_edge.i), max(token.i, child.right_edge.i) + 1, "collocation")

    # 4) Noun phrases around nominal heads.
    for token in sent:
        if token.pos_ not in {"NOUN", "PROPN", "PRON"}:
            continue
        add_span(token.left_edge.i, token.right_edge.i + 1, "noun phrase")

    # 5) Prepositional phrases
    for token in sent:
        if token.pos_ == "ADP":
            add_span(token.i, token.right_edge.i + 1, "prepositional phrase")

    spans.sort(key=lambda s: (s[0], s[1]))
    return spans


def _is_weak_phrase_candidate(span, phrase_pos: str) -> bool:
    tokens = [tok for tok in span if not tok.is_space and not tok.is_punct]
    if len(tokens) < 2:
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
    if phrase_pos in {"verb phrase", "phrasal verb", "idiom", "collocation"}:
        return "predicate"
    if phrase_pos == "clause chunk":
        return "clause"
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


def _is_sentence_content_duplicate_span(sent, start: int, end: int, doc) -> bool:
    """True when a phrase span covers all non-space/non-punct sentence tokens."""
    sent_token_ids = [tok.i for tok in sent if not tok.is_space and not tok.is_punct]
    if not sent_token_ids:
        return False
    span_token_ids = [tok.i for tok in doc[start:end] if not tok.is_space and not tok.is_punct]
    return span_token_ids == sent_token_ids


def _is_clause_like_sentence(sent) -> bool:
    has_subject = False
    has_finite_predicate = False
    for token in sent:
        if token.is_space or token.is_punct:
            continue
        dep = token.dep_.lower()
        if dep in {"nsubj", "nsubjpass", "csubj", "csubjpass", "expl"}:
            has_subject = True
        if token.pos_ in {"VERB", "AUX"} and "Fin" in token.morph.get("VerbForm"):
            has_finite_predicate = True
        if dep == "root" and token.pos_ in {"VERB", "AUX"} and "Fin" in token.morph.get("VerbForm"):
            return True
    return has_subject and has_finite_predicate


def _build_word_nodes(span, *, parent_id: str, next_id) -> List[Dict]:
    words: List[Dict] = []
    entries: List[Tuple[object, Dict]] = []
    for token in span:
        if token.is_space or token.is_punct:
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
            # Do not create a phrase node that duplicates the whole sentence content.
            if _is_sentence_content_duplicate_span(sent, start, end, doc):
                continue
            if _is_weak_phrase_candidate(span, phrase_pos):
                continue
            if _is_simple_determiner_np(span, phrase_pos):
                continue
            phrase_spans.append((start, end, phrase_pos))

        if _is_clause_like_sentence(sent):
            covered_token_ids: set[int] = set()
            for start, end, _ in phrase_spans:
                covered_token_ids.update(
                    token.i
                    for token in doc[start:end]
                    if not token.is_space and not token.is_punct
                )
            sentence_token_ids = {
                token.i
                for token in sent
                if not token.is_space and not token.is_punct
            }
            if not phrase_spans or covered_token_ids != sentence_token_ids:
                phrase_spans.append((sent.start, sent.end, "clause chunk"))

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

        # Always keep sentence words not covered by phrase spans.
        covered_token_ids: set[int] = set()
        for idx in top_level_indices:
            start, end, _ = phrase_spans[idx]
            covered_token_ids.update(range(start, end))

        uncovered_sentence_tokens = [
            token
            for token in sent
            if not token.is_space and not token.is_punct and token.i not in covered_token_ids
        ]
        uncovered_word_nodes = _build_word_nodes(
            uncovered_sentence_tokens,
            parent_id=sentence_id,
            next_id=next_id,
        )
        sentence_node["linguistic_elements"] = _sort_children_by_span(
            sentence_node["linguistic_elements"] + uncovered_word_nodes
        )

        if not sentence_node["linguistic_elements"]:
            # Ultimate fallback: attach all sentence tokens.
            sentence_node["linguistic_elements"] = _build_word_nodes(
                sent,
                parent_id=sentence_id,
                next_id=next_id,
            )

        _mark_ref_duplicates(sentence_node)
        output[sent_text] = sentence_node

    return output
