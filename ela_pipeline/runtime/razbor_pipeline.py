"""Intermediate CEFR razbor pipeline and mapping to frontend contract."""

from __future__ import annotations

from functools import lru_cache
import json
import os
import re
from pathlib import Path
from typing import Any

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.validation.validator import raise_if_invalid, validate_contract, validate_razbor_contract


_SUBJECT_DEPS = {"nsubj", "nsubjpass", "csubj", "csubjpass", "expl"}
_OBJECT_DEPS = {"dobj", "obj", "iobj", "pobj"}
_MODAL_HINTS = {"can", "could", "may", "might", "must", "shall", "should", "will", "would"}
_HIGH_REGISTER_WORDS = {
    "cacophony",
    "jarring",
    "defied",
    "notwithstanding",
    "whereas",
    "thereby",
    "consequently",
    "albeit",
}
_CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]
_WORD_POS_MAP = {
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
_GRAMMAR_ROLE_MAP = {
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
    "mark": "subordinator",
}


def _normalize_spaces(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _empty_notes() -> dict[str, str]:
    return {
        "elementary": "",
        "intermediate": "",
        "advanced": "",
    }


def _extract_clauses(sent: Any) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    candidate_tokens: list[Any] = []
    for token in sent:
        if token.pos_ not in {"VERB", "AUX"}:
            continue
        is_finite = "Fin" in token.morph.get("VerbForm") or token.tag_ == "MD"
        if not is_finite:
            continue
        if token.dep_ in {"ROOT", "conj", "advcl", "ccomp", "xcomp", "relcl", "acl", "csubj", "csubjpass", "parataxis"}:
            candidate_tokens.append(token)

    if not candidate_tokens:
        root = next((tok for tok in sent if tok.dep_ == "ROOT"), None)
        if root is not None:
            candidate_tokens.append(root)

    seen_spans: set[tuple[int, int]] = set()
    relation_map = {
        "ROOT": "main predication",
        "conj": "coordination",
        "advcl": "adverbial subordination",
        "ccomp": "complement clause",
        "xcomp": "open complement",
        "relcl": "relative clause",
        "acl": "adnominal clause",
        "csubj": "clausal subject",
        "csubjpass": "clausal subject",
        "parataxis": "parataxis",
    }
    for token in candidate_tokens:
        span_tokens = [t for t in token.subtree]
        if not span_tokens:
            continue
        start_char = min(t.idx for t in span_tokens)
        end_char = max(t.idx + len(t.text) for t in span_tokens)
        key = (start_char, end_char)
        if key in seen_spans:
            continue
        seen_spans.add(key)
        span_text = _normalize_spaces(str(token.doc.text[start_char:end_char]))
        marker = next((child.text for child in token.children if child.dep_ == "mark"), None)
        role = "main" if token.dep_ in {"ROOT", "conj", "parataxis"} else "subordinate"
        clauses.append(
            {
                "root": token,
                "role": role,
                "marker": marker,
                "relation": relation_map.get(token.dep_, "clause dependency"),
                "span": span_text,
                "start": start_char,
                "end": end_char,
            }
        )

    if not clauses:
        text = _normalize_spaces(sent.text)
        clauses.append(
            {
                "root": None,
                "role": "main",
                "marker": None,
                "relation": "main predication",
                "span": text,
                "start": int(sent.start_char),
                "end": int(sent.end_char),
            }
        )

    clauses.sort(key=lambda row: (int(row["start"]), int(row["end"])))
    return clauses


def _detect_communicative_type(sentence_text: str, sent: Any) -> str:
    text = str(sentence_text or "").strip()
    if text.endswith("?"):
        return "Interrogative"
    if text.endswith("!"):
        return "Exclamative"
    first = next((tok for tok in sent if not tok.is_space and not tok.is_punct), None)
    has_explicit_subject = any(tok.dep_ in _SUBJECT_DEPS for tok in sent)
    if first is not None and first.pos_ in {"VERB", "AUX"} and not has_explicit_subject:
        return "Imperative"
    return "Declarative"


def _detect_sentence_type(sent: Any, clauses: list[dict[str, Any]]) -> str:
    clause_count = len(clauses)
    has_subordinate = any(row.get("role") == "subordinate" for row in clauses)
    has_coord = any(tok.dep_ == "cc" for tok in sent) or any(row.get("relation") == "coordination" for row in clauses)
    if clause_count <= 1:
        return "Simple"
    if has_subordinate and has_coord:
        return "Compound-Complex"
    if has_subordinate:
        return "Complex"
    if has_coord:
        return "Compound"
    return "Complex"


def _subject_span(sent: Any) -> str | None:
    subjects = [tok for tok in sent if tok.dep_ in _SUBJECT_DEPS]
    if not subjects:
        return None
    start = min(tok.idx for tok in subjects)
    end = max(tok.idx + len(tok.text) for tok in subjects)
    return _normalize_spaces(str(sent.doc.text[start:end]))


def _predicate_span(sent: Any) -> str | None:
    root = next((tok for tok in sent if tok.dep_ == "ROOT" and tok.pos_ in {"VERB", "AUX"}), None)
    if root is None:
        return None
    predicate_tokens = [root]
    predicate_tokens.extend(child for child in root.children if child.dep_ in {"aux", "auxpass", "neg", "prt"})
    start = min(tok.idx for tok in predicate_tokens)
    end = max(tok.idx + len(tok.text) for tok in predicate_tokens)
    return _normalize_spaces(str(sent.doc.text[start:end]))


def _post_predicate_span(sentence_text: str, predicate_span: str | None) -> str | None:
    text = str(sentence_text or "")
    if not predicate_span:
        return _normalize_spaces(text)
    pos = text.lower().find(predicate_span.lower())
    if pos < 0:
        return _normalize_spaces(text)
    tail = text[pos + len(predicate_span) :]
    return _normalize_spaces(tail) if tail.strip() else None


def _constituent_function_from_dep(dep: str) -> str:
    if dep in _SUBJECT_DEPS:
        return "Subject"
    if dep in _OBJECT_DEPS:
        return "Object"
    if dep in {"attr", "acomp", "oprd"}:
        return "Complement"
    if dep in {"advmod", "advcl", "obl", "npadvmod"}:
        return "Adjunct"
    return "Modifier"


def _build_constituents(sent: Any, clauses: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[tuple[int, int, dict[str, str]]] = []
    seen: set[tuple[str, str, str]] = set()

    for chunk in getattr(sent, "noun_chunks", []):
        span_text = _normalize_spaces(chunk.text)
        if not span_text:
            continue
        item = {
            "phrase_type": "NP",
            "function": _constituent_function_from_dep(chunk.root.dep_),
            "span": span_text,
        }
        key = (item["phrase_type"], item["function"], item["span"])
        if key in seen:
            continue
        seen.add(key)
        rows.append((int(chunk.start_char), int(chunk.end_char), item))

    for clause in clauses:
        span_text = _normalize_spaces(str(clause.get("span") or ""))
        if not span_text:
            continue
        function = "Predicate"
        if clause.get("role") == "subordinate":
            function = "Subordinate predicate"
        item = {
            "phrase_type": "VP",
            "function": function,
            "span": span_text,
        }
        key = (item["phrase_type"], item["function"], item["span"])
        if key in seen:
            continue
        seen.add(key)
        rows.append((int(clause["start"]), int(clause["end"]), item))

    for token in sent:
        if token.pos_ == "SCONJ":
            item = {
                "phrase_type": "SCONJ",
                "function": "Subordinator",
                "span": token.text,
            }
            key = (item["phrase_type"], item["function"], item["span"])
            if key in seen:
                continue
            seen.add(key)
            rows.append((int(token.idx), int(token.idx + len(token.text)), item))
        if token.pos_ == "ADP" and token.dep_ == "prep":
            subtree = [tok for tok in token.subtree]
            start_char = min(tok.idx for tok in subtree)
            end_char = max(tok.idx + len(tok.text) for tok in subtree)
            span_text = _normalize_spaces(str(sent.doc.text[start_char:end_char]))
            item = {
                "phrase_type": "PP",
                "function": "Adjunct",
                "span": span_text,
            }
            key = (item["phrase_type"], item["function"], item["span"])
            if key in seen:
                continue
            seen.add(key)
            rows.append((start_char, end_char, item))

    rows.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in rows]


def _token_features(token: Any) -> dict[str, Any]:
    morph_map = token.morph.to_dict() if hasattr(token, "morph") else {}
    features: dict[str, Any] = {}
    for key, value in morph_map.items():
        if value is None:
            continue
        features[str(key)] = str(value)
    return features


def _clause_aspect(root: Any, aux_tokens: list[Any]) -> str:
    if root is None:
        return "Simple"
    tags = {tok.tag_ for tok in [root, *aux_tokens]}
    lemmas = {tok.lemma_.lower() for tok in [root, *aux_tokens]}
    if "have" in lemmas and ("VBG" in tags or root.tag_ == "VBG"):
        return "Perfect Progressive"
    if "have" in lemmas and ("VBN" in tags or root.tag_ == "VBN"):
        return "Perfect"
    if "VBG" in tags or root.tag_ == "VBG":
        return "Progressive"
    return "Simple"


def _clause_tense(root: Any, aux_tokens: list[Any]) -> str:
    if root is None:
        return "Present"
    tokens = [root, *aux_tokens]
    lemmas = {tok.lemma_.lower() for tok in tokens}
    tags = {tok.tag_ for tok in tokens}
    if "will" in lemmas or "shall" in lemmas:
        return "Future"
    if "VBD" in tags:
        return "Past"
    if any("Past" in tok.morph.get("Tense") for tok in tokens):
        return "Past"
    return "Present"


def _clause_voice(root: Any, aux_tokens: list[Any], clause_tokens: list[Any]) -> str:
    if root is None:
        return "Active"
    if any(tok.dep_ == "auxpass" for tok in aux_tokens):
        return "Passive"
    has_passive_subject = any(tok.dep_ in {"nsubjpass", "csubjpass"} for tok in clause_tokens)
    if has_passive_subject and root.tag_ in {"VBN", "VBD"}:
        return "Passive"
    return "Active"


def _clause_mood(root: Any, aux_tokens: list[Any], communicative_type: str) -> str:
    tokens = [root, *aux_tokens] if root is not None else aux_tokens
    if any(tok.tag_ == "MD" for tok in tokens):
        return "Modal"
    if communicative_type == "Imperative":
        return "Imperative"
    return "Indicative"


def _clause_modality(aux_tokens: list[Any]) -> str | None:
    hints = [tok.lemma_.lower() for tok in aux_tokens if tok.tag_ == "MD" or tok.lemma_.lower() in _MODAL_HINTS]
    if not hints:
        return None
    return ", ".join(dict.fromkeys(hints))


def _clause_time_reference(tense: str, aspect: str) -> str:
    if tense == "Future":
        return "Future"
    if tense == "Past":
        return "Past"
    if aspect in {"Perfect", "Perfect Progressive"}:
        return "Present with retrospective focus"
    return "Present/General"


def _build_verb_system(sent: Any, clauses: list[dict[str, Any]], communicative_type: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for clause in clauses:
        root = clause.get("root")
        if root is not None:
            clause_tokens = [tok for tok in root.subtree]
            aux_tokens = [tok for tok in clause_tokens if tok.dep_ in {"aux", "auxpass"} or tok.tag_ == "MD"]
        else:
            clause_tokens = [tok for tok in sent]
            aux_tokens = [tok for tok in clause_tokens if tok.dep_ in {"aux", "auxpass"} or tok.tag_ == "MD"]

        tense = _clause_tense(root, aux_tokens)
        aspect = _clause_aspect(root, aux_tokens)
        voice = _clause_voice(root, aux_tokens, clause_tokens)
        mood = _clause_mood(root, aux_tokens, communicative_type)
        modality = _clause_modality(aux_tokens)
        time_reference = _clause_time_reference(tense, aspect)

        evidence: list[str] = []
        if root is not None:
            evidence.append(f"finite predicate: '{root.text}'")
        if aux_tokens:
            aux_text = " ".join(tok.text for tok in aux_tokens)
            evidence.append(f"auxiliaries/modals: {aux_text}")
        if clause.get("marker"):
            evidence.append(f"subordinator marker: {clause['marker']}")
        if voice == "Passive":
            evidence.append("passive alignment: passive subject + participle/auxiliary")
        if not evidence:
            evidence.append("single finite clause")

        out.append(
            {
                "clause_span": str(clause.get("span") or ""),
                "tense": tense,
                "aspect": aspect,
                "voice": voice,
                "mood": mood,
                "modality": modality,
                "time_reference": time_reference,
                "evidence": evidence,
            }
        )

    return out


def _build_lexis(sent: Any) -> dict[str, Any]:
    collocations: list[dict[str, Any]] = []
    for token in sent:
        if token.pos_ not in {"VERB", "AUX"}:
            continue
        for child in token.children:
            if child.dep_ in _OBJECT_DEPS:
                pair = [token.lemma_.lower(), child.lemma_.lower()]
                collocations.append({"pair": pair, "label": "verb-object collocation"})

    seen_pairs: set[tuple[str, str]] = set()
    unique_collocations: list[dict[str, Any]] = []
    for row in collocations:
        pair = row.get("pair") or []
        if len(pair) != 2:
            continue
        key = (str(pair[0]), str(pair[1]))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        unique_collocations.append(row)

    tokens = [tok for tok in sent if tok.is_alpha]
    long_words = [tok for tok in tokens if len(tok.text) >= 8]
    high_register_hits = [tok.text for tok in tokens if tok.lemma_.lower() in _HIGH_REGISTER_WORDS]

    if high_register_hits or len(long_words) >= 3:
        register = "literary / high-register narrative"
    elif any(tok.lemma_.lower() in {"however", "therefore", "whereas", "although"} for tok in tokens):
        register = "formal / academic"
    else:
        register = "neutral"

    precision_signals: list[str] = []
    if any(tok.pos_ == "PROPN" for tok in sent):
        precision_signals.append("Proper-noun anchoring")
    if long_words:
        precision_signals.append("Lexical specificity via low-frequency longer words")
    if high_register_hits:
        precision_signals.append(f"High-register lexemes: {', '.join(high_register_hits[:4])}")

    return {
        "register": register,
        "collocations": unique_collocations,
        "semantic_precision": {
            "issues": [],
            "high_precision_signals": precision_signals,
        },
    }


def _infer_cefr_level(*, sent: Any, architecture: dict[str, Any], verb_system: list[dict[str, Any]], lexis: dict[str, Any]) -> tuple[str, list[str]]:
    score = 1
    markers: list[str] = []

    sentence_type = str(architecture.get("sentence_type") or "")
    if sentence_type in {"Compound", "Complex", "Compound-Complex"}:
        score += 1
        markers.append("multi-clause architecture")
    if sentence_type in {"Complex", "Compound-Complex"}:
        score += 1
        markers.append("subordination")

    if any(str(row.get("aspect")) in {"Perfect", "Perfect Progressive", "Progressive"} for row in verb_system):
        score += 1
        markers.append("aspectual control")
    if any(str(row.get("voice")) == "Passive" for row in verb_system):
        score += 1
        markers.append("passive voice")
    if any(str(row.get("modality") or "").strip() for row in verb_system):
        score += 1
        markers.append("modal system")

    token_count = len([tok for tok in sent if not tok.is_space and not tok.is_punct])
    if token_count >= 18:
        score += 1
        markers.append("high information density")
    if token_count >= 26:
        score += 1

    register = str(lexis.get("register") or "")
    if "high-register" in register or "formal" in register:
        score += 1
        markers.append("register sophistication")

    text = str(sent.text or "")
    lowered = text.casefold()
    if any(pattern in lowered for pattern in ("hardly had", "not only", "rarely ", "seldom ", "no sooner")):
        score += 1
        markers.append("marked inversion")

    if score <= 1:
        level = "A1"
    elif score == 2:
        level = "A2"
    elif score == 3:
        level = "B1"
    elif score == 4:
        level = "B2"
    elif score == 5:
        level = "C1"
    else:
        level = "C2"

    unique_markers = list(dict.fromkeys(markers))
    if not unique_markers:
        unique_markers = ["baseline finite clause control"]
    return level, unique_markers


def _build_razbor_item(sentence_text: str, sentence_idx: int, nlp: Any) -> dict[str, Any]:
    sent_doc = nlp(sentence_text)
    sent = next(iter(sent_doc.sents), sent_doc[:])

    clauses = _extract_clauses(sent)
    communicative_type = _detect_communicative_type(sentence_text, sent)
    architecture = {
        "sentence_type": _detect_sentence_type(sent, clauses),
        "communicative_type": communicative_type,
        "clauses": [
            {
                "role": str(row.get("role") or "main"),
                "marker": row.get("marker"),
                "relation": row.get("relation"),
                "span": str(row.get("span") or ""),
            }
            for row in clauses
        ],
    }

    predicate_span = _predicate_span(sent)
    constituents_heuristic = {
        "subject_span": _subject_span(sent),
        "predicate_span": predicate_span,
        "post_predicate_span": _post_predicate_span(sentence_text, predicate_span),
    }

    constituents = _build_constituents(sent, clauses)

    morphology_tokens = []
    for token in sent:
        text = str(token.text or "")
        if not text:
            continue
        morphology_tokens.append(
            {
                "text": text,
                "pos": str(token.pos_ or "WORD"),
                "lemma": str(token.lemma_ or text).lower(),
                "features": _token_features(token),
            }
        )

    verb_system = _build_verb_system(sent, clauses, communicative_type)
    lexis = _build_lexis(sent)
    cefr_level, cefr_markers = _infer_cefr_level(sent=sent, architecture=architecture, verb_system=verb_system, lexis=lexis)

    meaning_pragmatics = {
        "speech_act": communicative_type.lower(),
        "time_reference": str(verb_system[0].get("time_reference") if verb_system else "Present/General"),
        "pragmatic_notes": [
            f"{communicative_type} packaging with {architecture['sentence_type'].lower()} structure.",
        ],
    }

    return {
        "id": f"auto_{cefr_level.lower()}_{sentence_idx + 1:03d}",
        "input": sentence_text,
        "analysis": {
            "architecture": architecture,
            "constituents_heuristic": constituents_heuristic,
            "constituents": constituents,
            "morphology": {"tokens": morphology_tokens},
            "verb_system": {"per_clause": verb_system},
            "meaning_pragmatics": meaning_pragmatics,
            "lexis": lexis,
            "cefr": {
                "level": cefr_level,
                "markers": cefr_markers,
            },
        },
        "notes": _empty_notes(),
    }


def _strip_code_fences(text: str) -> str:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value).strip()
        if value.endswith("```"):
            value = value[:-3].strip()
    return value


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        return None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = cleaned[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_notes_object(payload: dict[str, Any] | None) -> dict[str, str]:
    base = _empty_notes()
    if not isinstance(payload, dict):
        return base
    for key in ("elementary", "intermediate", "advanced"):
        value = payload.get(key)
        if value is None:
            continue
        base[key] = str(value).strip()
    return base


@lru_cache(maxsize=1)
def _load_example_bank(path: str) -> dict[str, list[dict[str, Any]]]:
    data_path = Path(path)
    if not data_path.exists():
        return {}
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    examples = data.get("examples") if isinstance(data, dict) else []
    if not isinstance(examples, list):
        return {}

    bank: dict[str, list[dict[str, Any]]] = {}
    for row in examples:
        if not isinstance(row, dict):
            continue
        analysis = row.get("analysis") if isinstance(row.get("analysis"), dict) else {}
        cefr = analysis.get("cefr") if isinstance(analysis.get("cefr"), dict) else {}
        level = str(row.get("cefr_level") or cefr.get("level") or "").strip().upper()
        if level not in _CEFR_ORDER:
            continue
        bank.setdefault(level, []).append(row)
    return bank


def _fallback_notes_for_item(item: dict[str, Any]) -> dict[str, str]:
    analysis = item.get("analysis") if isinstance(item.get("analysis"), dict) else {}
    cefr = analysis.get("cefr") if isinstance(analysis.get("cefr"), dict) else {}
    level = str(cefr.get("level") or "B1")
    architecture = analysis.get("architecture") if isinstance(analysis.get("architecture"), dict) else {}
    sentence_type = str(architecture.get("sentence_type") or "simple")
    communicative = str(architecture.get("communicative_type") or "declarative")
    sentence = str(item.get("input") or "").strip()

    return {
        "elementary": f"This sentence is {communicative.lower()} and expresses a clear message: {sentence}",
        "intermediate": f"Structure: {sentence_type}. The parse highlights clause organization and core verb choices.",
        "advanced": f"Estimated level {level}: marked by {sentence_type.lower()} architecture, controlled TAM patterns, and register cues.",
    }


def _generate_notes_via_chatgpt(
    *,
    item: dict[str, Any],
    example_bank: dict[str, list[dict[str, Any]]],
    model: str,
    api_key: str,
) -> dict[str, str] | None:
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except Exception:
        return None

    level = str(((item.get("analysis") or {}).get("cefr") or {}).get("level") or "B1").upper()
    examples = example_bank.get(level, [])
    limit = max(1, int(str(os.getenv("ELA_RAZBOR_EXAMPLES_PER_LEVEL", "2")).strip() or "2"))
    curated_examples: list[dict[str, Any]] = []
    for row in examples[:limit]:
        curated_examples.append(
            {
                "input": row.get("input"),
                "notes": row.get("notes"),
            }
        )

    prompt_payload = {
        "task": "Generate pedagogical notes for one analyzed English sentence.",
        "cefr_level": level,
        "sentence": item.get("input"),
        "analysis": item.get("analysis"),
        "reference_examples_same_level": curated_examples,
        "output_format": {
            "elementary": "string",
            "intermediate": "string",
            "advanced": "string",
        },
        "constraints": [
            "Return only JSON",
            "Do not include markdown or code fences",
            "Keep explanations faithful to provided analysis",
        ],
    }

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise CEFR linguistics assistant. "
                    "Return valid JSON with exactly keys elementary, intermediate, advanced."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_payload, ensure_ascii=False),
            },
        ],
    )
    content = ""
    if resp.choices:
        content = str(resp.choices[0].message.content or "")
    parsed = _extract_json_object(content)
    if parsed is None:
        return None
    notes = _coerce_notes_object(parsed)
    if not any(notes.values()):
        return None
    return notes


