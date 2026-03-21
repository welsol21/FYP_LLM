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


def _looks_clean_context(text: str, *, pair_method: str = "") -> bool:
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
    if pair_method == "rulebook_source_first":
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
        if not _looks_clean_context(context_text, pair_method=pair_method):
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
