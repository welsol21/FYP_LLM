"""Scrape Cambridge Learner's Dictionary for function-word definition pairs.

Targets ADP, AUX, SCONJ, CCONJ words that are underrepresented in Wiktionary.
Output schema matches simplewiktionary_grammar_pairs.jsonl:
  context_text   – the word (lemma)
  notation_text  – Cambridge definition (with example stripped to bare definition)
  entry_head     – "word (pos_label)"
  pair_method    – "cambridge_learner_defn_v1"
  topic_key      – "prepositions" | "modal" | "subordinating_conjunctions" | "coordinating_conjunctions"
  source_path    – cambridge URL
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

try:
    import urllib.request as _req
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Target words by grammatical category
# ---------------------------------------------------------------------------

PREPOSITIONS = [
    "about", "above", "across", "after", "against", "along", "among", "around",
    "as", "at", "before", "behind", "below", "beneath", "beside", "between",
    "beyond", "by", "despite", "down", "during", "except", "for", "from",
    "in", "inside", "into", "like", "near", "of", "off", "on", "onto",
    "opposite", "out", "outside", "over", "past", "per", "round", "since",
    "through", "throughout", "till", "to", "toward", "towards", "under",
    "unlike", "until", "up", "upon", "via", "with", "within", "without",
]

AUXILIARIES = [
    "be", "can", "could", "dare", "do", "have", "may", "might", "must",
    "need", "ought", "shall", "should", "will", "would",
]

SUBORDINATING_CONJUNCTIONS = [
    "after", "although", "as", "because", "before", "if", "once", "since",
    "though", "unless", "until", "when", "whereas", "while", "whether",
]

COORDINATING_CONJUNCTIONS = [
    "and", "but", "for", "nor", "or", "so", "yet",
]

# Cambridge POS label → spaCy-style POS tag + topic_key
POS_MAP: dict[str, tuple[str, str]] = {
    "preposition":              ("ADP",  "prepositions"),
    "conjunction":              ("CCONJ","coordinating_conjunctions"),
    "subordinating conjunction":("SCONJ","subordinating_conjunctions"),
    "coordinating conjunction": ("CCONJ","coordinating_conjunctions"),
    "modal verb":               ("AUX",  "modal"),
    "auxiliary verb":           ("AUX",  "modal"),
    "verb":                     ("VERB", "verb"),
    "adverb":                   ("ADV",  "adverbs"),
    "adjective":                ("ADJ",  "adjectives"),
    "determiner":               ("DET",  "determiners"),
    "pronoun":                  ("PRON", "pronouns"),
}

# Only keep POS blocks relevant to our target categories
WANTED_TOPIC_KEYS = {
    "prepositions",
    "modal",
    "subordinating_conjunctions",
    "coordinating_conjunctions",
}

BASE_URL = "https://dictionary.cambridge.org/dictionary/learner-english/{word}"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/109.0"
DELAY_S = 1.2  # polite crawl delay

_WS_RE = re.compile(r"\s+")


def _fetch(word: str) -> Optional[str]:
    url = BASE_URL.format(word=word)
    req = _req.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with _req.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  WARN: fetch failed for {word!r}: {exc}")
        return None


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return _WS_RE.sub(" ", text).strip()


def _strip_example(definition: str) -> str:
    """Remove trailing example sentence (after the colon + 2 spaces pattern)."""
    # Cambridge format: "definition text:  Example sentence here."
    # We want only "definition text."
    m = re.match(r"^(.*?:)\s{2,}.*$", definition, re.DOTALL)
    if m:
        core = m.group(1).rstrip(":").strip()
        if len(core.split()) >= 3:
            return core + "."
    return definition


_SCONJ_WORDS = set(SUBORDINATING_CONJUNCTIONS)
_CCONJ_WORDS = set(COORDINATING_CONJUNCTIONS)


def _resolve_conjunction(word: str) -> tuple[str, str] | tuple[None, None]:
    """Cambridge uses 'conjunction' generically; disambiguate using our word lists."""
    if word in _SCONJ_WORDS:
        return ("SCONJ", "subordinating_conjunctions")
    if word in _CCONJ_WORDS:
        return ("CCONJ", "coordinating_conjunctions")
    return (None, None)


def _parse_page(word: str, html: str) -> list[dict]:
    rows: list[dict] = []
    seen_defs: set[str] = set()

    # Split into per-POS blocks
    blocks = re.split(r'<div class="pr entry-body__el">', html)
    for block in blocks[1:]:  # skip first (before first match)
        # Extract POS label
        pos_match = re.search(r'<span class="pos dpos"[^>]*>([^<]+)</span>', block)
        if not pos_match:
            continue
        pos_label = _clean(pos_match.group(1)).lower().strip()

        if pos_label == "conjunction":
            pos_tag, topic_key = _resolve_conjunction(word)
        else:
            pos_tag, topic_key = POS_MAP.get(pos_label, (None, None))

        if topic_key not in WANTED_TOPIC_KEYS:
            continue

        # Extract all definitions in this block
        for def_match in re.finditer(
            r'class="def ddef_d db"[^>]*>(.*?)</span', block, re.DOTALL
        ):
            raw_def = _clean(def_match.group(1))
            if not raw_def:
                continue

            # Normalise: strip trailing example, ensure ends with period
            definition = _strip_example(raw_def)
            # Skip very short or fragment definitions
            words = definition.split()
            if len(words) < 4:
                continue
            # Deduplicate
            norm_def = re.sub(r"\s+", " ", definition.lower().strip())
            if norm_def in seen_defs:
                continue
            seen_defs.add(norm_def)

            rows.append({
                "context_text": word,
                "notation_text": definition,
                "entry_head": f"{word} ({pos_label})",
                "pair_method": "cambridge_learner_defn_v1",
                "topic_key": topic_key,
                "source_path": BASE_URL.format(word=word),
                "examples": [],
            })

    return rows


def scrape_word_list(words: list[str], label: str) -> list[dict]:
    all_rows: list[dict] = []
    for i, word in enumerate(words):
        print(f"  [{i+1}/{len(words)}] {word} ({label})", flush=True)
        html = _fetch(word)
        if not html:
            continue
        rows = _parse_page(word, html)
        if rows:
            print(f"    → {len(rows)} definitions")
            all_rows.extend(rows)
        else:
            print(f"    → 0 definitions (skipped)")
        time.sleep(DELAY_S)
    return all_rows


def main() -> None:
    import os
    os.chdir("/home/vlad/Dev/FYP_LLM")

    output_path = Path("data/reports/cambridge_learner_pairs.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []

    print("Scraping prepositions...")
    all_rows.extend(scrape_word_list(PREPOSITIONS, "preposition"))

    print("Scraping auxiliaries...")
    all_rows.extend(scrape_word_list(AUXILIARIES, "auxiliary"))

    print("Scraping subordinating conjunctions...")
    all_rows.extend(scrape_word_list(SUBORDINATING_CONJUNCTIONS, "sconj"))

    print("Scraping coordinating conjunctions...")
    all_rows.extend(scrape_word_list(COORDINATING_CONJUNCTIONS, "cconj"))

    # Deduplicate across words
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in all_rows:
        key = f"{row['context_text']}|||{row['notation_text']}"
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    with output_path.open("w", encoding="utf-8") as f:
        for row in deduped:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nTotal pairs written: {len(deduped)}")
    print(f"Output: {output_path}")

    # Summary by topic
    from collections import Counter
    by_topic = Counter(r["topic_key"] for r in deduped)
    for topic, n in sorted(by_topic.items()):
        print(f"  {topic}: {n}")


if __name__ == "__main__":
    main()