def _translations_stub(text: str) -> dict[str, dict[str, str]]:
    value = str(text or "").strip() or "-"
    return {
        "backend_m2m100": {
            "source_lang": "en",
            "target_lang": "ru",
            "text": value,
        }
    }


def _find_fragment_span(sentence_text: str, fragment: str, start_hint: int = 0) -> tuple[int, int]:
    source = str(sentence_text or "")
    frag = str(fragment or "").strip()
    if not frag:
        return 0, len(source)

    lowered_source = source.casefold()
    lowered_frag = frag.casefold()

    pos = lowered_source.find(lowered_frag, max(0, start_hint))
    if pos < 0:
        pos = lowered_source.find(lowered_frag)
    if pos < 0:
        return 0, len(source)
    return pos, pos + len(frag)


def _normalize_feature_for_contract(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _word_linguistic_note(lemma: str, features: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in sorted(features.keys()):
        value = features.get(key)
        rendered = _normalize_feature_for_contract(value)
        if rendered is None:
            continue
        parts.append(f"{key}={rendered}")
    features_text = ", ".join(parts) if parts else "none"
    return f"lemma={lemma}; features={features_text}"


def _map_razbor_item_to_sentence_contract(item: dict[str, Any], sentence_idx: int, nlp: Any) -> dict[str, Any]:
    sentence_text = str(item.get("input") or "").strip()
    analysis = item.get("analysis") if isinstance(item.get("analysis"), dict) else {}
    verb_system = ((analysis.get("verb_system") or {}).get("per_clause") or []) if isinstance(analysis, dict) else []
    morphology_tokens = ((analysis.get("morphology") or {}).get("tokens") or []) if isinstance(analysis, dict) else []
    cefr_level = str(((analysis.get("cefr") or {}).get("level") or "").strip())

    doc = nlp(sentence_text)
    sent = next(iter(doc.sents), doc[:])
    word_tokens = [tok for tok in sent if not tok.is_space and not tok.is_punct]
    morph_word_tokens = [
        row
        for row in morphology_tokens
        if isinstance(row, dict) and not re.fullmatch(r"[^\w]+", str(row.get("text") or ""), flags=re.UNICODE)
    ]

    word_rows: list[dict[str, Any]] = []
    for idx, token in enumerate(word_tokens):
        morph_row = morph_word_tokens[idx] if idx < len(morph_word_tokens) else {}
        lemma = str(morph_row.get("lemma") or token.lemma_ or token.text).lower()
        features_raw = morph_row.get("features") if isinstance(morph_row.get("features"), dict) else {}
        features: dict[str, str | None] = {}
        for key, value in features_raw.items():
            features[str(key)] = _normalize_feature_for_contract(value)

        tense_value = features.get("Tense")
        word_rows.append(
            {
                "token": token,
                "lemma": lemma,
                "features": features,
                "tense": tense_value,
                "note": _word_linguistic_note(lemma, features_raw if isinstance(features_raw, dict) else {}),
            }
        )

    clause_specs: list[dict[str, Any]] = []
    search_cursor = 0
    for idx, clause in enumerate(verb_system):
        if not isinstance(clause, dict):
            continue
        clause_span = str(clause.get("clause_span") or clause.get("span") or "").strip() or sentence_text
        start, end = _find_fragment_span(sentence_text, clause_span, start_hint=search_cursor)
        search_cursor = max(search_cursor, end)
        evidence = clause.get("evidence") if isinstance(clause.get("evidence"), list) else []
        clause_specs.append(
            {
                "idx": idx,
                "span": clause_span,
                "start": int(start),
                "end": int(end),
                "tense": clause.get("tense"),
                "aspect": clause.get("aspect"),
                "voice": clause.get("voice"),
                "mood": clause.get("mood"),
                "evidence": [str(v) for v in evidence if str(v).strip()],
            }
        )

    if not clause_specs:
        clause_specs.append(
            {
                "idx": 0,
                "span": sentence_text,
                "start": 0,
                "end": len(sentence_text),
                "tense": None,
                "aspect": None,
                "voice": None,
                "mood": None,
                "evidence": [],
            }
        )

    words_by_clause: dict[int, list[dict[str, Any]]] = {idx: [] for idx in range(len(clause_specs))}
    for row in word_rows:
        token = row["token"]
        token_start = int(token.idx)
        token_end = int(token.idx + len(token.text))
        chosen_idx: int | None = None
        for idx, clause in enumerate(clause_specs):
            if token_start >= int(clause["start"]) and token_end <= int(clause["end"]):
                chosen_idx = idx
                break
        if chosen_idx is None:
            distances = [
                abs(token_start - int(clause["start"])) + abs(token_end - int(clause["end"]))
                for clause in clause_specs
            ]
            chosen_idx = int(distances.index(min(distances))) if distances else 0
        words_by_clause.setdefault(chosen_idx, []).append(row)

    sentence_node_id = f"s{sentence_idx + 1}"
    phrase_nodes: list[dict[str, Any]] = []
    global_word_counter = 0

    for idx, clause in enumerate(clause_specs):
        phrase_node_id = f"{sentence_node_id}_p{idx + 1}"
        phrase_node: dict[str, Any] = {
            "type": "Phrase",
            "content": str(clause.get("span") or sentence_text),
            "tense": _normalize_feature_for_contract(clause.get("tense")),
            "aspect": _normalize_feature_for_contract(clause.get("aspect")),
            "mood": _normalize_feature_for_contract(clause.get("mood")),
            "voice": _normalize_feature_for_contract(clause.get("voice")),
            "finiteness": "finite",
            "linguistic_notes": [str(v) for v in clause.get("evidence", []) if str(v).strip()],
            "part_of_speech": "clause",
            "translations": _translations_stub(str(clause.get("span") or sentence_text)),
            "active_translation_provider": "backend_m2m100",
            "linguistic_elements": [],
            "node_id": phrase_node_id,
            "parent_id": sentence_node_id,
            "source_span": {
                "start": int(clause.get("start") or 0),
                "end": int(clause.get("end") or len(sentence_text)),
            },
            "grammatical_role": "subordinate clause" if idx > 0 else "main clause",
            "schema_version": "v2",
        }
        if cefr_level:
            phrase_node["cefr_level"] = cefr_level

        for word in words_by_clause.get(idx, []):
            token = word["token"]
            global_word_counter += 1
            word_node: dict[str, Any] = {
                "type": "Word",
                "content": str(token.text),
                "tense": _normalize_feature_for_contract(word.get("tense")),
                "linguistic_notes": [str(word.get("note") or "")],
                "part_of_speech": _WORD_POS_MAP.get(token.pos_, "other"),
                "translations": _translations_stub(str(token.text)),
                "active_translation_provider": "backend_m2m100",
                "linguistic_elements": [],
                "node_id": f"{sentence_node_id}_w{global_word_counter}",
                "parent_id": phrase_node_id,
                "source_span": {
                    "start": int(token.idx),
                    "end": int(token.idx + len(token.text)),
                },
                "grammatical_role": _GRAMMAR_ROLE_MAP.get(token.dep_, "other"),
                "schema_version": "v2",
                "features": word.get("features") or {},
                "dep_label": str(token.dep_),
                "head_id": None,
            }
            if cefr_level:
                word_node["cefr_level"] = cefr_level
            phrase_node["linguistic_elements"].append(word_node)

        phrase_nodes.append(phrase_node)

    notes = item.get("notes") if isinstance(item.get("notes"), dict) else {}
    sentence_notes = [
        str(notes.get("elementary") or "").strip(),
        str(notes.get("intermediate") or "").strip(),
        str(notes.get("advanced") or "").strip(),
    ]
    sentence_notes = [note for note in sentence_notes if note]

    first_clause = clause_specs[0] if clause_specs else {}
    sentence_node: dict[str, Any] = {
        "type": "Sentence",
        "content": sentence_text,
        "tense": _normalize_feature_for_contract(first_clause.get("tense")),
        "aspect": _normalize_feature_for_contract(first_clause.get("aspect")),
        "mood": _normalize_feature_for_contract(first_clause.get("mood")),
        "voice": _normalize_feature_for_contract(first_clause.get("voice")),
        "finiteness": "finite",
        "linguistic_notes": sentence_notes,
        "part_of_speech": "sentence",
        "translations": _translations_stub(sentence_text),
        "active_translation_provider": "backend_m2m100",
        "linguistic_elements": phrase_nodes,
        "node_id": sentence_node_id,
        "parent_id": None,
        "source_span": {
            "start": 0,
            "end": len(sentence_text),
        },
        "grammatical_role": "clause",
        "schema_version": "v2",
    }
    if cefr_level:
        sentence_node["cefr_level"] = cefr_level

    return sentence_node


def _split_sentence_stream(raw_text: str, nlp: Any) -> list[str]:
    text = str(raw_text or "").strip()
    if not text:
        return []
    doc = nlp(text)
    stream: list[str] = []
    for sent in doc.sents:
        value = _normalize_spaces(sent.text)
        if value:
            stream.append(value)
    return stream


def _normalize_sentence_array(sentences: list[Any] | None) -> list[str]:
    if not isinstance(sentences, list):
        return []
    out: list[str] = []
    for row in sentences:
        value = _normalize_spaces(str(row or ""))
        if value:
            out.append(value)
    return out


def build_text_analysis_payload(
    *,
    raw_text: str,
    sentences: list[Any] | None = None,
    spacy_model: str = "en_core_web_sm",
    generate_notes: bool = True,
    examples_path: str = "docs/example_sentences_razbor.json",
) -> dict[str, Any]:
    nlp = load_nlp(spacy_model)
    sentence_stream = _normalize_sentence_array(sentences)
    if not sentence_stream:
        sentence_stream = _split_sentence_stream(raw_text, nlp)

    if not sentence_stream:
        raise ValueError("No valid sentences to analyze.")

    example_bank = _load_example_bank(examples_path)
    openai_api_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    openai_model = str(os.getenv("ELA_RAZBOR_OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"

    razbor_items: list[dict[str, Any]] = []
    contract: dict[str, Any] = {}
    notes_sources: list[str] = []

    for sentence_idx, sentence_text in enumerate(sentence_stream):
        item = _build_razbor_item(sentence_text, sentence_idx, nlp)

        notes = _empty_notes()
        source = "empty"
        if generate_notes:
            chatgpt_notes: dict[str, str] | None = None
            if openai_api_key:
                try:
                    chatgpt_notes = _generate_notes_via_chatgpt(
                        item=item,
                        example_bank=example_bank,
                        model=openai_model,
                        api_key=openai_api_key,
                    )
                except Exception:
                    chatgpt_notes = None
            if chatgpt_notes is not None:
                notes = _coerce_notes_object(chatgpt_notes)
                source = "chatgpt"
            else:
                notes = _fallback_notes_for_item(item)
                source = "fallback"

        item["notes"] = notes
        raise_if_invalid(validate_razbor_contract(item))
        razbor_items.append(item)
        notes_sources.append(source)

        sentence_node = _map_razbor_item_to_sentence_contract(item, sentence_idx, nlp)
        contract[sentence_node["content"]] = sentence_node

    raise_if_invalid(validate_contract(contract, validation_mode="v2_strict"))

    return {
        "raw_text": str(raw_text or "").strip(),
        "sentences": sentence_stream,
        "razbor": razbor_items,
        "contract": contract,
        "notes_sources": notes_sources,
    }
