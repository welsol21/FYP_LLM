"""Sentence-side placeholder templating from contract spaCy nodes."""

from __future__ import annotations

import re
from typing import Any

from ela_pipeline.dataset.note_patterning import normalize_placeholder_name


WS_RE = re.compile(r"\s+")
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")

SUBJECT_DEPS = {"nsubj", "nsubjpass", "csubj", "csubjpass"}
OBJECT_DEPS = {"obj", "dobj", "iobj", "pobj", "attr", "acomp", "oprd"}
AUX_DEPS = {"aux", "auxpass"}
PREP_DEPS = {"prep", "pcomp"}
NEG_DEPS = {"neg"}
DET_DEPS = {"det"}
MODAL_WORDS = {
    "can",
    "could",
    "may",
    "might",
    "must",
    "shall",
    "should",
    "will",
    "would",
}

CLAUSE_MARKERS: list[tuple[str, str]] = [
    ("even if", "EVEN_IF_CONDITION"),
    ("only if", "NECESSARY_CONDITION"),
    ("provided that", "RESTRICTIVE_CONDITION"),
    ("provided", "RESTRICTIVE_CONDITION"),
    ("providing", "RESTRICTIVE_CONDITION"),
    ("as long as", "RESTRICTIVE_CONDITION"),
    ("unless", "UNLESS_CONDITION"),
    ("if", "IF_CLAUSE"),
    ("when", "TIME_CLAUSE"),
    ("while", "TIME_CLAUSE"),
    ("before", "TIME_CLAUSE"),
    ("after", "TIME_CLAUSE"),
    ("because", "REASON_CLAUSE"),
    ("since", "REASON_CLAUSE"),
    ("although", "CONCESSION_CLAUSE"),
    ("though", "CONCESSION_CLAUSE"),
    ("that", "THAT_CLAUSE"),
    ("what", "WH_CLAUSE"),
    ("who", "WH_CLAUSE"),
    ("whom", "WH_CLAUSE"),
    ("whose", "WH_CLAUSE"),
    ("which", "WH_CLAUSE"),
    ("where", "WH_CLAUSE"),
    ("why", "WH_CLAUSE"),
    ("how", "WH_CLAUSE"),
]


