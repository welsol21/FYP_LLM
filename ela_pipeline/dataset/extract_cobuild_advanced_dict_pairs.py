"""Extract note-context pairs from Collins COBUILD Advanced Learner's Dictionary 9th Edition (2018).

Extraction strategy:
- Scan entries marked with [usu passive] or V-PASSIVE grammar codes.
- Extract definition text as notation (the "If someone is X, they are Y" pattern).
- Extract example sentences (marked with □) as context.
- Assign topic_key = "passive_voice" for all extracted pairs.
- Deduplicate extracted sentences.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


_CONTROL_RE = re.compile(r"[\x00-\x1f\uF000-\uF8FF]")
_WS_RE = re.compile(r"\s+")

# Example sentence marker in COBUILD entries
_EXAMPLE_MARKER = "\u25a1"  # □

# Grammar codes that mark passive constructions
_PASSIVE_CODES = ("[usu passive]", "V-PASSIVE", "[usu v-link ADJ]")

# Clean up grammar pattern codes embedded before examples
_GRAMMAR_CODE_RE = re.compile(r"\[[^\]]{1,60}\]")

# Extract headword from line start (word|word format)
_HEADWORD_RE = re.compile(r"^(?:\d+\s*)?([A-Za-z|/\-]+)")

# Passive definition pattern: "If someone/something is VERB, ..."
_PASSIVE_DEF_RE = re.compile(
    r"If\s+(?:someone|something|a\s+\w+|an?\s+\w+)\s+(?:is|are|has been|gets?)\s+\w+",
    re.IGNORECASE,
)


def _norm(value: object) -> str:
    value = _CONTROL_RE.sub(" ", str(value or ""))
    return _WS_RE.sub(" ", value.strip())


def _is_good_passive_sentence(text: str) -> bool:
    """Return True if text looks like a well-formed passive example sentence."""
    text = text.strip()
    if len(text) < 15:
        return False
    # Must end with sentence terminator
    if text[-1] not in ".!?":
        return False
    words = text.split()
    if len(words) < 4:
        return False
    lower = text.lower()
    # Must contain a passive auxiliary
    if not re.search(r"\b(?:is|are|was|were|been|be|being)\s+\w+ed\b|\b(?:is|are|was|were|been|be|being)\s+\w+en\b", lower):
        # Also accept modal passive like "can be done", "will be required"
        if not re.search(r"\b(?:can|could|will|would|should|may|might|must)\s+be\s+\w+", lower):
            return False
    return True


def _extract_definition_text(line: str) -> str:
    """Extract the definition/notation text from a COBUILD entry line."""
    # Remove leading sense number and POS tag
    text = re.sub(r"^\d+\s*(?:VERB|ADJ|N-\w+|PHRASAL VERB|PHR|PRON|QUANT|PHRASE)\s*", "", line).strip()
    # Remove grammar codes like [usu passive], [beV-ed +of], etc.
    text = _GRAMMAR_CODE_RE.sub("", text).strip()
    # Cut off at first example marker □
    if _EXAMPLE_MARKER in text:
        text = text[:text.index(_EXAMPLE_MARKER)].strip()
    # Remove trailing punctuation except period
    text = text.rstrip(", ")
    # Clean up whitespace
    text = _norm(text)
    # Must be at least a minimal definition
    if len(text) < 20:
        return ""
    return text


def _extract_examples(line: str) -> list[str]:
    """Extract example sentences from a COBUILD entry line (after □ markers)."""
    parts = line.split(_EXAMPLE_MARKER)
    examples = []
    for part in parts[1:]:  # Skip everything before first □
        # Remove leading grammar code like [beV-ed] or [beV-ed +of]
        part = _GRAMMAR_CODE_RE.sub("", part).strip()
        # Also remove [Also V] style endings
        part = re.sub(r"\[Also[^\]]*\]", "", part).strip()
        # Cut off at sense separator ● (start of next definition sense)
        if "\u25cf" in part:
            part = part[:part.index("\u25cf")].strip()
        # Take only up to first unrelated content (next entry start, etc.)
        # Stop at register markers like [FORMAL], [INFORMAL], [WRITTEN], [SPOKEN]
        part = re.sub(r"\s*\[(?:FORMAL|INFORMAL|WRITTEN|SPOKEN|BUSINESS|JOURNALISM|LITERARY|TECHNICAL|COMPUTING|LEGAL|MEDICAL|OFFENSIVE|DATED|OLD-FASHIONED)\].*$", "", part, flags=re.IGNORECASE).strip()
        # Clean control characters
        sentence = _norm(part)
        if sentence and sentence[-1] not in ".!?":
            # Try to get just the first sentence
            m = re.match(r"^(.{10,}?[.!?])", sentence)
            if m:
                sentence = m.group(1).strip()
            else:
                continue
        if sentence and len(sentence) >= 15:
            examples.append(sentence)
    return examples


def extract_cobuild_passive_pairs(text: str, source_path: str) -> list[dict[str, Any]]:
    """Extract passive-voice note-context pairs from COBUILD dictionary text."""
    lines = _norm(text).split("\n") if "\n" in _norm(text) else text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Re-normalize line by line
    lines = [_norm(line) for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]

    pairs: list[dict[str, Any]] = []
    seen_contexts: set[str] = set()

    for i, line in enumerate(lines):
        # Check if this line has a passive grammar code
        has_passive = any(code in line for code in _PASSIVE_CODES)
        if not has_passive:
            continue

        # Extract headword for notation/entry_head
        hw_match = _HEADWORD_RE.match(line.lstrip("0123456789 "))
        headword = hw_match.group(1).replace("|", "") if hw_match else ""

        # Extract definition (notation text)
        notation = _extract_definition_text(line)

        # Extract examples
        examples = _extract_examples(line)

        # Filter to passive sentences only
        for example in examples:
            if not _is_good_passive_sentence(example):
                continue
            key = example.lower()
            if key in seen_contexts:
                continue
            seen_contexts.add(key)

            pairs.append({
                "topic_key": "passive_voice",
                "context_text": example,
                "notation_text": notation or f"The word '{headword}' is used in the passive voice.",
                "entry_head": headword,
                "source_path": source_path,
                "pair_method": "cobuild_passive_v1",
            })

    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract passive-voice pairs from Collins COBUILD Advanced Learner's Dictionary 9th Edition."
    )
    parser.add_argument(
        "--payload-txt",
        default=(
            "data/processed_book_text_cache/"
            "Collins_COBUILD_Advanced_Learner_s_Dictionary._The_Source_of_Authentic_English."
            "_9th_Edition_-_Collins_COBUILD_Dictionaries_for_Learners_-_2018__0cd928ffaeea/payload.txt"
        ),
    )
    parser.add_argument(
        "--output-jsonl",
        default="data/reports/cobuild_advanced_2018_pairs.jsonl",
    )
    parser.add_argument(
        "--report-json",
        default="data/reports/cobuild_advanced_2018_pairs_report.json",
    )
    args = parser.parse_args()

    payload_path = Path(args.payload_txt)
    text = payload_path.read_text(encoding="utf-8", errors="ignore")

    pairs = extract_cobuild_passive_pairs(text, source_path=str(payload_path))

    out_path = Path(args.output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair, ensure_ascii=False) + "\n")

    topic_counts = {"passive_voice": len(pairs)}
    report = {
        "source": str(payload_path),
        "pairs_total": len(pairs),
        "topic_counts": topic_counts,
    }
    Path(args.report_json).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
