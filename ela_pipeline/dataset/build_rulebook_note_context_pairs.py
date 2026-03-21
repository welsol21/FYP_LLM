"""Build notation-context pairs from rulebook-style grammar dictionary rows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ela_pipeline.parse.spacy_parser import load_nlp


_CONTROL_GLYPH_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WHITESPACE_RE = re.compile(r"\s+")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_ROMAN_PAGE_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
_EXAMPLE_MARKER_RE = re.compile(r"\b(?:e\.g\.|for example|example:|examples:)\b", re.IGNORECASE)
_ROW_EXAMPLE_MARKER_RE = re.compile(
    r"(?:\b(?:e\.g\.|for example|for instance)\b|example:|examples:|as underlined in:|as in:|compare:)",
    re.IGNORECASE,
)
_EG_CONTENT_RE = re.compile(r"\be\.g\.\s*([^)]{4,})\)?", re.IGNORECASE)
_INLINE_EXAMPLE_CUE_RE = re.compile(
    r"\b(?:for example|for instance|e\.g\.|such as|as in|as underlined in)\b[:,]?",
    re.IGNORECASE,
)
_PAREN_EXAMPLE_RE = re.compile(r"\((?:e\.g\.|i\.e\.)\s*([^)]{4,})\)", re.IGNORECASE)
_PAREN_META_TAIL_RE = re.compile(r"\s+\((?:where|in which|that is|i\.e\.|e\.g\.).*?\)\.?$", re.IGNORECASE)
_CAPITALIZED_CLAUSE_TAIL_RE = re.compile(r"\b(?:in|as in)\s+([A-Z][^.!?]*[.!?]?)$")
_TRAILING_EXPLANATORY_TAIL_RE = re.compile(r"\)\s*,\s*(?:so|and|but|which|where)\b.*$", re.IGNORECASE)
_LABEL_PREFIX_RE = re.compile(r"^(?:[A-Z][A-Z-]{2,}\s+)+")
_CROSS_REF_RE = re.compile(
    r"\b(?:see(?:\s+also|\s+further\s+under)?|compare|cf\.?|section\s+\d+|under\s+[A-Za-z-]+)\b",
    re.IGNORECASE,
)
_META_LINE_PREFIXES = (
    "see also ",
    "compare ",
    "also called ",
    "contrasted with ",
)
_META_TERMS = (
    "adjective",
    "adjectives",
    "article",
    "articles",
    "choice",
    "noun",
    "verb",
    "pronoun",
    "pronouns",
    "determiner",
    "determiners",
    "form",
    "forms",
    "phrase",
    "clause",
    "word",
    "term",
    "grammar",
    "construction",
    "subject",
    "object",
    "complement",
    "predicator",
    "language",
    "entry",
    "entries",
    "meaning",
    "category",
    "class",
    "construction",
    "analysis",
    "context",
    "referent",
    "reference",
    "topic",
    "usage",
)
_EXPLANATION_HINTS = (
    "used",
    "use ",
    "means",
    "refers",
    "indicate",
    "indicates",
    "designating",
    "designates",
    "expresses",
    "called",
    "contrasts",
    "signals",
    "functions",
    "omitted",
    "introduced",
    "denotes",
    "classiﬁcation",
    "classification",
)
_LOWERCASE_CONTEXT_STARTERS = {
    "a",
    "an",
    "the",
    "my",
    "your",
    "his",
    "her",
    "its",
    "our",
    "their",
    "this",
    "that",
    "these",
    "those",
    "some",
    "any",
    "each",
    "every",
    "another",
    "no",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "without",
    "to",
    "of",
    "as",
    "about",
    "after",
    "before",
    "between",
    "among",
    "through",
    "into",
    "onto",
    "toward",
    "towards",
    "across",
    "around",
    "within",
    "behind",
    "beneath",
    "above",
    "below",
    "near",
    "inside",
    "outside",
    "during",
    "despite",
    "who",
    "whom",
    "whose",
    "which",
    "that",
    "where",
    "when",
    "why",
    "how",
}
_BANNED_CONTEXT_STARTERS = {
    "also",
    "although",
    "because",
    "but",
    "compare",
    "comparable",
    "equivalents",
    "feature",
    "grammatically",
    "however",
    "if",
    "it",
    "kind",
    "note",
    "rather",
    "see",
    "since",
    "sometimes",
    "than",
    "then",
    "therefore",
    "thus",
    "under",
    "used",
    "whereas",
    "which",
}
_BANNED_METALANGUAGE_SENTENCE_STARTERS = {
    "a",
    "an",
    "the",
    "this",
    "these",
    "those",
    "many",
    "most",
    "such",
    "common",
    "typical",
}
_SOURCE_FIRST_RULE_TYPES = {
    "dictionary_entry",
}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PREFIX_MARK_RE = re.compile(r"^[?*]+\s*")


def _norm(value: Any) -> str:
    value = _CONTROL_GLYPH_RE.sub(" ", str(value or ""))
    return _WHITESPACE_RE.sub(" ", value.strip())


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


def _normalize_payload_lines(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in text.split("\n")]


def _line_slice(lines: list[str], start_line: int, end_line: int) -> list[str]:
    start = max(0, int(start_line) - 1)
    end = max(start, int(end_line))
    return [line for line in lines[start:end] if _norm(line)]


def _looks_meta_line(text: str) -> bool:
    lowered = _norm(text).lower()
    if not lowered:
        return True
    if _PAGE_NUMBER_RE.fullmatch(lowered) or _ROMAN_PAGE_RE.fullmatch(lowered):
        return True
    if any(lowered.startswith(prefix) for prefix in _META_LINE_PREFIXES):
        return True
    return False


def _looks_explanatory(text: str) -> bool:
    lowered = _norm(text).lower()
    if not lowered or _looks_meta_line(lowered):
        return False
    return any(hint in lowered for hint in _EXPLANATION_HINTS)


def _looks_explanatory_source_first(text: str) -> bool:
    lowered = _norm(text).lower()
    if not lowered or _looks_meta_line(lowered):
        return False
    if len(re.findall(r"[A-Za-z]{2,}", lowered)) < 4:
        return False
    return any(hint in lowered for hint in _EXPLANATION_HINTS)


def _looks_definition_like(text: str) -> bool:
    lowered = _norm(text).lower()
    if not lowered or _looks_meta_line(lowered):
        return False
    if _CROSS_REF_RE.search(lowered):
        return False
    words = re.findall(r"[A-Za-z]{2,}", lowered)
    if len(words) < 5:
        return False
    meta_hits = sum(term in lowered for term in _META_TERMS)
    return meta_hits >= 1 or words[0] in {"this", "these", "those", "a", "an", "the"}


def _looks_short_example_line(text: str) -> bool:
    text = _norm(text)
    if not text or _looks_meta_line(text):
        return False
    words = re.findall(r"[A-Za-z']+", text)
    if not (2 <= len(words) <= 14):
        return False
    lowered = text.lower()
    if sum(term in lowered for term in _META_TERMS) >= 2:
        return False
    if any(token in lowered for token in ("e.g.", "for example", "example:", "examples:")):
        return False
    if text.endswith(":"):
        return False
    return bool(text[0].isupper() or "?" in text or "!" in text)


def _looks_example_candidate(text: str, nlp: Any) -> bool:
    text = _norm(text.strip(" ,;:"))
    if not text or _looks_meta_line(text):
        return False
    if _CROSS_REF_RE.search(text):
        return False
    words = re.findall(r"[A-Za-z']+", text)
    if not (2 <= len(words) <= 20):
        return False
    lowered = text.lower()
    if sum(term in lowered for term in _META_TERMS) >= 2:
        return False
    if any(lowered.startswith(prefix) for prefix in ("for example", "example", "examples", "see ", "compare ")):
        return False
    if len(words) >= 8 and text[:1].islower():
        return False
    if text[:1].isdigit():
        return False
    doc = nlp(text)
    has_verb = any(token.pos_ in {"VERB", "AUX"} for token in doc)
    if has_verb:
        return bool(text[:1].isupper() or "?" in text or "!" in text or len(words) <= 8)
    if "?" in text or "!" in text:
        return True
    if text[:1].isupper() and not text.endswith((".", "!", "?", ")")):
        return False
    return len(words) <= 6 and (text[:1].islower() or text.endswith((".", "!", "?", ")")))


def _strip_entry_head_prefix(text: str, entry_head: str) -> str:
    text = _norm(text)
    entry_head = _norm(entry_head)
    if not text or not entry_head:
        return text
    if text == entry_head:
        return ""
    lowered = text.lower()
    head_lower = entry_head.lower()
    if lowered.startswith(f"{head_lower} "):
        return _norm(text[len(entry_head) :])
    return text


def _looks_inline_headword(line: str) -> bool:
    line = _norm(line)
    if not line or line.endswith((".", "?", "!", ";", ":")):
        return False
    words = line.split()
    if not (1 <= len(words) <= 3):
        return False
    if any(ch.isdigit() for ch in line):
        return False
    if any(token in line.lower() for token in ("e.g.", "for example", "example:", "examples:")):
        return False
    return True


def _split_explicit_tail_into_examples(tail: str, nlp: Any) -> list[str]:
    tail = _norm(tail.strip(" :-"))
    if not tail:
        return []
    doc = nlp(tail)
    items = []
    for sent in doc.sents:
        candidate = _norm(sent.text)
        if _looks_example_candidate(candidate, nlp):
            items.append(candidate)
    if not items and _looks_example_candidate(tail, nlp):
        items.append(tail)
    return list(dict.fromkeys(items))


def _fast_sentence_split(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in _SENTENCE_SPLIT_RE.split(str(text or "").replace("\n", " ")):
        candidate = _norm(part)
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _looks_source_first_context(text: str, nlp: Any) -> bool:
    text = _norm(text.strip(" ,;:"))
    text = _PREFIX_MARK_RE.sub("", text)
    if not text or _looks_meta_line(text):
        return False
    if _CROSS_REF_RE.search(text):
        return False
    if re.match(r"^[A-Z][A-Z-]{2,}\b", text):
        return False
    if text[:1] in {",", ";", ":", ")", "]"} or text.startswith("("):
        return False
    if text[:1].isdigit():
        return False
    words = re.findall(r"[A-Za-z']+", text)
    if not (2 <= len(words) <= 24):
        return False
    lowered = text.lower()
    if lowered.startswith(("native speakers ", "in this sense", "any hint that", "its four major", "characters in dickens ")):
        return False
    if "grammaticality is a feature" in lowered:
        return False
    if words[-1].lower() in {"a", "an", "and", "as", "at", "by", "for", "from", "if", "in", "of", "on", "or", "than", "that", "the", "to", "with"}:
        return False
    first = words[0].lower()
    if first in _BANNED_CONTEXT_STARTERS:
        return False
    if text[:1].islower() and first not in _LOWERCASE_CONTEXT_STARTERS:
        return False
    if text[:1].islower() and ":" in text:
        return False
    meta_hits = sum(term in lowered for term in _META_TERMS)
    doc = nlp(text)
    has_verb = any(token.pos_ in {"VERB", "AUX"} for token in doc)
    has_subject = any(token.dep_ in {"nsubj", "nsubjpass", "expl", "csubj"} for token in doc)
    if has_verb and has_subject:
        if text[:1].islower():
            if first in {"a", "an", "the", "this", "these", "those"} and meta_hits >= 1:
                return False
            return first in _LOWERCASE_CONTEXT_STARTERS
        if first in {"this", "these", "those"}:
            return False
        if first in _BANNED_METALANGUAGE_SENTENCE_STARTERS and meta_hits >= 1:
            return False
        if meta_hits >= 2 and first not in {"i", "we", "he", "she", "they", "you", "there"}:
            return False
        return True
    if "?" in text or "!" in text:
        return True
    return first in _LOWERCASE_CONTEXT_STARTERS and len(words) <= 10 and meta_hits == 0


def _looks_meta_followup(text: str) -> bool:
    text = _norm(text)
    text = _PREFIX_MARK_RE.sub("", text)
    if not text:
        return False
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return False
    first = words[0].lower()
    lowered = text.lower()
    if first in {"as", "this", "these", "those", "the", "a", "an", "modern", "linguists", "adjuncts", "acceptability", "in", "native", "characters"}:
        return True
    if lowered.startswith(("in this sense", "native speakers", "any hint that", "its four major", "characters in dickens ")):
        return True
    if any(marker in lowered for marker in (" are generally ", " are normally ", " can be ", " is another term ", " are therefore ")):
        return sum(term in lowered for term in _META_TERMS) >= 1
    return any(hint in lowered for hint in _EXPLANATION_HINTS) or sum(term in lowered for term in _META_TERMS) >= 2


def _normalize_example_candidate(text: str) -> str:
    text = _PREFIX_MARK_RE.sub("", _norm(text.strip(" ,;:")))
    if not text:
        return ""
    text = _LABEL_PREFIX_RE.sub("", text)
    lowered = text.lower()
    eg_match = _EG_CONTENT_RE.search(text)
    if eg_match:
        content = _norm(eg_match.group(1).strip(" ,;:"))
        if content:
            text = content
            lowered = text.lower()
    paren_match = _PAREN_EXAMPLE_RE.search(text)
    if paren_match:
        text = _norm(paren_match.group(1))
        lowered = text.lower()
    cue_match = _INLINE_EXAMPLE_CUE_RE.search(text)
    if cue_match:
        tail = _norm(text[cue_match.end() :].strip(" ,;:"))
        if tail:
            text = tail
            lowered = text.lower()
    meta_hits = sum(term in lowered for term in _META_TERMS)
    if text[:1].islower() or meta_hits >= 1:
        clause_match = _CAPITALIZED_CLAUSE_TAIL_RE.search(text)
        if clause_match:
            tail = _norm(clause_match.group(1))
            if tail:
                text = tail
    text = _PAREN_META_TAIL_RE.sub("", text)
    text = _TRAILING_EXPLANATORY_TAIL_RE.sub("", text).rstrip(" )")
    return _norm(text)


def _notation_from_buffer(buffer: list[str]) -> str:
    kept = [_norm(line) for line in buffer if _norm(line) and not _looks_meta_line(line)]
    return _norm(" ".join(kept[-3:]))


def _prune_contained_contexts(contexts: list[str]) -> list[str]:
    out: list[str] = []
    for item in sorted((_norm(text) for text in contexts if _norm(text)), key=len, reverse=True):
        lower = item.lower()
        if any(lower != kept.lower() and lower in kept.lower() for kept in out):
            continue
        out.append(item)
    return out


def _extract_source_first_examples(lines: list[str], entry_head: str, nlp: Any) -> list[str]:
    out: list[str] = []
    for raw_line in lines:
        line = _strip_entry_head_prefix(raw_line, entry_head)
        if not line or _looks_meta_line(line):
            continue
        if line.endswith((",", ";", ":")):
            continue
        marker = _EXAMPLE_MARKER_RE.search(line)
        if marker:
            tail = _norm(line[marker.end() :])
            for item in _split_explicit_tail_into_examples(tail, nlp):
                normalized = _normalize_example_candidate(item)
                if _looks_source_first_context(normalized, nlp):
                    out.append(normalized)
            continue
        normalized_line = _normalize_example_candidate(line)
        if _looks_source_first_context(normalized_line, nlp):
            out.append(normalized_line)
            continue
        collected_in_line = False
        for sent in _fast_sentence_split(line):
            if sent.endswith((",", ";", ":")):
                continue
            normalized_sent = _normalize_example_candidate(sent)
            if collected_in_line and _looks_meta_followup(normalized_sent):
                break
            if _looks_source_first_context(normalized_sent, nlp):
                out.append(normalized_sent)
                collected_in_line = True
    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _iter_example_zone_candidates(text: str) -> list[str]:
    text = _norm(text)
    if not text:
        return []
    normalized = re.sub(r"\s([?*])\s+(?=[A-Z])", r" || \1 ", text)
    normalized = re.sub(r"([:;])\s+(?=[?*A-Z])", r"\1 || ", normalized)
    out: list[str] = []
    for chunk in normalized.split("||"):
        chunk = _norm(chunk)
        if not chunk:
            continue
        out.extend(_fast_sentence_split(chunk))
    return [item for item in out if item]


def _extract_source_first_examples_from_text(text: str, entry_head: str, nlp: Any) -> list[str]:
    text = _strip_entry_head_prefix(_norm(text), entry_head)
    if not text:
        return []
    markers = list(_ROW_EXAMPLE_MARKER_RE.finditer(text))
    if not markers:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for idx, match in enumerate(markers):
        tail_start = match.end()
        tail_end = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
        tail = _norm(text[tail_start:tail_end].strip(" :-"))
        if not tail:
            continue
        collecting = False
        for candidate in _iter_example_zone_candidates(tail):
            cleaned = _normalize_example_candidate(candidate)
            if not cleaned:
                continue
            if collecting and _looks_meta_followup(cleaned):
                break
            if _looks_source_first_context(cleaned, nlp):
                key = cleaned.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(cleaned)
                collecting = True
    return out


def _extract_pairs_from_row_source_first(row: dict[str, Any], payload_lines: list[str], nlp: Any) -> list[dict[str, Any]]:
    row_type = str(row.get("row_type") or "")
    if row_type not in _SOURCE_FIRST_RULE_TYPES:
        return []
    lines = _line_slice(payload_lines, int(row.get("line_start") or 0), int(row.get("line_end") or 0))
    if not lines:
        return []
    entry_head = _norm(row.get("entry_head") or row.get("heading"))
    row_text = _strip_entry_head_prefix(_norm(row.get("text") or ""), entry_head)
    notation_sentences: list[str] = []
    first_marker = _ROW_EXAMPLE_MARKER_RE.search(row_text or "")
    notation_source = _norm(row_text[: first_marker.start()]) if first_marker else row_text
    if notation_source:
        for sent in _fast_sentence_split(notation_source):
            if _looks_explanatory_source_first(sent):
                notation_sentences.append(sent)
    if not notation_sentences and notation_source:
        for sent in _fast_sentence_split(notation_source):
            if _looks_definition_like(sent):
                notation_sentences.append(sent)
            if len(notation_sentences) >= 2:
                break
    if not notation_sentences:
        for raw_line in lines:
            line = _strip_entry_head_prefix(raw_line, entry_head)
            if not line:
                continue
            doc = nlp(line)
            for sent in doc.sents:
                sent_text = _norm(sent.text)
                if _looks_explanatory_source_first(sent_text):
                    notation_sentences.append(sent_text)
    if not notation_sentences:
        return []
    notation_text = _norm(" ".join(list(dict.fromkeys(notation_sentences))[:2]))
    if not notation_text:
        return []
    pairs: list[dict[str, Any]] = []
    explicit_contexts = _extract_source_first_examples_from_text(str(row.get("text") or ""), entry_head, nlp)
    line_contexts = _extract_source_first_examples(lines, entry_head, nlp)
    contexts: list[str] = []
    seen_contexts: set[str] = set()
    for context_text in explicit_contexts + line_contexts:
        key = _norm(context_text).lower()
        if not key or key in seen_contexts:
            continue
        seen_contexts.add(key)
        contexts.append(_norm(context_text))
    contexts = _prune_contained_contexts(contexts)
    for context_text in contexts:
        if not context_text:
            continue
        if notation_text.lower() == context_text.lower():
            continue
        if context_text.lower() in notation_text.lower():
            continue
        pairs.append(
            {
                "source_path": row.get("source_path"),
                "row_type": row_type,
                "entry_head": row.get("entry_head") or row.get("heading"),
                "heading": row.get("heading"),
                "notation_text": notation_text,
                "context_text": context_text,
                "pair_method": "rulebook_source_first",
            }
        )
    return pairs


def _extract_pairs_from_row(row: dict[str, Any], payload_lines: list[str], nlp: Any) -> list[dict[str, Any]]:
    row_type = str(row.get("row_type") or "")
    if row_type not in {"dictionary_entry", "notational_rule"}:
        return []
    lines = _line_slice(payload_lines, int(row.get("line_start") or 0), int(row.get("line_end") or 0))
    if not lines:
        return []

    pairs: list[dict[str, Any]] = []
    notation_buffer: list[str] = []
    entry_head = _norm(row.get("entry_head") or row.get("heading"))
    idx = 0
    while idx < len(lines):
        line = _strip_entry_head_prefix(lines[idx], entry_head)
        if not line:
            idx += 1
            continue
        if _looks_inline_headword(line):
            notation_buffer = []
            idx += 1
            continue
        marker = _EXAMPLE_MARKER_RE.search(line)
        if marker:
            before = _norm(line[: marker.start()])
            after = _norm(line[marker.end() :])
            notation = _notation_from_buffer(notation_buffer + ([before] if before else []))
            examples = _split_explicit_tail_into_examples(after, nlp)
            j = idx + 1
            while j < len(lines):
                candidate = _strip_entry_head_prefix(lines[j], entry_head)
                if not _looks_example_candidate(candidate, nlp):
                    break
                examples.append(_norm(candidate))
                j += 1
            for context_text in list(dict.fromkeys([item for item in examples if item])):
                if notation and context_text:
                    pairs.append(
                        {
                            "source_path": row.get("source_path"),
                            "row_type": row_type,
                            "entry_head": row.get("entry_head") or row.get("heading"),
                            "heading": row.get("heading"),
                            "notation_text": notation,
                            "context_text": context_text,
                            "pair_method": "explicit_marker",
                        }
                    )
            if before:
                notation_buffer.append(before)
            idx = j
            continue

        if _looks_explanatory(line):
            notation_buffer.append(line)
            j = idx + 1
            block_examples: list[str] = []
            while j < len(lines):
                candidate = _strip_entry_head_prefix(lines[j], entry_head)
                if not _looks_example_candidate(candidate, nlp):
                    break
                block_examples.append(_norm(candidate))
                j += 1
            if block_examples:
                notation = _notation_from_buffer(notation_buffer)
                for context_text in block_examples:
                    if notation and context_text:
                        pairs.append(
                            {
                                "source_path": row.get("source_path"),
                                "row_type": row_type,
                                "entry_head": row.get("entry_head") or row.get("heading"),
                                "heading": row.get("heading"),
                                "notation_text": notation,
                                "context_text": context_text,
                                "pair_method": "line_block",
                            }
                        )
                idx = j
                continue
        elif not _looks_meta_line(line):
            notation_buffer.append(line)
        idx += 1
    return pairs


def build_rulebook_note_context_pairs(
    *,
    rulebook_jsonl: str,
    payload_txt: str,
    spacy_model: str = "en_core_web_sm",
    source_first: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp(spacy_model)
    payload_lines = _normalize_payload_lines(payload_txt)
    rows = list(_iter_jsonl(rulebook_jsonl))

    pairs: list[dict[str, Any]] = []
    for row in rows:
        if source_first:
            pairs.extend(_extract_pairs_from_row_source_first(row, payload_lines, nlp))
        else:
            pairs.extend(_extract_pairs_from_row(row, payload_lines, nlp))

    report = {
        "pipeline_version": "rulebook_note_context_source_first_v1" if source_first else "rulebook_note_context_v1",
        "rulebook_jsonl": str(Path(rulebook_jsonl).resolve()),
        "payload_txt": str(Path(payload_txt).resolve()),
        "rows_seen": len(rows),
        "pairs_total": len(pairs),
        "explicit_marker_pairs": sum(1 for row in pairs if row.get("pair_method") == "explicit_marker"),
        "line_block_pairs": sum(1 for row in pairs if row.get("pair_method") == "line_block"),
        "source_first_pairs": sum(1 for row in pairs if row.get("pair_method") == "rulebook_source_first"),
        "distinct_entry_heads": len({str(row.get("entry_head") or "").strip().lower() for row in pairs if str(row.get("entry_head") or "").strip()}),
    }
    return pairs, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build notation-context pairs from rulebook rows.")
    parser.add_argument("--rulebook-jsonl", required=True)
    parser.add_argument("--payload-txt", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--source-first", action="store_true")
    args = parser.parse_args()

    rows, report = build_rulebook_note_context_pairs(
        rulebook_jsonl=args.rulebook_jsonl,
        payload_txt=args.payload_txt,
        spacy_model=args.spacy_model,
        source_first=args.source_first,
    )
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