def _norm(value: Any) -> str:
    return WS_RE.sub(" ", str(value or "").strip())


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _children_sorted(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = [child for child in (node.get("linguistic_elements") or []) if isinstance(child, dict)]
    return sorted(
        children,
        key=lambda item: (
            int((item.get("source_span") or {}).get("start", 0)),
            int((item.get("source_span") or {}).get("end", 0)),
            0 if str(item.get("type") or "").strip() == "Word" else 1,
        ),
    )


def _descendant_words(node: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(cur: dict[str, Any]) -> None:
        if str(cur.get("type") or "").strip() == "Word":
            out.append(cur)
        for child in _children_sorted(cur):
            walk(child)

    walk(node)
    out.sort(key=lambda item: int((item.get("source_span") or {}).get("start", 0)))
    return out


def extract_placeholders(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in PLACEHOLDER_RE.findall(text or ""):
        canonical = normalize_placeholder_name(raw)
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def _sentence_family(node: dict[str, Any]) -> str | None:
    text = _norm_lower(node.get("content"))
    if not text:
        return None
    if text.startswith("even if "):
        return "EVEN_IF_CONDITION"
    if text.startswith("only if "):
        return "NECESSARY_CONDITION"
    if text.startswith("provided that ") or text.startswith("provided ") or text.startswith("providing ") or text.startswith("as long as "):
        return "RESTRICTIVE_CONDITION"
    if text.startswith("unless "):
        return "UNLESS_CONDITION"
    if text.startswith("if "):
        return "IF_CLAUSE"
    if text.startswith("when ") or text.startswith("while ") or text.startswith("before ") or text.startswith("after "):
        return "TIME_CLAUSE"
    if text.startswith("because ") or text.startswith("since ") or text.startswith("as "):
        return "REASON_CLAUSE"
    if text.startswith("although ") or text.startswith("though "):
        return "CONCESSION_CLAUSE"
    if text.startswith(("what ", "who ", "whom ", "whose ", "which ", "where ", "why ", "how ")):
        return "WH_CLAUSE"
    if text.startswith("that "):
        return "THAT_CLAUSE"
    if text.startswith("there "):
        return "EXISTENTIAL_THERE"
    return None


def _phrase_placeholder(node: dict[str, Any]) -> str | None:
    pos = _norm_lower(node.get("part_of_speech"))
    role = _norm_lower(node.get("grammatical_role"))
    content = _norm_lower(node.get("content"))

    family = _sentence_family(node)
    if family:
        return family

    if pos == "noun phrase":
        if role == "subject":
            return "SUBJECT"
        if role == "object":
            return "OBJECT"
        return "NOUN_PHRASE"
    if pos == "prepositional phrase":
        return "PREPOSITIONAL_PHRASE"
    if pos == "adjective phrase":
        return "ADJECTIVE_PHRASE"
    if pos == "adverb phrase":
        return "ADVERB_PHRASE"

    if pos == "verb phrase":
        if "have" in content and any(word.get("content", "").lower() in MODAL_WORDS for word in _descendant_words(node)):
            return "MODAL_PERFECT"
        if "been" in content and "by" in content:
            return "PASSIVE_VOICE"
        return None

    return None


def _word_placeholder(node: dict[str, Any], parent: dict[str, Any] | None) -> str | None:
    content = _norm_lower(node.get("content"))
    pos = _norm_lower(node.get("part_of_speech"))
    dep = _norm_lower(node.get("dep_label"))
    role = _norm_lower(node.get("grammatical_role"))

    if dep in NEG_DEPS or content in {"not", "n't"}:
        return "NEGATION"
    if dep in PREP_DEPS or pos == "preposition":
        return "PREPOSITION"
    if pos == "particle" or content == "to":
        return "PARTICLE"
    if dep in AUX_DEPS or pos == "auxiliary verb":
        if content in MODAL_WORDS:
            return "MODAL"
        if content in {"be", "been", "being", "am", "is", "are", "was", "were"}:
            return "AUXILIARY"
        if content == "have":
            return "AUXILIARY"
        return "AUXILIARY"
    if dep in DET_DEPS or pos == "article" or content in {"a", "an", "the"}:
        return "DETERMINER"
    if dep in SUBJECT_DEPS:
        return "SUBJECT"
    if dep in OBJECT_DEPS:
        return "OBJECT"

    if dep == "mark":
        for marker, placeholder in CLAUSE_MARKERS:
            if content == marker or content.startswith(marker + " "):
                return placeholder
        if content in {"if", "unless", "when", "while", "before", "after", "because", "since", "although", "though", "that"}:
            return "IF_CLAUSE"
        if content in {"what", "who", "whom", "whose", "which", "where", "why", "how"}:
            return "WH_CLAUSE"

    if pos == "pronoun":
        if role == "subject":
            return "SUBJECT"
        if role == "object":
            return "OBJECT"
        return "PRONOUN"

    if pos == "noun" or pos == "proper noun":
        if role == "subject":
            return "SUBJECT"
        if role == "object":
            return "OBJECT"
        return "NOUN_PHRASE"
    if pos == "verb":
        if content in MODAL_WORDS:
            return "MODAL"
        feats = node.get("features") or {}
        verb_form = _norm_lower(feats.get("verb_form"))
        tense_feature = _norm_lower(feats.get("tense_feature"))
        if verb_form == "part" and tense_feature == "past":
            return "PAST_PARTICIPLE"
        if verb_form == "part" and tense_feature == "pres":
            return "PRESENT_PARTICIPLE"
        if verb_form == "inf":
            return "BASE_VERB"
        if role in {"predicate", "root"}:
            return "BASE_VERB"
        return "BASE_VERB"
    if pos == "adverb":
        return "ADVERB"
    if parent is not None:
        parent_pos = _norm_lower(parent.get("part_of_speech"))
        if parent_pos == "verb phrase" and content in {"going", "gone"}:
            return "BASE_VERB"

    return None


def _render_node(node: dict[str, Any], *, parent: dict[str, Any] | None, seen: set[tuple]) -> tuple[str, list[str]]:
    node_type = _norm_lower(node.get("type"))
    span = node.get("source_span") or {}
    key = (
        node_type,
        int(span.get("start", -1)) if isinstance(span.get("start"), int) else -1,
        int(span.get("end", -1)) if isinstance(span.get("end"), int) else -1,
        _norm_lower(node.get("content")),
        _norm_lower(node.get("part_of_speech")),
    )
    if key in seen:
        return "", []
    if node.get("ref_node_id"):
        seen.add(key)
        return "", []
    seen.add(key)

    if node_type == "word":
        placeholder = _word_placeholder(node, parent)
        if placeholder:
            return f"{{{{{placeholder}}}}}", [placeholder]
        content = _norm(node.get("content"))
        return content, []

    if node_type == "phrase":
        placeholder = _phrase_placeholder(node)
        if placeholder and placeholder not in {"MODAL_PERFECT", "PASSIVE_VOICE"}:
            return f"{{{{{placeholder}}}}}", [placeholder]
        children = _children_sorted(node)
        parts: list[str] = []
        placeholders: list[str] = []
        for child in children:
            rendered, child_placeholders = _render_node(child, parent=node, seen=seen)
            if rendered:
                parts.append(rendered)
            placeholders.extend(child_placeholders)
        text = _norm(" ".join(parts))
        if placeholder in {"MODAL_PERFECT", "PASSIVE_VOICE"}:
            if placeholder == "MODAL_PERFECT":
                return "{{MODAL}} have {{PAST_PARTICIPLE}}", ["MODAL", "PAST_PARTICIPLE"]
            if placeholder == "PASSIVE_VOICE":
                return "{{AUXILIARY}} {{PAST_PARTICIPLE}}", ["AUXILIARY", "PAST_PARTICIPLE"]
        return text, placeholders

    if node_type == "sentence":
        family = _sentence_family(node)
        if family in {"IF_CLAUSE", "UNLESS_CONDITION", "EVEN_IF_CONDITION", "NECESSARY_CONDITION", "RESTRICTIVE_CONDITION"}:
            text = _norm_lower(node.get("content"))
            result_placeholder = "WILL_RESULT_CLAUSE" if " will " in f" {text} " else "MODAL_RESULT_CLAUSE"
            if any(aux in text for aux in (" must ", " should ", " could ", " might ", " may ", " can ")):
                result_placeholder = "MODAL_RESULT_CLAUSE"
            if text.startswith("only if "):
                result_placeholder = "INVERTED_RESULT_CLAUSE" if " will " in text or " can " in text else "MAIN_RESULT_CLAUSE"
            if text.startswith("unless "):
                result_placeholder = "MAIN_RESULT_CLAUSE"
            if text.startswith("even if "):
                result_placeholder = "UNCHANGED_RESULT_CLAUSE"
            if text.startswith("provided") or text.startswith("providing") or text.startswith("as long as"):
                result_placeholder = "MAIN_RESULT_CLAUSE"
            return f"{{{{{family}}}}}, {{{{{result_placeholder}}}}}", [family, result_placeholder]
        if family in {"WH_CLAUSE", "THAT_CLAUSE", "EXISTENTIAL_THERE", "TIME_CLAUSE", "REASON_CLAUSE", "CONCESSION_CLAUSE"}:
            children = _children_sorted(node)
            parts: list[str] = []
            placeholders: list[str] = [family]
            for child in children:
                rendered, child_placeholders = _render_node(child, parent=node, seen=seen)
                if rendered:
                    parts.append(rendered)
                placeholders.extend(child_placeholders)
            rendered = _norm(" ".join(parts))
            if rendered:
                return f"{{{{{family}}}}} {rendered}", placeholders
            return f"{{{{{family}}}}}", placeholders

        children = _children_sorted(node)
        parts: list[str] = []
        placeholders: list[str] = []
        for child in children:
            rendered, child_placeholders = _render_node(child, parent=node, seen=seen)
            if rendered:
                parts.append(rendered)
            placeholders.extend(child_placeholders)
        return _norm(" ".join(parts)), placeholders

    children = _children_sorted(node)
    parts: list[str] = []
    placeholders: list[str] = []
    for child in children:
        rendered, child_placeholders = _render_node(child, parent=node, seen=seen)
        if rendered:
            parts.append(rendered)
        placeholders.extend(child_placeholders)
    return _norm(" ".join(parts)), placeholders


def build_sentence_input_pattern(sentence_node: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    seen: set[tuple] = set()
    template, placeholders = _render_node(sentence_node, parent=None, seen=seen)
    template = _norm(template)
    placeholder_set = list(dict.fromkeys(placeholders))
    slot_values = {name: name.lower().replace("_", " ") for name in placeholder_set if name}
    if not template:
        template = "{{SENTENCE}}"
        placeholder_set = ["SENTENCE"]
        slot_values = {"SENTENCE": _norm(sentence_node.get("content")) or "sentence"}
        source = "fallback_sentence"
    else:
        source = "node_template"
    return template, slot_values, source
