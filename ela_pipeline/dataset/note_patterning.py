from __future__ import annotations

import re
from typing import Any


QUOTE_RE = re.compile(r'["“](.*?)["”]')
PLACEHOLDER_ALIAS_MAP = {
    "NP": "NOUN_PHRASE",
    "NOUN_PHRASE": "NOUN_PHRASE",
    "VP": "VERB_PHRASE",
    "VERB_PHRASE": "VERB_PHRASE",
    "PP": "PREPOSITIONAL_PHRASE",
    "PREPOSITIONAL_PHRASE": "PREPOSITIONAL_PHRASE",
    "WH CLAUSE": "WH_CLAUSE",
    "WH-CLAUSE": "WH_CLAUSE",
    "WH_CLAUSE": "WH_CLAUSE",
    "IF CLAUSE": "IF_CLAUSE",
    "IF-CLAUSE": "IF_CLAUSE",
    "IF_CLAUSE": "IF_CLAUSE",
    "THAT CLAUSE": "THAT_CLAUSE",
    "THAT-CLAUSE": "THAT_CLAUSE",
    "THAT_CLAUSE": "THAT_CLAUSE",
    "DO SUPPORT": "DO_SUPPORT",
    "DO-SUPPORT": "DO_SUPPORT",
    "DO_SUPPORT": "DO_SUPPORT",
    "YES NO QUESTIONS": "YES_NO_QUESTIONS",
    "YES-NO QUESTIONS": "YES_NO_QUESTIONS",
    "YES_NO_QUESTIONS": "YES_NO_QUESTIONS",
    "QUESTION TAG": "QUESTION_TAG",
    "QUESTION TAGS": "QUESTION_TAGS",
    "QUESTION_TAG": "QUESTION_TAG",
    "QUESTION_TAGS": "QUESTION_TAGS",
    "RELATIVE CLAUSE": "RELATIVE_CLAUSE",
    "RELATIVE-CLAUSE": "RELATIVE_CLAUSE",
    "RELATIVE_CLAUSE": "RELATIVE_CLAUSE",
    "CONDITIONAL CLAUSE": "CONDITIONAL_CLAUSE",
    "CONDITIONAL-CLAUSE": "CONDITIONAL_CLAUSE",
    "CONDITIONAL_CLAUSE": "CONDITIONAL_CLAUSE",
    "AUXILIARY": "AUXILIARY",
    "MODAL": "MODAL",
    "OBJECT": "OBJECT",
    "SUBJECT": "SUBJECT",
    "PREPOSITION": "PREPOSITION",
    "NOUN CLAUSE": "NOUN_CLAUSE",
    "NOUN-CLAUSE": "NOUN_CLAUSE",
    "NOUN_CLAUSE": "NOUN_CLAUSE",
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_placeholder_name(name: str) -> str:
    text = _norm(name).upper().replace("-", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    canonical = PLACEHOLDER_ALIAS_MAP.get(text)
    if canonical:
        return canonical
    return text.replace(" ", "_")


def build_note_pattern(
    *,
    note_text: str,
    sentence_text: str = "",
    slot_template_text: str = "",
    slot_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rendered = _norm(note_text)
    template = _norm(slot_template_text)
    normalized_slots = {
        normalize_placeholder_name(str(key)): _norm(value)
        for key, value in (slot_values or {}).items()
        if normalize_placeholder_name(str(key)) and _norm(value)
    }

    if "{{" in template and "}}" in template:
        for raw, canonical in PLACEHOLDER_ALIAS_MAP.items():
            template = re.sub(r"\{\{\s*" + re.escape(raw) + r"\s*\}\}", "{{" + canonical + "}}", template, flags=re.IGNORECASE)
        return {
            "pattern_text": template,
            "slot_values": normalized_slots,
            "pattern_source": "slot_template",
        }

    pattern_text = rendered
    derived_slots: dict[str, str] = {}
    seen_fragments: set[str] = set()
    sentence_lower = _norm(sentence_text).lower()
    slot_index = 1

    for fragment in [frag.strip() for frag in QUOTE_RE.findall(rendered) if frag.strip()]:
        fragment_lower = fragment.lower()
        if len(fragment) <= 1 or fragment_lower in seen_fragments:
            continue
        if sentence_lower and fragment_lower not in sentence_lower:
            continue
        slot_name = f"SPAN_{slot_index}"
        replacement = "{{" + slot_name + "}}"
        pattern_text = pattern_text.replace(f'"{fragment}"', replacement)
        pattern_text = pattern_text.replace(f'“{fragment}”', replacement)
        derived_slots[slot_name] = fragment
        seen_fragments.add(fragment_lower)
        slot_index += 1

    if derived_slots:
        return {
            "pattern_text": pattern_text,
            "slot_values": derived_slots,
            "pattern_source": "quoted_fragment",
        }

    return {
        "pattern_text": rendered,
        "slot_values": {},
        "pattern_source": "verbatim",
    }
