"""Build a clean subset from raw source-first note/context pairs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


_BAD_TOKEN_RE = re.compile(
    r"\b(?:workes|finishs|brushs|watchs|washs|teachs|playes|gos|acomputer|youa|nota|amn't|spm|ipm)\b",
    re.IGNORECASE,
)
_BAD_CHAR_RE = re.compile(r"[|#~]")
_NEG_AUX_INFLECTED_RE = re.compile(
    r"\b(?:does not|doesn't|do not|don't|did not|didn't)\s+[A-Za-z]+(?:s|es|ed)\b",
    re.IGNORECASE,
)
_BE_AGREEMENT_RE = re.compile(
    r"\b(?:they|we|you)\s+isn['’]?t\b|\b(?:he|she|it)\s+aren['’]?t\b|\bi\s+amn['’]?t\b",
    re.IGNORECASE,
)
_DO_AGREEMENT_RE = re.compile(
    r"\b(?:they|we|you|i)\s+doesn['’]?t\b|\b(?:he|she|it)\s+don['’]?t\b",
    re.IGNORECASE,
)
_NAME_DONT_RE = re.compile(r"^(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+don['’]?t\b")
_NP_DONT_RE = re.compile(r"^(?:My|His|Her|The|That|This)\s+[A-Za-z]+\s+[A-Za-z]+\s+don['’]?t\b")
_QUESTION_START_RE = re.compile(
    r"^(?:am|are|is|was|were|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must|"
    r"who|what|when|where|why|how)\b",
    re.IGNORECASE,
)
_TRAILING_META_RE = re.compile(r"(?:i\.e\.|e\.g\.)$", re.IGNORECASE)
_LEADING_META_RE = re.compile(r"^(?:compare|see|for example|example|examples)\b", re.IGNORECASE)
_CROSS_REF_RE = re.compile(r"\b(?:see(?:\s+also|\s+further\s+under)?|compare|cf\.?|section\s+\d+)\b", re.IGNORECASE)
_LEADING_LABEL_RE = re.compile(r"^[A-Z][A-Z-]{2,}\b")
_LOW_INFO_RULEBOOK_RE = re.compile(
    r"^(?:in this|to use|therefore prefaced by|grammatical rules of english|a glossary of english grammar)\b",
    re.IGNORECASE,
)
_META_FOLLOWUP_RE = re.compile(
    r"\b(?:is|are|was|were)\s+(?:generally|normally|typically|therefore)\b",
    re.IGNORECASE,
)
_META_SOURCE_FIRST_RE = re.compile(
    r"^(?:native speakers\b|in this sense\b|any hint that\b|its four major\b|characters in dickens\b|"
    r"a properly constructed,\s+grammatically correct sentence\b)",
    re.IGNORECASE,
)
_EXAMPLE_META_RE = re.compile(
    r"^(?:as the examples show\b|as in those examples\b)|\bbegins with (?:a|an) (?:consonant|vowel) sound\b",
    re.IGNORECASE,
)
_BANNED_RULEBOOK_START_RE = re.compile(
    r"^(?:also|although|because|but|compare|however|note|rather|see|since|sometimes|than|then|therefore|thus|under|used|whereas)\b",
    re.IGNORECASE,
)
_ALLOWED_LOWERCASE_START_RE = re.compile(
    r"^(?:a|an|the|my|your|his|her|its|our|their|this|that|these|those|some|any|each|every|another|no|"
    r"in|on|at|by|for|from|with|without|to|of|as|about|after|before|between|among|through|into|onto|"
    r"toward|towards|across|around|within|behind|beneath|above|below|near|inside|outside|during|despite|"
    r"who|whom|whose|which|that|where|when|why|how)\b",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")
_MYSTERIES_BANNED_START_RE = re.compile(
    r"^(?:setting the scene|wrapping up|what should i read\??|some more|english prepositions|"
    r"masses of quantifiers|how to deal|the first of these|both of these|of most interest|"
    r"in other|because this|we assume that speakers|according to walker, speakers|"
    r"in misunderstandings|linguistic logic is not mathematical|so if someone asks you|"
    r"in more functions than previously assumed|of time, not just|but when we look|"
    r"similarly with|we can push this further|this is interesting|but we do not know|"
    r"to doing so|new zealand\) effects|greek, latin and romance|london: allison|"
    r"aarts et al\.|the list given here|the same thing\.|we can tell which|now we turn|"
    r"we might want to treat|with the other cases|there is some hint|and in this,|"
    r"i will come to these reasons|of is has had the prescriptive public|why do we have|"
    r"the no-man's land|so, let’s look|so, let's look|but in other cases|who refers does|"
    r"with good lab data|in spite of all this work|i have to accept that)\b",
    re.IGNORECASE,
)
_MYSTERIES_BANNED_ANYWHERE_RE = re.compile(
    r"\b(?:setting the scene|wrapping up|what should i read|doi:|mouton de gruyter)\b",
    re.IGNORECASE,
)
_MYSTERIES_DISCOURSE_START_RE = re.compile(
    r"^(?:although|but|if|now|of|to|which|because|while|when|whereas|therefore|thus)\b",
    re.IGNORECASE,
)
_MYSTERIES_REFERENCE_RE = re.compile(
    r"\b(?:et al\.|university press|cambridge|routledge|language log|dissertation|journal of|working papers)\b",
    re.IGNORECASE,
)
_MYSTERIES_CTX_ARTIFACT_RE = re.compile(r"\[…\]|\[\.{2,}\]|/\*|\*/")
_MYSTERIES_NOTE_PAGE_NUM_RE = re.compile(r"^\d+\s+[A-Z]")
_MYSTERIES_NOTE_CHAPTER_REF_RE = re.compile(
    r"^(?:this factor (?:has been|was)|see chapter|chapter \d|in chapter|"
    r"aarts et al\.|for a longer|for those who want|in general,\s+the \d{4})\b",
    re.IGNORECASE,
)
_MYSTERIES_META_RE = re.compile(
    r"\b(?:grammar|grammatical|language|languages|speaker|speakers|linguist|linguists|construction|constructions|"
    r"pattern|patterns|system|systems|meaning|meanings|usage|usages|research|chapter|chapters|table|tables|"
    r"question|questions|problem|problems|development|developments|corpus|corpora|book|books|word|words|"
    r"english|tense|tenses|aspect|aspects|article|articles|noun|nouns|verb|verbs|adjective|adjectives|"
    r"preposition|prepositions|pronoun|pronouns|clause|clauses|sentence|sentences|countability|comparative|"
    r"comparatives|superlative|superlatives|progressive|passive|perfect|agreement|possession|case)\b",
    re.IGNORECASE,
)
_INCOMPLETE_LAST_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "if",
    "in",
    "of",
    "on",
    "or",
    "than",
    "that",
    "the",
    "to",
    "with",
}


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


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", str(text or "").strip())


def _looks_clean_mysteries_context(text: str, *, topic_key: str = "") -> bool:
    cleaned = _norm(text)
    lowered = cleaned.lower()
    words = re.findall(r"[A-Za-z']+", cleaned)
    if not cleaned:
        return False
    if _MYSTERIES_BANNED_START_RE.search(cleaned):
        return False
    if _MYSTERIES_BANNED_ANYWHERE_RE.search(cleaned):
        return False
    if _MYSTERIES_REFERENCE_RE.search(cleaned):
        return False
    if _MYSTERIES_CTX_ARTIFACT_RE.search(cleaned):
        return False
    if len(words) < 3:
        return False
    if words and words[-1].lower() in _INCOMPLETE_LAST_WORDS:
        return False
    if _MYSTERIES_DISCOURSE_START_RE.search(cleaned) and not cleaned.endswith((".", "!", "?")):
        return False
    if cleaned[:1].islower() and not _ALLOWED_LOWERCASE_START_RE.search(cleaned):
        return False
    if not any(ch in cleaned for ch in ".?!") and len(words) < 6:
        return False
    explicit_example_signal = bool("*" in cleaned or "…" in cleaned or "..." in cleaned or "'" in cleaned or "‘" in cleaned or "’" in cleaned or '"' in cleaned)
    if _MYSTERIES_META_RE.search(cleaned) and not explicit_example_signal:
        return False
    if len(words) < 5 and not re.search(r"\b(?:is|are|was|were|be|been|being|am|have|has|had|do|does|did|can|could|will|would|should|may|might|must|[A-Za-z]+ed|[A-Za-z]+ing|[A-Za-z]+s)\b", cleaned):
        if topic_key not in {"prepositions", "possession", "comparatives"}:
            return False
    if topic_key == "prepositions":
        if len(words) <= 5:
            if not re.search(
                r"\b(?:about|above|across|after|against|along|around|at|before|behind|below|beside|between|by|for|from|"
                r"in|inside|into|near|of|off|on|out|over|through|to|under|with)\b",
                lowered,
            ):
                return False
    return True


def _looks_clean_context(text: str, *, pair_method: str = "", source_path: str = "", topic_key: str = "") -> bool:
    cleaned = _norm(text)
    lowered = cleaned.lower()
    words = re.findall(r"[A-Za-z']+", cleaned)
    if not cleaned:
        return False
    if _BAD_TOKEN_RE.search(cleaned):
        return False
    if _BAD_CHAR_RE.search(cleaned):
        return False
    if _NEG_AUX_INFLECTED_RE.search(lowered):
        return False
    if _BE_AGREEMENT_RE.search(lowered):
        return False
    if _DO_AGREEMENT_RE.search(lowered):
        return False
    if _NAME_DONT_RE.search(cleaned):
        return False
    if _NP_DONT_RE.search(cleaned):
        return False
    if _TRAILING_META_RE.search(cleaned):
        return False
    if _LEADING_META_RE.search(cleaned):
        return False
    if _CROSS_REF_RE.search(cleaned):
        return False
    if cleaned.endswith("?"):
        if not _QUESTION_START_RE.search(cleaned):
            return False
        if len(words) < 4:
            return False
    if pair_method in {"rulebook_source_first", "quick_solutions_source_first"}:
        if len(words) < 3:
            return False
        if _LOW_INFO_RULEBOOK_RE.search(cleaned):
            return False
        if _META_FOLLOWUP_RE.search(cleaned):
            return False
        if _META_SOURCE_FIRST_RE.search(cleaned):
            return False
        if _EXAMPLE_META_RE.search(cleaned):
            return False
        if _LEADING_LABEL_RE.search(cleaned):
            return False
        if cleaned.endswith((",", ";", ":")):
            return False
        if ";" in cleaned:
            return False
        if cleaned[:1] in {",", ";", ":", ")"} or cleaned.startswith("("):
            return False
        if cleaned[:1].isdigit():
            return False
        if _BANNED_RULEBOOK_START_RE.search(cleaned):
            return False
        if cleaned[:1].islower() and not _ALLOWED_LOWERCASE_START_RE.search(cleaned):
            return False
        if cleaned[:1].islower() and "," in cleaned and not cleaned.endswith((".", "!", "?")) and len(words) > 4:
            return False
        if words and words[-1].lower() in _INCOMPLETE_LAST_WORDS:
            return False
    if "mysteries of english grammar" in str(source_path).lower():
        if not _looks_clean_mysteries_context(cleaned, topic_key=topic_key):
            return False
    return True


def build_clean_note_context_pairs(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    stats = {
        "input_rows": len(rows),
        "kept_rows": 0,
        "dropped_rows": 0,
        "dropped_bad_context": 0,
    }
    for row in rows:
        context_text = str(row.get("context_text") or "")
        pair_method = str(row.get("pair_method") or "")
        source_path = str(row.get("source_path") or "")
        topic_key = str(row.get("topic_key") or "")
        if not _looks_clean_context(context_text, pair_method=pair_method, source_path=source_path, topic_key=topic_key):
            stats["dropped_rows"] += 1
            stats["dropped_bad_context"] += 1
            continue
        if "mysteries of english grammar" in str(row.get("source_path") or "").lower():
            notation_text = _norm(str(row.get("notation_text") or ""))
            if _MYSTERIES_NOTE_PAGE_NUM_RE.search(notation_text):
                stats["dropped_rows"] += 1
                stats["dropped_bad_context"] += 1
                continue
            if _MYSTERIES_NOTE_CHAPTER_REF_RE.search(notation_text):
                stats["dropped_rows"] += 1
                stats["dropped_bad_context"] += 1
                continue
        kept.append(row)
        stats["kept_rows"] += 1
    report = {
        "pipeline_version": "clean_note_context_pairs_v1",
        "stats": stats,
        "topic_counts": {
            key: sum(1 for row in kept if str(row.get("topic_key") or "") == key)
            for key in sorted({str(row.get("topic_key") or "") for row in kept})
        },
    }
    return kept, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter raw source-first note/context pairs into a clean subset.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows, report = build_clean_note_context_pairs(list(_iter_jsonl(args.input_jsonl)))
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
