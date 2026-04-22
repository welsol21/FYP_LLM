"""Extract grammar (word, definition) pairs from Simple English Wiktionary dump.

Targets grammatical function words: prepositions, conjunctions, modal auxiliaries,
determiners/articles, relative pronouns, question words, particles.

Input:  data/wiktionary/simplewiktionary-latest.xml.bz2
Output: data/reports/simplewiktionary_grammar_pairs.jsonl
"""

from __future__ import annotations

import argparse
import bz2
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# POS section headings that are relevant to grammar instruction
_TARGET_POS: set[str] = {
    "preposition",
    "conjunction",
    "determiner",
    "article",
    "pronoun",
    "particle",
    "adverb",
    "interjection",
    "verb",  # modals — we'll filter by topic_key
}

# Map raw POS heading (lowercased) → canonical topic_key
_POS_TO_TOPIC: dict[str, str] = {
    "preposition": "prepositions",
    "conjunction": "conjunctions",
    "determiner": "determiners",
    "article": "determiners",
    "pronoun": "pronouns",
    "particle": "particles",
    "adverb": "adverbs",
    "verb": "modal",
}

# For "Verb" POS entries we only keep known modals/auxiliaries
_MODAL_WORDS: frozenset[str] = frozenset(
    ["can", "could", "will", "would", "shall", "should", "may", "might", "must",
     "ought", "dare", "need", "used to", "have to", "be able to"]
)

# Relative/question pronouns — keep under relative_clauses / wh_question
_RELATIVE_PRONOUNS: frozenset[str] = frozenset(
    ["who", "whom", "whose", "which", "that", "what", "where", "when", "why", "how"]
)

_WS_RE = re.compile(r"\s+")
_WIKILINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
_TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ITALIC_RE = re.compile(r"'{2,3}")
_BOLD_RE = re.compile(r"'''([^']+)'''")
_ITALIC2_RE = re.compile(r"''([^']+)''")
_HASH_PREFIX_RE = re.compile(r"^#+:?\s*")


def _strip_wiki(text: str) -> str:
    """Remove wiki markup, return plain text."""
    text = _WIKILINK_RE.sub(r"\1", text)
    text = _TEMPLATE_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC2_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _parse_page_text(wikitext: str) -> Iterator[Dict[str, Any]]:
    """Yield (pos, definition, examples) dicts from a page's wikitext."""
    current_pos: Optional[str] = None
    current_defs: List[str] = []
    current_examples: List[str] = []

    def _flush():
        if current_pos and current_defs:
            yield {"pos": current_pos, "defs": list(current_defs), "examples": list(current_examples)}

    lines = wikitext.split("\n")
    for line in lines:
        # Detect POS section heading: == Preposition ==
        m = re.match(r"^==\s*([^=]+?)\s*==\s*$", line)
        if m:
            yield from _flush()
            current_pos = m.group(1).strip().lower()
            current_defs = []
            current_examples = []
            continue

        if current_pos is None:
            continue

        # Skip sub-section headings (===, ====)
        if re.match(r"^={3,}", line):
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # Definition line: starts with #, NOT #:
        if re.match(r"^#+[^:#]", stripped):
            defn = _strip_wiki(_HASH_PREFIX_RE.sub("", stripped))
            # Filter out short/tag-only entries
            if len(defn.split()) >= 4 and any(ch.islower() for ch in defn):
                current_defs.append(defn)

        # Example line: starts with #:
        elif stripped.startswith("#:") or stripped.startswith("##:"):
            example = _strip_wiki(_HASH_PREFIX_RE.sub("", stripped))
            # Strip wrapping italics leftover
            example = example.strip("'").strip()
            if len(example.split()) >= 3:
                current_examples.append(example)

    yield from _flush()


