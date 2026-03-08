"""Sentence-level pedagogical notes with subject/predicate focus."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

from ela_pipeline.parse.spacy_parser import load_nlp

_SUBJECT_DEPS = {"nsubj", "nsubjpass", "csubj", "csubjpass", "expl"}
_FINITE_CLAUSE_DEPS = {"root", "conj", "advcl", "ccomp", "xcomp", "acl", "relcl", "parataxis"}
_PREDICATE_COMPLEMENT_DEPS = {"obj", "dobj", "iobj", "attr", "acomp", "oprd", "xcomp", "ccomp"}
_PREDICATE_ADVERBIAL_DEPS = {"advmod", "obl", "npadvmod", "prep", "mark"}


@lru_cache(maxsize=4)
def _get_nlp_cached(model_name: str):
    return load_nlp(model_name)


def _normalize_spaces(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _normalize_for_match(text: str) -> str:
    return _normalize_spaces(text).casefold()


def _token_span_text(token: Any) -> str:
    span = token.doc[token.left_edge.i : token.right_edge.i + 1]
    return _normalize_spaces(span.text)


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = _normalize_spaces(item)
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _dedupe_spans(items: list[str]) -> list[str]:
    base = _dedupe(items)
    out: list[str] = []
    for value in base:
        norm_value = value.casefold()
        if not norm_value:
            continue
        replaced = False
        for idx, existing in enumerate(out):
            norm_existing = existing.casefold()
            if norm_value in norm_existing:
                replaced = True
                break
            if norm_existing in norm_value:
                out[idx] = value
                replaced = True
                break
        if not replaced:
            out.append(value)
    return out


def _subject_profile(sent: Any) -> dict[str, Any]:
    heads = [tok for tok in sent if tok.dep_.lower() in _SUBJECT_DEPS]
    if not heads:
        return {
            "type": "omitted",
            "components": {
                "heads": [],
                "coordinated": [],
                "modifiers": [],
            },
        }

    head_forms = _dedupe([tok.text for tok in heads])
    coordinated = _dedupe([child.text for tok in heads for child in tok.children if child.dep_.lower() == "conj"])
    modifiers = _dedupe(
        [
            child.text
            for tok in heads
            for child in tok.children
            if child.dep_.lower() in {"amod", "det", "compound", "nmod", "poss", "appos"}
        ]
    )
    has_clausal_expansion = any(
        child.dep_.lower() in {"relcl", "acl", "ccomp", "xcomp"} for tok in heads for child in tok.children
    )

    subj_type = "simple"
    if coordinated:
        subj_type = "compound"
    elif has_clausal_expansion:
        subj_type = "complex"

    return {
        "type": subj_type,
        "components": {
            "heads": head_forms,
            "coordinated": coordinated,
            "modifiers": modifiers,
            "spans": _dedupe([_token_span_text(tok) for tok in heads]),
        },
    }


def _is_finite_verb(token: Any) -> bool:
    if token.pos_ not in {"VERB", "AUX"}:
        return False
    verb_form = token.morph.get("VerbForm")
    if "Fin" in verb_form:
        return True
    return token.tag_ == "MD"


def _predicate_profile(sent: Any) -> dict[str, Any]:
    roots = [tok for tok in sent if tok.dep_ == "ROOT" and tok.pos_ in {"VERB", "AUX"}]
    root = roots[0] if roots else None
    finite_heads = [tok for tok in sent if _is_finite_verb(tok) and tok.dep_.lower() in _FINITE_CLAUSE_DEPS]
    if root is None and finite_heads:
        root = finite_heads[0]

    if root is None:
        return {
            "type": "complex",
            "components": {
                "finite_heads": [],
                "auxiliaries": [],
                "complements": [],
                "adverbials": [],
                "non_finite_chains": [],
            },
        }

    auxiliaries = _dedupe([child.text for child in root.children if child.dep_.lower() in {"aux", "auxpass"}])
    complements = _dedupe_spans(
        [_token_span_text(child) for child in root.children if child.dep_.lower() in _PREDICATE_COMPLEMENT_DEPS]
    )
    adverbials = _dedupe_spans(
        [_token_span_text(child) for child in root.children if child.dep_.lower() in _PREDICATE_ADVERBIAL_DEPS]
    )
    non_finite = _dedupe_spans(
        [
            _token_span_text(tok)
            for tok in sent
            if tok.pos_ in {"VERB", "AUX"}
            and "Fin" not in tok.morph.get("VerbForm")
            and tok.dep_.lower() in {"advcl", "xcomp", "ccomp", "conj", "acl", "relcl"}
        ]
    )
    coordinated_finite = [
        tok for tok in finite_heads if tok.dep_.lower() == "conj" and tok.i != root.i
    ]

    pred_type = "simple_verbal"
    is_copular_nominal = root.lemma_.lower() == "be" and any(
        child.dep_.lower() in {"attr", "acomp"} for child in root.children
    )
    if non_finite or coordinated_finite:
        pred_type = "complex"
    elif is_copular_nominal:
        pred_type = "compound_nominal"
    elif auxiliaries:
        pred_type = "compound_verbal"

    return {
        "type": pred_type,
        "components": {
            "finite_heads": _dedupe([tok.text for tok in finite_heads]) or [root.text],
            "root": root.text,
            "auxiliaries": auxiliaries,
            "complements": complements,
            "adverbials": adverbials,
            "non_finite_chains": non_finite,
        },
    }


def build_core_syntax(sentence_text: str, *, spacy_model: str = "en_core_web_sm") -> dict[str, Any]:
    nlp = _get_nlp_cached(spacy_model)
    doc = nlp(str(sentence_text or "").strip())
    sent = next(iter(doc.sents), None)
    if sent is None:
        return {
            "subject": {"type": "omitted", "components": {"heads": [], "coordinated": [], "modifiers": []}},
            "predicate": {
                "type": "complex",
                "components": {
                    "finite_heads": [],
                    "auxiliaries": [],
                    "complements": [],
                    "adverbials": [],
                    "non_finite_chains": [],
                },
            },
        }
    return {
        "subject": _subject_profile(sent),
        "predicate": _predicate_profile(sent),
    }


def _fallback_notes(*, core_syntax: dict[str, Any]) -> dict[str, str]:
    subject = core_syntax.get("subject") if isinstance(core_syntax, dict) else {}
    predicate = core_syntax.get("predicate") if isinstance(core_syntax, dict) else {}

    subj_type = str((subject or {}).get("type") or "omitted")
    subj_heads = (subject or {}).get("components", {}).get("heads") or []
    pred_type = str((predicate or {}).get("type") or "complex")
    pred_heads = (predicate or {}).get("components", {}).get("finite_heads") or []
    non_finite = (predicate or {}).get("components", {}).get("non_finite_chains") or []
    adverbials = (predicate or {}).get("components", {}).get("adverbials") or []

    subj_label = ", ".join([str(x) for x in subj_heads if str(x).strip()]) or "not clearly shown"
    pred_label = ", ".join([str(x) for x in pred_heads if str(x).strip()]) or "not clearly shown"
    non_finite_label = ", ".join([str(x) for x in _dedupe_spans([str(x) for x in non_finite])[:2] if str(x).strip()])
    adverbial_label = ", ".join([str(x) for x in _dedupe_spans([str(x) for x in adverbials])[:2] if str(x).strip()])

    subject_type_map = {
        "simple": "simple",
        "compound": "compound",
        "complex": "extended",
        "omitted": "not expressed",
    }
    predicate_type_map = {
        "simple_verbal": "simple verbal",
        "compound_verbal": "compound verbal",
        "compound_nominal": "compound nominal",
        "complex": "complex",
    }
    subj_type_label = subject_type_map.get(subj_type, subj_type.replace("_", " "))
    pred_type_label = predicate_type_map.get(pred_type, pred_type.replace("_", " "))

    elementary = (
        f"The subject is {subj_type_label} ({subj_label}). "
        f"The predicate is {pred_type_label} ({pred_label})."
    )

    intermediate_parts = [
        f"Subject: {subj_type_label}; main word: {subj_label}.",
        f"Predicate: {pred_type_label}; main verb form: {pred_label}.",
    ]
    if non_finite_label:
        intermediate_parts.append(f"There are extra -ing/-ed action parts: {non_finite_label}.")
    if adverbial_label:
        intermediate_parts.append(f"Meaning is specified by modifiers: {adverbial_label}.")
    intermediate = " ".join(intermediate_parts[:4])

    advanced_parts = [
        f"Subject: {subj_type_label} ({subj_label}). Predicate: {pred_type_label} with main verb {pred_label}.",
    ]
    if non_finite_label:
        advanced_parts.append(f"The predicate is expanded by extra action constructions: {non_finite_label}.")
    if adverbial_label:
        advanced_parts.append(f"Modifier groups add manner/circumstance: {adverbial_label}.")
    advanced = " ".join(advanced_parts[:3])
    return {
        "elementary": elementary,
        "intermediate": intermediate,
        "advanced": advanced,
    }


def _coerce_notes(payload: dict[str, Any] | None) -> dict[str, str]:
    out = {"elementary": "", "intermediate": "", "advanced": ""}
    if not isinstance(payload, dict):
        return out
    for key in out:
        raw = str(payload.get(key) or "")
        cleaned = re.sub(r"^\s*(linguistic\s*notes?|notes?)\s*:\s*", "", raw, flags=re.IGNORECASE)
        out[key] = _normalize_spaces(cleaned)
    return out


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _quality_gate(*, notes: dict[str, str], sentence_text: str) -> bool:
    source_norm = _normalize_for_match(sentence_text)
    if not source_norm:
        return False

    limits = {"elementary": 180, "intermediate": 360, "advanced": 420}
    for key, max_chars in limits.items():
        value = _normalize_spaces(str(notes.get(key) or ""))
        if not value:
            return False
        if len(value) > max_chars:
            return False
        if source_norm in _normalize_for_match(value):
            return False
        if value.casefold().startswith("this sentence"):
            return False

    intermediate = _normalize_for_match(notes.get("intermediate", ""))
    advanced = _normalize_for_match(notes.get("advanced", ""))
    if "subject" not in intermediate or "predicate" not in intermediate:
        return False
    if "subject" not in advanced or "predicate" not in advanced:
        return False
    return True


def _chatgpt_notes(
    *,
    sentence_text: str,
    core_syntax: dict[str, Any],
    model: str,
    api_key: str,
) -> dict[str, str] | None:
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except Exception:
        return None

    payload = {
        "task": "Generate pedagogical sentence notes with explicit subject/predicate focus.",
        "sentence": sentence_text,
        "core_syntax": core_syntax,
        "output_format": {"elementary": "string", "intermediate": "string", "advanced": "string"},
        "constraints": [
            "Return only JSON",
            "Do not repeat the full sentence text",
            "Each note must mention subject and predicate",
            "Elementary should be one short sentence",
            "Intermediate should provide 2-3 structural facts",
            "Use school-friendly grammar wording and avoid heavy linguistic terms",
            "Advanced should focus on grammar constructions: clause type, verb links, modifiers",
            "No markdown, no labels, no placeholders",
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
                    "You are a precise English grammar assistant. "
                    "Return valid JSON with exactly keys elementary, intermediate, advanced."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
    )
    content = ""
    if resp.choices:
        content = str(resp.choices[0].message.content or "")
    parsed = _extract_json_object(content)
    if parsed is None:
        return None
    notes = _coerce_notes(parsed)
    if not _quality_gate(notes=notes, sentence_text=sentence_text):
        return None
    return notes


def build_sentence_notes(sentence_text: str) -> dict[str, str]:
    text = _normalize_spaces(sentence_text)
    if not text:
        return {"elementary": "", "intermediate": "", "advanced": ""}

    core_syntax = build_core_syntax(text)
    notes = _fallback_notes(core_syntax=core_syntax)

    use_chatgpt = str(os.getenv("ELA_SENTENCE_NOTES_USE_CHATGPT", "0")).strip().lower() in {"1", "true", "yes", "on"}
    api_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    model = str(os.getenv("ELA_SENTENCE_NOTES_OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"
    if use_chatgpt and api_key:
        generated = _chatgpt_notes(
            sentence_text=text,
            core_syntax=core_syntax,
            model=model,
            api_key=api_key,
        )
        if generated is not None:
            notes = generated

    if not _quality_gate(notes=notes, sentence_text=text):
        notes = _fallback_notes(core_syntax=core_syntax)

    return {
        "elementary": _normalize_spaces(notes.get("elementary", "")),
        "intermediate": _normalize_spaces(notes.get("intermediate", "")),
        "advanced": _normalize_spaces(notes.get("advanced", "")),
    }
