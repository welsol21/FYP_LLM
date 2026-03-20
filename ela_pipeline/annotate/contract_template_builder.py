"""Build contract-safe note templates for Sentence and Phrase nodes."""

from __future__ import annotations

import json
import re
from typing import Any

from ela_pipeline.annotate.template_registry import (
    REGISTRY_VERSION,
    SENTENCE_MODAL_PERFECT_VARIANTS,
    TEMPLATE_VARIANTS,
    TemplateSelection,
    is_template_semantically_compatible,
    render_template_note,
    select_template_candidates,
)
from ela_pipeline.validation.notes_quality import sanitize_note

CONTRACT_TEMPLATE_VERSION = "v1"
CONTRACT_PROMPT_TEMPLATE_VERSION = "contract_template_v2"
CONTRACT_CLASSIFIER_PROMPT_TEMPLATE_VERSION = "contract_template_classifier_v1"
_SLOT_RE = re.compile(r"{{([A-Z_]+)}}")
_TAG_RE = re.compile(r",\s*([A-Za-z]+(?:n't)?)\s+([A-Za-z]+)\?\s*$", re.IGNORECASE)
_PREPOSITIONS = {
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "around",
    "as",
    "at",
    "before",
    "behind",
    "below",
    "beneath",
    "beside",
    "between",
    "beyond",
    "by",
    "down",
    "during",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "near",
    "of",
    "off",
    "on",
    "onto",
    "out",
    "outside",
    "over",
    "past",
    "through",
    "to",
    "toward",
    "under",
    "up",
    "upon",
    "with",
    "within",
    "without",
}
_RELATIVE_MARKERS = {"who", "which", "that", "whom", "whose", "where", "when", "why"}
_UNSAFE_HEAD_WORDS = _RELATIVE_MARKERS | {
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
}
_TAG_PRONOUNS = {"i", "you", "he", "she", "it", "we", "they", "there"}
_SUPPORTED_NODE_TYPES = {"sentence", "phrase"}
_SENTENCE_PRIORITY = [
    "SENT_QUESTION_TAG",
    "SENT_QUESTION_WH_DO_SUPPORT",
    "SENT_QUESTION_WH",
    "SENT_QUESTION_YES_NO_DO_SUPPORT",
    "SENT_QUESTION_YES_NO_AUX",
    "SENT_EXISTENTIAL_THERE_QUESTION",
    "SENT_EXISTENTIAL_THERE_AGREEMENT",
    "SENT_EXISTENTIAL_THERE",
    "SENT_EXTRAPOSITION_IT_THAT",
    "SENT_CLEFT_IT",
    "SENT_PASSIVE_PERFECT",
    "SENT_PASSIVE_PROGRESSIVE",
    "SENT_PASSIVE_REPORTING_IT",
    "SENT_PASSIVE_AGENTLESS",
    "SENT_PASSIVE_GENERAL",
    "SENT_CONDITIONAL_THIRD",
    "SENT_CONDITIONAL_SECOND",
    "SENT_CONDITIONAL_FIRST",
    "SENT_CONDITIONAL_ZERO",
    "SENT_CONDITIONAL_CONCESSIVE",
    "SENT_CONDITIONAL_FORMAL_SHOULD",
    "SENT_CONDITIONAL_IMPERATIVE_RESULT",
    "SENT_CONDITIONAL_PRESENT_MODAL",
    "SENT_CONDITIONAL_COUNTERFACTUAL_PAST",
    "SENT_CONDITIONAL_COUNTERFACTUAL",
    "SENT_CONDITIONAL_FACTUAL",
    "SENT_CONDITIONAL_NECESSARY_CONDITION",
    "SENT_CONDITIONAL_PREDICTIVE",
    "SENT_CONDITIONAL_GENERAL",
    "SENT_TIME_CLAUSE_FUTURE_REFERENCE",
    "SENT_NOUN_CLAUSE_THAT",
    "SENT_NOUN_CLAUSE_WH",
    "SENT_NEGATION_DO_SUPPORT",
    "SENT_NEGATION_AUXILIARY",
    "SENT_NEGATION_GENERAL",
    "SENT_MODAL_GENERAL",
    "SENT_PERFECT_GENERAL",
    "SENT_PROGRESSIVE_GENERAL",
    "SENT_IMPERATIVE",
    "SENT_EXCLAMATIVE",
    "SENT_DECLARATIVE",
    "SENT_ACTIVE_VOICE",
    "SENTENCE_FINITE_CLAUSE",
]
_PHRASE_PRIORITY = [
    "PHRASE_PP_LOCATION",
    "PHRASE_PP_TIME",
    "PHRASE_PP_SOURCE",
    "PHRASE_PP_PURPOSE",
    "PHRASE_PP_AGENT",
    "PHRASE_PP_MEANS",
    "PHRASE_PP_ASSOCIATION",
    "PHRASE_PP_GENERAL",
    "PHRASE_RELATIVE_CLAUSE_STRANDED_PREP",
    "PHRASE_RELATIVE_CLAUSE_FRONTED_PREP",
    "PHRASE_RELATIVE_CLAUSE_NONRESTRICTIVE",
    "PHRASE_RELATIVE_CLAUSE_RESTRICTIVE",
    "PHRASE_RELATIVE_CLAUSE",
    "PHRASE_VP_PERFECT_PROGRESSIVE",
    "PHRASE_VP_PROGRESSIVE",
    "PHRASE_VP_PERFECT",
    "PHRASE_VP_PASSIVE",
    "PHRASE_VP_MODAL",
    "PHRASE_VP_INFINITIVE",
    "PHRASE_VP_ING_NONFINITE",
    "PHRASE_VP_PHRASAL_VERB",
    "PHRASE_VP_COLLOCATION",
    "PHRASE_VP_GENERAL",
    "PP_TIME_BEFORE_ING",
    "PP_GENERAL_LINKING",
    "VP_MODAL_PERFECT",
    "VP_AUXILIARY",
    "VP_PARTICIPLE",
    "NP_POSSESSIVE",
    "NP_DETERMINER_NOUN",
]