def _iter_pages(dump_path: Path) -> Iterator[tuple[str, str]]:
    """Yield (title, wikitext) for each page in the dump."""
    ns = {"mw": "http://www.mediawiki.org/xml/Export-0.11/"}

    with bz2.open(dump_path, "rt", encoding="utf-8") as f:
        content = f.read()

    # Use iterative parsing on string to handle large file
    root = ET.fromstring(content)
    ns_uri = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    tag = lambda name: f"{{{ns_uri}}}{name}" if ns_uri else name

    for page in root.iter(tag("page")):
        title_el = page.find(tag("title"))
        if title_el is None or title_el.text is None:
            continue
        title = title_el.text.strip()

        # Skip non-main-namespace entries (contain ":")
        if ":" in title:
            continue

        # Find wikitext
        text_el = page.find(f".//{tag('text')}")
        if text_el is None or not text_el.text:
            continue

        yield title, text_el.text


def extract_wiktionary_pairs(dump_path: Path) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for title, wikitext in _iter_pages(dump_path):
        title_lower = title.lower().strip()

        for entry in _parse_page_text(wikitext):
            pos = entry["pos"]
            defs = entry["defs"]
            examples = entry["examples"]

            # Determine topic_key
            topic_key = _POS_TO_TOPIC.get(pos, "")
            if not topic_key:
                continue

            # For verbs: only keep modals
            if pos == "verb":
                if title_lower not in _MODAL_WORDS:
                    continue

            # For pronouns: split relative/wh vs general
            if pos == "pronoun":
                if title_lower in _RELATIVE_PRONOUNS:
                    topic_key = "relative_clauses" if title_lower in {"who", "whom", "whose", "which", "that"} else "wh_question"
                else:
                    continue  # skip non-relative pronouns

            for defn in defs:
                # Filter out meta-text
                if len(defn.split()) < 5:
                    continue
                if not defn.rstrip().endswith((".", "!", "?")):
                    defn = defn + "."

                # Pair: use example sentence as context (if available) or skip
                # We create pairs: (title word, definition) = notation pairs
                # Also create example-based pairs where definition is the notation
                dedup_key = f"{title_lower}|||{defn}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                pairs.append({
                    "topic_key": topic_key,
                    "context_text": title,       # the word itself as the "sentence"
                    "notation_text": defn,
                    "entry_head": f"{title} ({pos})",
                    "source_path": str(dump_path),
                    "pair_method": "wiktionary_defn_v1",
                    "examples": examples[:3],
                })

                # Emit at most one example-based pair per (word, definition) to avoid
                # many identical targets flooding the training set.
                for ex in examples[:1]:
                    if len(ex.split()) < 4:
                        continue
                    ex_key = f"{ex.lower()}|||{defn}"
                    if ex_key in seen:
                        continue
                    seen.add(ex_key)
                    pairs.append({
                        "topic_key": topic_key,
                        "context_text": ex,
                        "notation_text": defn,
                        "entry_head": f"{title} ({pos})",
                        "source_path": str(dump_path),
                        "pair_method": "wiktionary_example_v1",
                        "examples": [],
                    })

    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract grammar pairs from Simple English Wiktionary dump")
    parser.add_argument(
        "--dump",
        default="data/wiktionary/simplewiktionary-latest.xml.bz2",
        help="Path to the bz2 MediaWiki dump",
    )
    parser.add_argument(
        "--output-jsonl",
        default="data/reports/simplewiktionary_grammar_pairs.jsonl",
    )
    parser.add_argument(
        "--report-json",
        default="data/reports/simplewiktionary_grammar_pairs_report.json",
    )
    args = parser.parse_args()

    base = Path("/home/vlad/Dev/FYP_LLM")
    dump_path = base / args.dump
    out_path = base / args.output_jsonl
    report_path = base / args.report_json

    print(f"Parsing {dump_path} ...")
    pairs = extract_wiktionary_pairs(dump_path)
    print(f"Extracted {len(pairs)} pairs")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    topic_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    for p in pairs:
        topic_counts[p["topic_key"]] = topic_counts.get(p["topic_key"], 0) + 1
        method_counts[p["pair_method"]] = method_counts.get(p["pair_method"], 0) + 1

    report = {
        "dump": str(dump_path),
        "pairs_total": len(pairs),
        "topic_counts": dict(sorted(topic_counts.items())),
        "method_counts": method_counts,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
