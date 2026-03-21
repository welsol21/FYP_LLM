"""Extract note-context pairs from English Grammar in Use 5th Edition (2019).

Extraction strategy:
- Walk unit headers: "Unit" (standalone line) → title line → unit number line.
- Map unit numbers/titles to topic_keys.
- Collect example sentences from sections A–H (stop before Exercises).
- Classify lines as examples vs. metalinguistic prose using targeted heuristics.
- Output one pair per sentence: topic_key + sentence + unit title as notation.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_UNIT_NUMBER_RE = re.compile(r"^\d{1,3}$")
_SECTION_RE = re.compile(r"^[A-H]$")
_PAGE_NUM_RE = re.compile(r"^\d{1,4}$")

# Trailing (not X), (= X), (or X) annotations
_TRAILING_ANNOTATION_RE = re.compile(
    r"\s*\((?:not|=|or)\s+[^)]{1,100}\)\s*\.?\s*$", re.IGNORECASE
)
# Ellipsis artefacts
_ELLIPSIS_RE = re.compile(r"\s*…\s*$")
# "or X" alternative at end of line
_OR_ALT_RE = re.compile(r"\s+or\s+\S.*$")

# Unit-number → topic_key override map (unit number as int)
_UNIT_TOPIC: dict[int, str] = {
    # Present continuous / progressive
    1: "progressive", 6: "progressive", 9: "progressive", 16: "progressive",
    # Present simple
    2: "present_simple",
    # Past simple
    5: "past_simple",
    # Present perfect
    7: "perfect", 8: "perfect", 9: "perfect", 10: "perfect",
    11: "perfect", 12: "perfect", 13: "perfect", 14: "perfect",
    # Past perfect
    15: "perfect", 16: "perfect",
    # Future
    19: "future", 20: "future", 21: "future", 22: "future",
    23: "future", 24: "future", 25: "future",
    # Modal
    26: "modal", 27: "modal", 28: "modal", 29: "modal", 30: "modal",
    31: "modal", 32: "modal", 33: "modal", 34: "modal", 35: "modal",
    36: "modal",
    # Conditional / wish / if
    38: "conditional_sentences", 39: "conditional_sentences",
    40: "conditional_sentences", 41: "conditional_sentences",
    # Passive
    42: "passive_voice", 43: "passive_voice", 44: "passive_voice",
    45: "passive_voice", 46: "passive_voice",
    # Reported speech
    47: "reported_speech", 48: "reported_speech",
    # Questions
    49: "wh_question", 50: "wh_question", 51: "wh_question",
    52: "question_tags",
    # Infinitive / gerund / verb patterns
    53: "verb_patterns", 54: "verb_patterns", 55: "verb_patterns",
    56: "verb_patterns", 57: "verb_patterns", 58: "verb_patterns",
    59: "verb_patterns", 60: "verb_patterns", 61: "verb_patterns",
    62: "verb_patterns", 63: "verb_patterns", 64: "verb_patterns",
    65: "verb_patterns", 66: "verb_patterns", 67: "verb_patterns",
    68: "verb_patterns",
    # Nouns / articles
    69: "nouns", 70: "nouns", 71: "nouns", 72: "articles",
    73: "articles", 74: "articles", 75: "articles", 76: "articles",
    77: "articles", 78: "articles", 79: "nouns", 80: "nouns",
    # Pronouns / quantifiers
    82: "pronouns", 83: "pronouns", 84: "pronouns",
    85: "quantifiers", 86: "quantifiers", 87: "quantifiers",
    88: "quantifiers", 89: "quantifiers", 90: "quantifiers", 91: "quantifiers",
    # Relative clauses
    92: "relative_clauses", 93: "relative_clauses", 94: "relative_clauses",
    95: "relative_clauses", 96: "relative_clauses",
    # Adjectives / adverbs
    98: "adjectives", 99: "adjectives", 100: "adverbs",
    101: "adverbs", 102: "adverbs", 103: "adjectives",
    # Prepositions (units 97–121 area)
    97: "prepositions", 104: "prepositions", 105: "prepositions",
    106: "prepositions", 107: "prepositions", 108: "prepositions",
    109: "prepositions", 110: "prepositions", 111: "prepositions",
    112: "prepositions", 113: "prepositions", 114: "prepositions",
    # Conjunctions / clauses
    115: "conjunctions", 116: "conjunctions", 117: "conjunctions",
    118: "conjunctions", 119: "conjunctions",
    # Word order
    120: "word_order", 121: "word_order",
    # Phrasal verbs
    122: "phrasal_verbs", 123: "phrasal_verbs", 124: "phrasal_verbs",
    125: "phrasal_verbs", 126: "phrasal_verbs", 127: "phrasal_verbs",
    128: "phrasal_verbs", 129: "phrasal_verbs", 130: "phrasal_verbs",
    131: "phrasal_verbs", 132: "phrasal_verbs", 133: "phrasal_verbs",
    134: "phrasal_verbs", 135: "phrasal_verbs", 136: "phrasal_verbs",
    137: "phrasal_verbs", 138: "phrasal_verbs", 139: "phrasal_verbs",
    140: "phrasal_verbs", 141: "phrasal_verbs", 142: "phrasal_verbs",
    143: "phrasal_verbs", 144: "phrasal_verbs", 145: "phrasal_verbs",
}

# Metalinguistic prefixes that mark explanatory prose (not examples).
# Only applied if the line STARTS with one of these (case-insensitive).
_META_PREFIXES: tuple[str, ...] = (
    "we use ", "we say ", "we can use", "we often ", "we don't use",
    "we do not", "we normally ", "we usually ",
    "when we use", "when we say", "when we talk", "when we write",
    "the present ", "the past ", "the future ", "the following",
    "study this ", "note that ", "for a list", "see the ", "see appendix",
    "compare ", "you can use", "you can say ", "you can also use",
    "it is not usual", "it's not usual", "it is usually", "it's usually",
    "sometimes we ", "in these expressions",
    "this is usually ", "this means ", "this is because",
    "just = ", "already = ", "yet = ", "still = ", "just:", "already:", "yet:",
    "in questions and negative", "in past questions",
    "with these meanings",
    "have got is not", "have/has", "had + ", "be + ",
    "for questions", "for negative",
    "irregular verbs", "past participle",
    "not normally used",
    "we are expecting",
    "both correct", "all correct",
    "➜ ", "→ ",
    "additional exercises",
    "a self-study", "fifth edition",
)


def _norm(value: object) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def _normalize_lines(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw.split("\n")]


def _clean_sentence(line: str) -> str:
    """Strip trailing annotation artefacts and clean whitespace."""
    # Remove trailing (not X), (= X) annotations
    text = _TRAILING_ANNOTATION_RE.sub("", line).strip()
    # Remove trailing ellipsis
    text = _ELLIPSIS_RE.sub("", text).strip()
    # Remove " or <alternative>" at end (keep first option)
    # Only when it looks like a full alternative sentence (starts with upper after " or ")
    m = re.search(r"\s+or\s+([A-Z'])", text)
    if m:
        text = text[: m.start()].strip()
    # Handle " / " separator — keep only the first alternative
    if " / " in text:
        text = text.split(" / ")[0].strip()
    # Re-add period if stripping left a sentence without terminator
    if text and text[-1] not in ".?!":
        text = text + "."
    return _norm(text)


def _is_metalinguistic(line: str) -> bool:
    """Return True if the line is grammatical explanation prose, not an example."""
    lower = line.lower()
    for prefix in _META_PREFIXES:
        if lower.startswith(prefix):
            return True
    # Lines that are just grammar labels / table headers (no verb, very short)
    if len(line) < 8:
        return True
    # Conjugation table entries like "I/we/they/you" or "he/she/it"
    if re.fullmatch(r"[A-Za-z/'\s]+", line) and len(line.split()) <= 4 and "/" in line:
        return True
    # Lines like "finished lost done been etc." (word list without sentence structure)
    if re.fullmatch(r"[a-z]+(?:\s+[a-z]+)*\s+etc\.", line):
        return True
    # Contains bare grammar metalanguage like "past participle"
    if re.search(r"\bpast participle\b|\bhave/has\b|\bverb form\b", lower):
        return True
    return False


def _is_example_sentence(line: str) -> bool:
    """Return True if line looks like a natural example sentence."""
    # Strong positive signal: annotation showing contrast/explanation
    if "(not " in line or "(= " in line:
        return True

    # Must have at least one lowercase letter (not ALL CAPS headers)
    if not any(c.islower() for c in line):
        return False

    # Skip metalinguistic prose
    if _is_metalinguistic(line):
        return False

    # Must start with uppercase, single quote, or 'I' (I've, I'm, etc.)
    first = line[0]
    if not (first.isupper() or first in ("'", "\u2018", "\u201c")):
        return False

    # Strip trailing annotations to check sentence terminator
    clean = _TRAILING_ANNOTATION_RE.sub("", line).strip()
    clean = _ELLIPSIS_RE.sub("", clean).strip()
    # Remove " or X" tail
    m = re.search(r"\s+or\s+([A-Z'])", clean)
    if m:
        clean = clean[: m.start()].strip()

    if not clean:
        return False

    # Line must end with sentence terminator
    if clean[-1] not in ".?!":
        return False

    # Must have at least 3 words
    if len(clean.split()) < 3:
        return False

    return True


def _parse_unit_headers(lines: list[str]) -> list[tuple[int, int, str]]:
    """
    Return list of (unit_number, header_end_idx, unit_title) for each parsed unit.
    """
    units: list[tuple[int, int, str]] = []
    i = 0
    while i < len(lines):
        if lines[i] != "Unit":
            i += 1
            continue
        # Collect next non-empty lines
        probe: list[tuple[int, str]] = []
        for j in range(i + 1, min(len(lines), i + 10)):
            if lines[j]:
                probe.append((j, lines[j]))
        if len(probe) < 2:
            i += 1
            continue
        title_idx, title = probe[0]
        num_idx, num_candidate = probe[1]
        if _UNIT_NUMBER_RE.fullmatch(num_candidate):
            try:
                unit_num = int(num_candidate)
            except ValueError:
                i += 1
                continue
            units.append((unit_num, num_idx, title))
            i = num_idx + 1
        else:
            i += 1
    return units


def extract_egiu_pairs(text: str, source_path: str) -> list[dict[str, Any]]:
    lines = _normalize_lines(text)
    pairs: list[dict[str, Any]] = []
    seen_sentences: set[str] = set()

    units = _parse_unit_headers(lines)

    for unit_idx, (unit_num, header_end, unit_title) in enumerate(units):
        topic_key = _UNIT_TOPIC.get(unit_num, "")
        if not topic_key:
            continue

        # Collect body lines until next "Unit" marker or "Exercises" standalone
        body_start = header_end + 1
        body_end = len(lines)
        for nxt_num, nxt_header, nxt_title in units[unit_idx + 1:]:
            # Find where the "Unit" line for the next unit is
            # Approximate: scan from body_start for "Unit" standalone
            break
        # Scan forward from body_start to find the next "Unit" line
        scan_idx = body_start
        while scan_idx < len(lines):
            if lines[scan_idx] == "Unit":
                body_end = scan_idx
                break
            if lines[scan_idx] == "Exercises":
                body_end = scan_idx
                break
            scan_idx += 1

        notation = f"Unit {unit_num}: {unit_title}"

        for line in lines[body_start:body_end]:
            if not line:
                continue
            if _PAGE_NUM_RE.fullmatch(line):
                continue
            if _SECTION_RE.fullmatch(line):
                continue
            if not _is_example_sentence(line):
                continue

            sentence = _clean_sentence(line)
            if not sentence or len(sentence) < 10:
                continue
            # Reject if sentence is still metalinguistic after cleaning
            if _is_metalinguistic(sentence):
                continue

            key = sentence.lower()
            if key in seen_sentences:
                continue
            seen_sentences.add(key)

            pairs.append(
                {
                    "topic_key": topic_key,
                    "context_text": sentence,
                    "notation_text": notation,
                    "entry_head": unit_title,
                    "source_path": source_path,
                    "pair_method": "egiu_unit_section_v1",
                }
            )

    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract note-context pairs from English Grammar in Use 5th Edition."
    )
    parser.add_argument(
        "--payload-txt",
        default=(
            "data/processed_book_text_cache/"
            "English_Grammar_in_Use_5th_Edition_-_2019__d95d2b28ce2e/payload.txt"
        ),
    )
    parser.add_argument(
        "--output-jsonl",
        default="data/reports/egiu_5th_2019_pairs.jsonl",
    )
    parser.add_argument(
        "--report-json",
        default="data/reports/egiu_5th_2019_pairs_report.json",
    )
    args = parser.parse_args()

    payload_path = Path(args.payload_txt)
    text = payload_path.read_text(encoding="utf-8", errors="ignore")

    pairs = extract_egiu_pairs(text, source_path=str(payload_path))

    out_path = Path(args.output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair, ensure_ascii=False) + "\n")

    topic_counts: dict[str, int] = {}
    for pair in pairs:
        topic_counts[pair["topic_key"]] = topic_counts.get(pair["topic_key"], 0) + 1

    report = {
        "source": str(payload_path),
        "pairs_total": len(pairs),
        "topic_counts": dict(sorted(topic_counts.items())),
    }
    Path(args.report_json).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
