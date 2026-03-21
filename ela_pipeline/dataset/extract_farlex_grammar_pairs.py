"""Extract note-context pairs from Farlex Complete English Grammar Rules (2016).

Extraction strategy:
- Walk section headings and map them to topic_keys.
- Collect bullet-point example sentences (lines starting with • or ✔).
- Skip incorrect-example lines (starting with ✖).
- Skip sections that are part of the table of contents or quizzes.
- Output one pair per sentence: topic_key + sentence + section heading as notation.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")
_PAGE_NUM_RE = re.compile(r"^\d{1,4}$")
_QUOTE_STRIP_RE = re.compile(r'^["\u201c\u201d\u2018\u2019]+|["\u201c\u201d\u2018\u2019.]+$')
# Trailing parenthetical after a sentence close: ." (note...) or .) at end
_TRAILING_PAREN_RE = re.compile(r'\s*\((?:[a-z]|[A-Z])[^)]{0,120}\)\s*\.?\s*$')
# Dialogue fragment: "Speaker A: ...", "Speaker B: ..."
_DIALOGUE_RE = re.compile(r'^Speaker\s+[A-Z]\s*:', re.IGNORECASE)

# Section heading → topic_key.  Keys are lowercase versions of the heading line.
_TOPIC_HEADINGS: dict[str, str] = {
    # Passive
    "passive voice": "passive_voice",
    "active and passive voice": "passive_voice",
    # Conditional
    "conditional sentences": "conditional_sentences",
    "zero conditional": "conditional_sentences",
    "first conditional": "conditional_sentences",
    "second conditional": "conditional_sentences",
    "third conditional": "conditional_sentences",
    # Modal
    "modal auxiliary verbs": "modal",
    "modal auxiliary verbs - will": "modal",
    "modal auxiliary verbs - would": "modal",
    "modal auxiliary verbs - shall": "modal",
    "modal auxiliary verbs - should": "modal",
    "modal auxiliary verbs - can": "modal",
    "modal auxiliary verbs - could": "modal",
    "modal auxiliary verbs - may": "modal",
    "modal auxiliary verbs - might": "modal",
    "modal auxiliary verbs - must": "modal",
    # Perfect aspect
    "present perfect tense": "perfect",
    "past perfect tense": "perfect",
    "future perfect tense": "perfect",
    "present perfect continuous tense": "perfect",
    "past perfect continuous tense": "perfect",
    "future perfect continuous tense": "perfect",
    # Progressive / continuous
    "present continuous tense (progressive)": "progressive",
    "present continuous tense": "progressive",
    "past continuous tense": "progressive",
    "future continuous tense": "progressive",
    # Relative clauses
    "relative clauses": "relative_clauses",
    "relative clauses (adjective clauses)": "relative_clauses",
    # Noun / that-clauses
    "noun clauses": "that_clause",
    # Prepositions
    "prepositions": "prepositions",
    "prepositional phrases": "prepositional_phrases",
    # Questions / negatives
    "interrogative sentences": "wh_question",
    "negative interrogative sentences": "questions_and_negatives",
    "question tags": "question_tags",
    "wh-questions": "wh_question",
}

# Lines that signal end of a useful section
_STOP_PREFIXES = ("quiz", "quiz answers", "index", "about the author", "about the editor")

# Minimum line number to start extraction (skip TOC + author bios)
_MIN_START_LINE = 250

# Maximum lines to collect per section
_MAX_SECTION_LINES = 200


def _norm(value: object) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def _normalize_lines(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return [_norm(line) for line in raw.split("\n")]


def _is_stop(line: str) -> bool:
    lower = line.lower()
    return any(lower == pfx or lower.startswith(pfx) for pfx in _STOP_PREFIXES)


def _is_title_case(line: str) -> bool:
    """Return True if every word in line starts with an uppercase letter."""
    words = re.split(r"[\s\-()]+", line)
    return bool(words) and all(
        (not w or not w[0].isalpha() or w[0].isupper()) for w in words
    )


def _is_topic_heading(line: str) -> str:
    """Return topic_key if line is a known section heading, else ''.

    Only matches title-case lines to avoid matching subsection references like
    "Passive voice" (lowercase "voice") embedded inside running prose.
    """
    if not line or not _is_title_case(line):
        return ""
    return _TOPIC_HEADINGS.get(line.lower(), "")


def _extract_sentence(line: str) -> str:
    """Extract English sentence from a bullet/example line.

    Bullet markers: •, ✔, "• ...", "✔ ..."
    Sentence may be quoted: • "She had already left."
    """
    # Remove bullet / tick markers
    text = re.sub(r"^[•✔]\s*", "", line).strip()

    # Filter dialogue fragments like "Speaker A: ..."
    if _DIALOGUE_RE.match(text):
        return ""

    # Unwrap outer quotes (curly or straight), then strip trailing paren note
    # Pattern: "sentence." (explanation...)  →  sentence.
    m = re.match(r'^["\u201c\u201e](.*?)["\u201d\u201c](.*)$', text)
    if m:
        inner = m.group(1).strip()
        # Only keep if the remainder is a parenthetical note, not more sentence
        remainder = m.group(2).strip()
        if not remainder or remainder.startswith("("):
            text = inner
        # else keep full text (both halves form the sentence)

    # Strip trailing parenthetical explanation: ." (note...) or just (note...)
    text = _TRAILING_PAREN_RE.sub("", text).strip()
    # Restore sentence-ending period if stripped
    if text and text[-1] not in ".?!":
        text = text  # leave as-is, spaCy will handle

    # Reject lines that look like labels / metadata (all-caps, short, no verb)
    if len(text) < 10:
        return ""
    if re.fullmatch(r"[A-Z0-9 ,.'\":()-]+", text) and len(text.split()) <= 6:
        return ""
    # Must have at least one lowercase letter (real sentence, not a heading)
    if not any(ch.islower() for ch in text):
        return ""
    return text


def extract_farlex_pairs(text: str, source_path: str) -> list[dict[str, Any]]:
    lines = _normalize_lines(text)
    pairs: list[dict[str, Any]] = []
    seen_sentences: set[str] = set()

    current_heading = ""
    current_topic = ""

    for idx, line in enumerate(lines):
        line_no = idx + 1

        if line_no < _MIN_START_LINE:
            continue

        if _is_stop(line):
            continue

        # Detect new topic section
        topic_key = _is_topic_heading(line)
        if topic_key:
            current_heading = line
            current_topic = topic_key
            continue

        if not current_topic:
            continue

        # Skip page numbers
        if _PAGE_NUM_RE.fullmatch(line):
            continue

        # Collect bullet-point examples (• or ✔), skip incorrect examples (✖)
        if line.startswith("✖"):
            continue

        if line.startswith("•") or line.startswith("✔"):
            sentence = _extract_sentence(line)
            if not sentence:
                continue
            key = sentence.lower()
            if key in seen_sentences:
                continue
            seen_sentences.add(key)
            pairs.append(
                {
                    "topic_key": current_topic,
                    "context_text": sentence,
                    "notation_text": current_heading,
                    "entry_head": current_heading,
                    "source_path": source_path,
                    "pair_method": "farlex_bullet_v1",
                }
            )

    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract note-context pairs from the Farlex grammar book.")
    parser.add_argument(
        "--payload-txt",
        default="data/processed_book_text_cache/"
        "Farlex_International_-_Complete_English_Grammar_Rules_-_2016__e594ff511831/payload.txt",
        help="Path to the cached payload.txt for the Farlex book",
    )
    parser.add_argument(
        "--output-jsonl",
        default="data/reports/farlex_grammar_2016_pairs.jsonl",
        help="Output JSONL path for extracted pairs",
    )
    parser.add_argument("--report-json", default="data/reports/farlex_grammar_2016_pairs_report.json")
    args = parser.parse_args()

    payload_path = Path(args.payload_txt)
    text = payload_path.read_text(encoding="utf-8", errors="ignore")

    pairs = extract_farlex_pairs(text, source_path=str(payload_path))

    out_path = Path(args.output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair, ensure_ascii=False) + "\n")

    # Per-topic counts
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