_TEMPLATE_OVERRIDES: dict[str, str] = {
    "SENT_QUESTION_TAG": "Question tags repeat {{TAG_AUXILIARY}} and use {{TAG_PRONOUN}} as the pronoun subject.",
    "PHRASE_PP_GENERAL": 'This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and links its complement to the wider clause.',
    "PHRASE_PP_LOCATION": 'This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses location or spatial position.',
    "PHRASE_PP_TIME": 'This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses time or temporal setting.',
    "PHRASE_PP_SOURCE": 'This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses source or origin.',
    "PHRASE_PP_PURPOSE": 'This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses purpose or intended use.',
    "PHRASE_PP_AGENT": 'This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and marks the agent or performer.',
    "PHRASE_PP_MEANS": 'This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses means, method, or instrument.',
    "PHRASE_PP_ASSOCIATION": 'This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses association or accompaniment.',
    "PHRASE_RELATIVE_CLAUSE": 'This relative clause gives more information about the noun "{{HEAD_NOUN}}".',
    "PHRASE_RELATIVE_CLAUSE_RESTRICTIVE": 'This restrictive relative clause helps identify the noun "{{HEAD_NOUN}}".',
    "PHRASE_RELATIVE_CLAUSE_NONRESTRICTIVE": 'This non-restrictive relative clause adds extra information about the noun "{{HEAD_NOUN}}".',
    "PHRASE_RELATIVE_CLAUSE_STRANDED_PREP": 'This relative clause leaves the preposition "{{PREPOSITION}}" later in the clause instead of placing it before "{{RELATIVE_MARKER}}".',
    "PHRASE_RELATIVE_CLAUSE_FRONTED_PREP": 'This pattern uses "{{PREPOSITION}}" + "{{RELATIVE_MARKER}}" in the relative clause.',
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _walk_nodes(node: dict[str, Any]):
    yield node
    for child in node.get("linguistic_elements") or []:
        if isinstance(child, dict):
            yield from _walk_nodes(child)


def _descendant_words(node: dict[str, Any]) -> list[dict[str, Any]]:
    words = [item for item in _walk_nodes(node) if str(item.get("type") or "").strip() == "Word"]
    words.sort(key=lambda item: int((item.get("source_span") or {}).get("start", 0)))
    return words


def _grammar_class_ids(node: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in node.get("grammar_classes") or []:
        if not isinstance(item, dict):
            continue
        class_id = _norm(item.get("class_id"))
        if class_id:
            out.append(class_id)
    return out


def _extract_preposition_object(node: dict[str, Any]) -> tuple[str | None, str | None]:
    phrase_text = _norm(node.get("content"))
    words = _descendant_words(node)
    preposition = None
    word_texts: list[str] = []
    for word in words:
        token = _norm(word.get("content"))
        if not token:
            continue
        word_texts.append(token)
        if preposition is None:
            pos = _norm_lower(word.get("part_of_speech"))
            if pos == "preposition" and token.lower() in _PREPOSITIONS:
                preposition = token
    if not preposition:
        parts = phrase_text.split()
        if parts and parts[0].lower() in _PREPOSITIONS:
            preposition = parts[0]
    if not preposition:
        return None, None
    parts = phrase_text.split()
    if parts and parts[0].lower() == preposition.lower() and len(parts) > 1:
        return preposition, " ".join(parts[1:]).strip() or None
    for idx, token in enumerate(word_texts):
        if token.lower() == preposition.lower() and idx + 1 < len(word_texts):
            return preposition, " ".join(word_texts[idx + 1 :]).strip() or None
    return preposition, None


def _extract_relative_marker(node: dict[str, Any]) -> str | None:
    for word in _descendant_words(node):
        token = _norm_lower(word.get("content"))
        if token in _RELATIVE_MARKERS:
            return _norm(word.get("content"))
    return None


def _previous_head_noun(sentence_node: dict[str, Any], target_node: dict[str, Any]) -> str | None:
    target_start = int((target_node.get("source_span") or {}).get("start", -1))
    if target_start < 0:
        return None
    candidates: list[dict[str, Any]] = []
    for node in _walk_nodes(sentence_node):
        if str(node.get("type") or "").strip() != "Word":
            continue
        node_start = int((node.get("source_span") or {}).get("start", -1))
        if node_start < 0 or node_start >= target_start:
            continue
        pos = _norm_lower(node.get("part_of_speech"))
        content = _norm_lower(node.get("content"))
        if pos in {"noun", "proper noun"} and content not in _UNSAFE_HEAD_WORDS:
            candidates.append(node)
    if not candidates:
        return None
    candidates.sort(key=lambda item: int((item.get("source_span") or {}).get("start", 0)))
    return _norm(candidates[-1].get("content")) or None


def _extract_question_tag_slots(sentence_node: dict[str, Any]) -> dict[str, str] | None:
    match = _TAG_RE.search(_norm(sentence_node.get("content")))
    if not match:
        return None
    auxiliary = _norm(match.group(1))
    pronoun = _norm(match.group(2))
    if pronoun.lower() not in _TAG_PRONOUNS:
        return None
    return {"TAG_AUXILIARY": auxiliary, "TAG_PRONOUN": pronoun}


def _allowed_slots(template_text: str) -> list[str]:
    seen: list[str] = []
    for slot in _SLOT_RE.findall(template_text or ""):
        if slot not in seen:
            seen.append(slot)
    return seen


def normalize_template_text(template_text: str) -> str:
    return sanitize_note(str(template_text or ""))


def _looks_like_prompt_leakage(template_text: str) -> bool:
    lowered = normalize_template_text(template_text).lower()
    if not lowered:
        return False
    leak_markers = (
        "keep exactly the same placeholders",
        "return template text only",
        "do not invent placeholders",
        "payload:",
        "template_text field",
        "audience level:",
        "rewrite this contract-safe linguistic note template",
        "rewrite_linguistic_note_template_from_contract_template",
    )
    return any(marker in lowered for marker in leak_markers)


def template_uses_allowed_slots(template_text: str, allowed_slots: list[str] | tuple[str, ...] | None) -> bool:
    normalized = normalize_template_text(template_text)
    expected = [str(slot).strip() for slot in (allowed_slots or []) if str(slot).strip()]
    actual = _allowed_slots(normalized)
    return set(actual) == set(expected) and len(actual) == len(expected)


def resolve_generated_template_text(
    generated_template_text: str,
    *,
    default_template_text: str,
    allowed_slots: list[str] | tuple[str, ...] | None,
) -> tuple[str, str]:
    candidate = normalize_template_text(generated_template_text)
    default = normalize_template_text(default_template_text)
    if not candidate:
        return default, "template_fallback_empty"
    if _looks_like_prompt_leakage(candidate):
        return default, "template_fallback_prompt_leakage"
    if not template_uses_allowed_slots(candidate, allowed_slots):
        return default, "template_fallback_slot_mismatch"
    return candidate, "template_generated"


def _selection_to_dict(selection: TemplateSelection, *, semantic_rejects: list[dict[str, str]] | None = None) -> dict[str, Any]:
    payload = {
        "level": selection.level,
        "template_id": selection.template_id,
        "matched_key": selection.matched_key,
        "registry_version": selection.registry_version,
        "context_key_l1": selection.context_key_l1,
        "context_key_l2": selection.context_key_l2,
        "context_key_l3": selection.context_key_l3,
    }
    if semantic_rejects:
        payload["semantic_rejects"] = semantic_rejects
    return payload


def _select_contract_template(node: dict[str, Any]) -> tuple[TemplateSelection, list[dict[str, str]]]:
    candidates = select_template_candidates(node)
    semantic_rejects: list[dict[str, str]] = []
    base = candidates[0]
    node_type = _norm_lower(node.get("type"))
    priority_ids = _SENTENCE_PRIORITY if node_type == "sentence" else _PHRASE_PRIORITY
    for template_id in priority_ids:
        if not is_template_semantically_compatible(node, template_id):
            continue
        return (
            TemplateSelection(
                level="SEMANTIC_PRIORITY",
                template_id=template_id,
                matched_key=f"semantic::{template_id.lower()}",
                registry_version=REGISTRY_VERSION,
                context_key_l1=base.context_key_l1,
                context_key_l2=base.context_key_l2,
                context_key_l3=base.context_key_l3,
            ),
            semantic_rejects,
        )
    for selection in candidates:
        template_id = _norm(selection.template_id)
        if template_id and is_template_semantically_compatible(node, template_id):
            return selection, semantic_rejects
        if template_id:
            semantic_rejects.append({"template_id": template_id, "level": selection.level})
    return candidates[-1], semantic_rejects


def _template_text_for(node: dict[str, Any], template_id: str) -> str:
    override = _TEMPLATE_OVERRIDES.get(template_id)
    if override:
        return override
    if template_id == "SENTENCE_FINITE_CLAUSE" and _norm_lower(node.get("tam_construction")) == "modal_perfect":
        variants = SENTENCE_MODAL_PERFECT_VARIANTS
    else:
        variants = TEMPLATE_VARIANTS.get(template_id) or []
    if not variants:
        return ""
    return str(variants[0]).replace("{content}", "{{CONTENT}}")


def _slot_values(
    *,
    node: dict[str, Any],
    sentence_node: dict[str, Any],
    parent: dict[str, Any] | None,
) -> dict[str, Any]:
    preposition, object_np = (None, None)
    relative_marker = None
    head_noun = None
    if _norm_lower(node.get("type")) == "phrase":
        preposition, object_np = _extract_preposition_object(node)
        relative_marker = _extract_relative_marker(node)
        head_noun = _previous_head_noun(sentence_node, node)
    tag_slots = _extract_question_tag_slots(sentence_node) if _norm_lower(node.get("type")) == "sentence" else None
    return {
        "CONTENT": _norm(node.get("content")) or None,
        "PART_OF_SPEECH": _norm(node.get("part_of_speech")) or None,
        "GRAMMATICAL_ROLE": _norm(node.get("grammatical_role")) or None,
        "NODE_TYPE": _norm(node.get("type")) or None,
        "CEFR_LEVEL": _norm(node.get("cefr_level")) or None,
        "TAM_CONSTRUCTION": _norm(node.get("tam_construction")) or None,
        "SENTENCE_TEXT": _norm(sentence_node.get("content")) or None,
        "PARENT_CONTENT": _norm(parent.get("content")) if isinstance(parent, dict) else None,
        "PARENT_PART_OF_SPEECH": _norm(parent.get("part_of_speech")) if isinstance(parent, dict) else None,
        "PARENT_GRAMMATICAL_ROLE": _norm(parent.get("grammatical_role")) if isinstance(parent, dict) else None,
        "PREPOSITION": preposition,
        "OBJECT_NP": object_np,
        "RELATIVE_MARKER": relative_marker,
        "HEAD_NOUN": head_noun,
        "TAG_AUXILIARY": (tag_slots or {}).get("TAG_AUXILIARY"),
        "TAG_PRONOUN": (tag_slots or {}).get("TAG_PRONOUN"),
    }


def should_template_node(node: dict[str, Any]) -> bool:
    return _norm_lower(node.get("type")) in _SUPPORTED_NODE_TYPES


def render_contract_template(
    template_text: str,
    *,
    slot_values: dict[str, Any],
    fallback_note: str,
) -> tuple[str, str]:
    if not _norm(template_text):
        return sanitize_note(fallback_note), "fallback_missing_template"
    allowed = _allowed_slots(template_text)
    missing = [slot for slot in allowed if not _norm(slot_values.get(slot))]
    if missing:
        return sanitize_note(fallback_note), "fallback_missing_slots"
    rendered = template_text
    for slot in allowed:
        rendered = rendered.replace("{{" + slot + "}}", _norm(slot_values.get(slot)))
    rendered = re.sub(r"\s+", " ", rendered).strip()
    rendered = rendered.replace(" .", ".")
    rendered = rendered.replace(" ,", ",")
    note = sanitize_note(rendered)
    if note:
        return note, "template_rendered"
    return sanitize_note(fallback_note), "fallback_empty_render"


def build_contract_template_payload(
    *,
    node: dict[str, Any],
    sentence_node: dict[str, Any],
    parent: dict[str, Any] | None,
    path_types: list[str],
    depth: int,
    sibling_index: int,
    sibling_count: int,
) -> dict[str, Any] | None:
    if not should_template_node(node):
        return None
    selection, semantic_rejects = _select_contract_template(node)
    template_id = _norm(selection.template_id)
    template_text = _template_text_for(node, template_id)
    slots = _slot_values(node=node, sentence_node=sentence_node, parent=parent)
    allowed_slots = _allowed_slots(template_text)
    fallback_note = render_template_note(template_id, node, selection.matched_key or "") if template_id else ""
    rendered_note, render_status = render_contract_template(
        template_text,
        slot_values=slots,
        fallback_note=fallback_note,
    )
    children = [child for child in (node.get("linguistic_elements") or []) if isinstance(child, dict)]
    return {
        "note_template_version": CONTRACT_TEMPLATE_VERSION,
        "template_id": template_id,
        "template_text": template_text,
        "allowed_slots": allowed_slots,
        "slot_values": {slot: slots.get(slot) for slot in allowed_slots},
        "selection": _selection_to_dict(selection, semantic_rejects=semantic_rejects),
        "fallback_note_text": fallback_note,
        "rendered_note_text": rendered_note,
        "render_status": render_status,
        "registry_version": REGISTRY_VERSION,
        "note_template_input": {
            "node_id": node.get("node_id"),
            "node_type": node.get("type"),
            "path_types": list(path_types),
            "depth": depth,
            "sibling_index": sibling_index,
            "sibling_count": sibling_count,
            "node_context": {
                "content": _norm(node.get("content")),
                "part_of_speech": _norm(node.get("part_of_speech")),
                "grammatical_role": _norm(node.get("grammatical_role")),
                "cefr_level": _norm(node.get("cefr_level")),
                "tam_construction": _norm(node.get("tam_construction")),
                "grammar_class_ids": _grammar_class_ids(node),
            },
            "sentence_context": {
                "sentence_text": _norm(sentence_node.get("content")),
            },
            "parent_context": {
                "content": _norm(parent.get("content")) if isinstance(parent, dict) else "",
                "part_of_speech": _norm(parent.get("part_of_speech")) if isinstance(parent, dict) else "",
                "grammatical_role": _norm(parent.get("grammatical_role")) if isinstance(parent, dict) else "",
            },
            "children_summary": {
                "count": len(children),
                "types": [str(child.get("type") or "") for child in children[:6]],
                "part_of_speech": [_norm(child.get("part_of_speech")) for child in children[:6]],
                "grammatical_role": [_norm(child.get("grammatical_role")) for child in children[:6]],
            },
        },
    }


def build_contract_template_training_prompt(
    payload: dict[str, Any],
    *,
    node_level: str,
    audience_level: str = "intermediate",
) -> str:
    brief = {
        "task": "rewrite_linguistic_note_template_from_contract_template",
        "prompt_template_version": CONTRACT_PROMPT_TEMPLATE_VERSION,
        "node_level": str(node_level or "").strip() or "Unknown",
        "audience_level": str(audience_level or "").strip() or "intermediate",
        "note_template_version": payload.get("note_template_version"),
        "template_id": payload.get("template_id"),
        "template_text": payload.get("template_text"),
        "allowed_slots": payload.get("allowed_slots"),
        "slot_values": payload.get("slot_values"),
        "deterministic_note": payload.get("rendered_note_text") or payload.get("fallback_note_text") or "",
        "selection": payload.get("selection"),
        "context": payload.get("note_template_input"),
    }
    return (
        "task: rewrite_linguistic_note_template_from_contract_template "
        f"payload: {json.dumps(brief, ensure_ascii=False, sort_keys=True)}"
    )


def build_contract_template_classifier_prompt(
    payload: dict[str, Any],
    *,
    node_level: str,
    task_name: str = "predict_template_id_from_contract_context",
) -> str:
    brief = {
        "task": str(task_name or "predict_template_id_from_contract_context"),
        "prompt_template_version": CONTRACT_CLASSIFIER_PROMPT_TEMPLATE_VERSION,
        "node_level": str(node_level or "").strip() or "Unknown",
        "note_template_version": payload.get("note_template_version"),
        "allowed_slots": payload.get("allowed_slots"),
        "slot_values": payload.get("slot_values"),
        "context": payload.get("note_template_input"),
    }
    return f"task: {brief['task']} payload: {json.dumps(brief, ensure_ascii=False, sort_keys=True)}"
