"""Build notation-context pairs from chapter-style handbook rows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ela_pipeline.parse.spacy_parser import load_nlp


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_QUOTE_RE = re.compile(r"[\"“'`](.{6,160}?)['\"”`]")
_EXAMPLE_LABEL_RE = re.compile(r"\([0-9]{1,3}[a-z]?\)|\b[a-z]\.")
_VERBISH_RE = re.compile(
    r"\b("
    r"is|are|was|were|be|been|being|am|"
    r"have|has|had|do|does|did|"
    r"can|could|will|would|shall|should|may|might|must|"
    r"[A-Za-z]+ed|[A-Za-z]+ing"
    r")\b",
    re.IGNORECASE,
)
_EXPLANATION_HINTS = (
    " is ",
    " are ",
    " type of ",
    " refers ",
    " can be ",
    " may be ",
    " functions as ",
    " expresses ",
    " introduces ",
    " illustrated ",
    " used ",
)
_META_PREFIXES = ("see ", "cf.", "compare ", "references", "chapter ")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_EXPLICIT_EXAMPLE_MARKERS = ("e.g.", "for example", "for instance", "example:", "examples:", "illustrated by")
_INLINE_ENUM_RE = re.compile(r"^\(?[0-9]{0,3}[a-z]?\)?\s*[a-z]\.\s+", re.IGNORECASE)
_LEADING_DIALOGUE_RE = re.compile(r"^(?:[A-Za-z]|[0-9]{1,2})\s*:\s+")
_MID_DIALOGUE_RE = re.compile(r"\b(?:[A-Za-z]|[0-9]{1,2})\s*:\s+")
_ALL_CAPS_CONTEXT_RE = re.compile(r"^[A-Z0-9 '\"/-]+$")
_INSTRUCTIONAL_PREFIX_RE = re.compile(
    r"^(?:"
    r"so you can say|we also use|we use|the structure is|study this example|listen|"
    r"for the past we use|the negative forms are|examples?|for example|for instance"
    r")\s*:?\s+",
    re.IGNORECASE,
)
_INCOMPLETE_ENDINGS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "because",
    "by",
    "concerning",
    "for",
    "from",
    "if",
    "in",
    "into",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "under",
    "with",
    "which",
}
_GRAMMAR_TAG_RE = re.compile(r"\[(?:PP|NP|VP|AdjP|AdvP|CP|DP|N′|V′)\b|(?:^|\s)(?:PP|NP|VP|AdjP|AdvP|CP|DP)(?:\s|$)")
_META_CONTEXT_TERMS = (
    "example",
    "examples",
    "called",
    "issue",
    "assumed",
    "considered",
    "refers",
    "means",
    "discussion",
    "theory",
    "grammar",
    "grammatical",
)
_DISCOURSE_START_RE = re.compile(
    r"^(?:"
    r"however|as noted|as \w+|again|consider again|in this sense|in section|in some work|"
    r"for langacker|both offer|little attention|very little|finite subordinate clauses|"
    r"animate noun phrases|the deverbal|modal meaning|habitual stative reading"
    r")\b",
    re.IGNORECASE,
)
_PASSIVE_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being|get|gets|got)\b"
    r"(?:\s+\w+){0,3}\s+\w+(?:ed|en|wn|lt|pt|nt|ft)\b",
    re.IGNORECASE,
)
_PERFECT_RE = re.compile(
    r"\b(?:have|has|had)\b(?:\s+\w+){0,2}\s+\w+(?:ed|en|wn|lt|pt|nt|ft)\b",
    re.IGNORECASE,
)
_PROGRESSIVE_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being)\b(?:\s+\w+){0,2}\s+\w+ing\b",
    re.IGNORECASE,
)
_QUESTION_TAG_RE = re.compile(
    r",\s*(?:am|is|are|was|were|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must)"
    r"(?:n't| not)?\s+(?:i|you|he|she|it|we|they|there)\?",
    re.IGNORECASE,
)
_RELATIVE_MARKER_RE = re.compile(r"\b(?:who|which|that|whose|whom|where|when)\b|Ø", re.IGNORECASE)
_WH_MARKER_RE = re.compile(r"\b(?:who|what|which|when|where|why|how|whether)\b", re.IGNORECASE)
_MODAL_RE = re.compile(
    r"\b(?:can|could|may|might|must|shall|should|will|would|ought(?:\s+to)?|need|dare)\b",
    re.IGNORECASE,
)
_PREP_PHRASE_RE = re.compile(
    r"\b(?:about|above|across|after|against|along|around|at|before|behind|below|beside|between|by|for|from|"
    r"in|inside|into|near|of|off|on|out|over|through|to|under|with)\b\s+",
    re.IGNORECASE,
)
_PREP_OBJECT_RE = re.compile(
    r"\b(?:about|above|across|after|against|along|around|at|before|behind|below|beside|between|by|for|from|"
    r"in|inside|into|near|of|off|on|out|over|through|under|with)\b\s+"
    r"(?:the|a|an|this|that|these|those|my|your|his|her|its|our|their|me|him|her|us|them|[A-Za-z][A-Za-z'-]*)\b",
    re.IGNORECASE,
)
_TO_OBJECT_RE = re.compile(
    r"\bto\b\s+(?:the|a|an|this|that|these|those|my|your|his|her|its|our|their|me|him|her|us|them|[A-Z][a-z]+)\b"
)
_TRAILING_CITATION_RE = re.compile(r"\s*\([A-Za-z][^)]*[:;][^)]*\)\.?\s*$")
_PREP_META_TERMS = {
    "work",
    "works",
    "section",
    "sections",
    "table",
    "tables",
    "example",
    "examples",
    "grammar",
    "phrase",
    "phrases",
    "preposition",
    "prepositions",
    "clause",
    "clauses",
    "subject",
    "object",
    "sentence",
    "sentences",
    "meaning",
    "meanings",
    "analysis",
}
_TOPIC_TERM_HINTS = {
    "question_tags": ("question tag", "question tags", "tag question", "tag questions"),
    "relative_clauses": ("relative clause", "relative clauses"),
    "prepositional_phrases": ("prepositional phrase", "prepositional phrases"),
    "prepositions": ("preposition", "prepositions", "prepositional"),
    "passive_voice": ("passive", "passive voice"),
    "that_clause": ("that-clause", "that clause"),
    "wh_clause": ("wh-clause", "wh clause", "wh-question", "wh question"),
    "conditional_sentences": ("conditional", "conditional sentence", "conditional sentences", "if-clause", "if clause"),
    "modal": ("modal", "modality", "modal auxiliary", "modal auxiliaries"),
    "perfect": ("perfect", "present perfect", "past perfect"),
    "progressive": ("progressive", "progressive aspect"),
}


def _norm(value: Any) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def _iter_jsonl(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _looks_explanatory_sentence(text: str, topic_key: str) -> bool:
    lowered = f" {_norm(text).lower()} "
    if not lowered.strip():
        return False
    if any(lowered.startswith(prefix) for prefix in _META_PREFIXES):
        return False
    if len(re.findall(r"[A-Za-z]{2,}", lowered)) < 6:
        return False
    topic_terms = topic_key.replace("_", " ")
    return topic_terms in lowered or any(hint in lowered for hint in _EXPLANATION_HINTS)


def _looks_explanatory_sentence_source_first(text: str) -> bool:
    lowered = f" {_norm(text).lower()} "
    if not lowered.strip():
        return False
    if any(lowered.startswith(prefix) for prefix in _META_PREFIXES):
        return False
    if len(re.findall(r"[A-Za-z]{2,}", lowered)) < 4:
        return False
    return any(hint in lowered for hint in _EXPLANATION_HINTS)


def _sentence_mentions_topic(text: str, topic_key: str) -> bool:
    lowered = _norm(text).lower()
    return any(term in lowered for term in _TOPIC_TERM_HINTS.get(topic_key, (topic_key.replace("_", " "),)))


def _looks_context_candidate(text: str) -> bool:
    text = _sanitize_context_text(text)
    if not text:
        return False
    if _ALL_CAPS_CONTEXT_RE.fullmatch(text) and len(re.findall(r"[A-Za-z']+", text)) <= 5:
        return False
    if not text[0].isalnum() and text[0] not in {'"', "'", "*"}:
        return False
    lowered = text.lower()
    if lowered.startswith("not:"):
        return False
    if any(lowered.startswith(prefix) for prefix in _META_PREFIXES):
        return False
    if _DISCOURSE_START_RE.match(text):
        return False
    if text.endswith((",", ";", ":")):
        return False
    if _GRAMMAR_TAG_RE.search(text):
        return False
    words = re.findall(r"[A-Za-z']+", text)
    if not (2 <= len(words) <= 30):
        return False
    if sum(ch.isdigit() for ch in text) > 3:
        return False
    if words and words[-1].lower() in _INCOMPLETE_ENDINGS:
        return False
    if len(words) > 6 and text[-1] not in ".?!'\"":
        return False
    if len(words) > 8 and sum(term in lowered for term in _META_CONTEXT_TERMS) >= 2:
        return False
    if _VERBISH_RE.search(text):
        return True
    return len(words) <= 8 and text[:1].isupper()


def _sanitize_context_text(text: str) -> str:
    value = _norm(str(text or "").strip(" ,;:"))
    if not value:
        return ""
    value = _LEADING_DIALOGUE_RE.sub("", value).strip()
    while True:
        updated = _INSTRUCTIONAL_PREFIX_RE.sub("", value).strip()
        if updated == value:
            break
        value = updated
    if not value:
        return ""
    mid_dialogue = list(_MID_DIALOGUE_RE.finditer(value))
    if mid_dialogue:
        tail = value[mid_dialogue[-1].end() :].strip()
        if tail and len(re.findall(r"[A-Za-z']+", tail)) >= 2:
            value = tail
    if value.lower().startswith("not:"):
        return ""
    value = _TRAILING_CITATION_RE.sub("", value).strip(" ,;:")
    return _norm(value)


def _topic_context_ok(topic_key: str, context_text: str) -> bool:
    text = _sanitize_context_text(context_text)
    lowered = text.lower()
    words = re.findall(r"[A-Za-z']+", text)
    if not text or "*" in text or lowered.startswith("not:"):
        return False
    if _DISCOURSE_START_RE.match(text):
        return False
    if topic_key == "passive_voice":
        return bool(_PASSIVE_RE.search(text) or (" by " in f" {lowered} " and re.search(r"\b\w+(?:ed|en|wn|lt|pt|nt|ft)\b", lowered)))
    if topic_key == "modal":
        return bool(_MODAL_RE.search(text))
    if topic_key == "perfect":
        return bool(_PERFECT_RE.search(text))
    if topic_key == "progressive":
        return bool(_PROGRESSIVE_RE.search(text))
    if topic_key == "question_tags":
        return bool(_QUESTION_TAG_RE.search(text))
    if topic_key == "conditional_sentences":
        return any(marker in lowered for marker in ("if ", "unless ", "provided ", "providing "))
    if topic_key == "relative_clauses":
        return bool(_RELATIVE_MARKER_RE.search(text)) and len(words) >= 4
    if topic_key == "that_clause":
        return lowered.startswith("that ") or " that " in f" {lowered} "
    if topic_key == "wh_clause":
        return bool(_WH_MARKER_RE.search(text))
    if topic_key in {"prepositions", "prepositional_phrases"}:
        if len(words) < 2:
            return False
        if any(word.lower() in _PREP_META_TERMS for word in words):
            return False
        return bool(_PREP_OBJECT_RE.search(text) or _TO_OBJECT_RE.search(text))
    return True


def _fast_sentence_split(text: str) -> list[str]:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = _SENTENCE_SPLIT_RE.split(text)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        candidate = _norm(part)
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _word_overlap(left: str, right: str) -> float:
    left_words = {word.lower() for word in re.findall(r"[A-Za-z']{2,}", left)}
    right_words = {word.lower() for word in re.findall(r"[A-Za-z']{2,}", right)}
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / max(1, min(len(left_words), len(right_words)))


def _extract_explicit_examples(text: str) -> list[str]:
    out: list[str] = []
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for raw_line in lines:
        line = _norm(raw_line)
        if not line:
            continue
        lowered = line.lower()
        marker_tail = ""
        for marker in _EXPLICIT_EXAMPLE_MARKERS:
            idx = lowered.find(marker)
            if idx >= 0:
                marker_tail = _norm(line[idx + len(marker) :].lstrip(" :"))
                break
        if marker_tail:
            out.extend(_fast_sentence_split(marker_tail))
            continue

        if _INLINE_ENUM_RE.match(line):
            stripped = _INLINE_ENUM_RE.sub("", line).strip()
            if stripped:
                out.append(_norm(stripped))
            continue

        if line.startswith("( )"):
            stripped = _norm(line[3:])
            if stripped:
                out.append(stripped)
            continue
    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _extract_contexts(text: str, nlp: Any | None) -> list[str]:
    contexts: list[str] = []
    explicit = _extract_explicit_examples(text)
    if explicit:
        contexts.extend([item for item in explicit if _looks_context_candidate(item)])

    for match in _QUOTE_RE.findall(text):
        candidate = _norm(match)
        if _looks_context_candidate(candidate):
            contexts.append(candidate)

    cleaned = _EXAMPLE_LABEL_RE.sub(" ", text)
    if not contexts:
        for line in cleaned.splitlines():
            candidate = _norm(line)
            if not candidate:
                continue
            if ":" in candidate and len(candidate) <= 180:
                tail = _norm(candidate.split(":", 1)[1])
                if _looks_context_candidate(tail):
                    contexts.append(tail)
                continue
            if len(candidate) <= 180:
                split_any = False
                for sent_text in _fast_sentence_split(candidate):
                    if _looks_context_candidate(sent_text):
                        contexts.append(sent_text)
                        split_any = True
                if not split_any and nlp is not None and len(candidate) > 180:
                    line_doc = nlp(candidate)
                    for sent in line_doc.sents:
                        sent_text = _norm(sent.text)
                        if _looks_context_candidate(sent_text):
                            contexts.append(sent_text)
                            split_any = True
                if not split_any and _looks_context_candidate(candidate):
                    contexts.append(candidate)

    if not contexts and nlp is not None:
        doc = nlp(cleaned)
        for sent in doc.sents:
            candidate = _norm(sent.text)
            if _looks_context_candidate(candidate):
                contexts.append(candidate)

    out: list[str] = []
    seen: set[str] = set()
    for item in contexts:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_handbook_note_context_pairs(
    *,
    rows_jsonl: str,
    spacy_model: str = "en_core_web_sm",
    source_first: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp: Any | None = None
    rows = list(_iter_jsonl(rows_jsonl))
    pairs: list[dict[str, Any]] = []

    for row in rows:
        text = str(row.get("text") or "")
        topic_key = str(row.get("topic_key") or "").strip()
        if not text or (not source_first and not topic_key):
            continue
        if len(text) > 2500 or len(re.findall(r"[A-Za-z]{2,}", text)) > 380:
            continue
        if source_first:
            notation_sentences = [
                sent_text
                for sent_text in _fast_sentence_split(text)
                if _looks_explanatory_sentence_source_first(sent_text)
                or (topic_key and _looks_explanatory_sentence(sent_text, topic_key))
            ]
        else:
            notation_sentences = [
                sent_text
                for sent_text in _fast_sentence_split(text)
                if _looks_explanatory_sentence(sent_text, topic_key)
            ]
        if not notation_sentences:
            if nlp is None:
                nlp = load_nlp(spacy_model)
            doc = nlp(text.replace("\n", " "))
            if source_first:
                notation_sentences = [
                    _norm(sent.text)
                    for sent in doc.sents
                    if _looks_explanatory_sentence_source_first(sent.text)
                    or (topic_key and _looks_explanatory_sentence(sent.text, topic_key))
                ]
            else:
                notation_sentences = [
                    _norm(sent.text)
                    for sent in doc.sents
                    if _looks_explanatory_sentence(sent.text, topic_key)
                ]
        if not notation_sentences:
            continue
        if source_first and not topic_key:
            ordered_notation = notation_sentences
        else:
            topic_sentences = [sent_text for sent_text in notation_sentences if topic_key and _sentence_mentions_topic(sent_text, topic_key)]
            ordered_notation = topic_sentences + [sent_text for sent_text in notation_sentences if sent_text not in topic_sentences]
        notation_text = _norm(" ".join(ordered_notation[:2]))
        contexts = _extract_contexts(text, nlp)
        for context_text in contexts:
            context_text = _sanitize_context_text(context_text)
            if not context_text:
                continue
            if notation_text.lower() == context_text.lower():
                continue
            if context_text.lower() in notation_text.lower():
                continue
            if _word_overlap(notation_text, context_text) >= 0.7 and len(context_text) > 24:
                continue
            if not source_first and not _topic_context_ok(topic_key, context_text):
                continue
            pairs.append(
                {
                    "source_path": row.get("source_path"),
                    "row_type": row.get("row_type"),
                    "entry_head": row.get("heading") or row.get("anchor") or row.get("topic_key"),
                    "heading": row.get("heading"),
                    "topic_key": topic_key,
                    "notation_text": notation_text,
                    "context_text": context_text,
                    "pair_method": "handbook_window_source_first" if source_first else "handbook_window",
                }
            )

    report = {
        "pipeline_version": "handbook_note_context_source_first_v1" if source_first else "handbook_note_context_v1",
        "rows_jsonl": str(Path(rows_jsonl).resolve()),
        "rows_seen": len(rows),
        "pairs_total": len(pairs),
        "topic_counts": {
            key: sum(1 for row in pairs if row.get("topic_key") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in pairs})
        },
    }
    return pairs, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build notation-context pairs from handbook rows.")
    parser.add_argument("--rows-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--source-first", action="store_true")
    args = parser.parse_args()

    rows, report = build_handbook_note_context_pairs(
        rows_jsonl=args.rows_jsonl,
        spacy_model=args.spacy_model,
        source_first=args.source_first,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
