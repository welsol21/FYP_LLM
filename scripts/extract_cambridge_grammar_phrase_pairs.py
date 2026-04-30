"""Scrape Cambridge Grammar Today phrase-type pages for (note, sentence) training pairs.

Strategy:
  1. Parse HTML preserving order of <p> (notes) and <blockquote> (examples).
  2. For each blockquote that contains a full sentence (≥6 words, ends with .!?),
     pair it with the most recent preceding <p> that has grammatical content.
  3. This gives locally-coherent (note, sentence) pairs rather than a noisy
     cross-product of all notes with all examples.

Output schema matches existing SOURCES:
  topic_key, context_text (example sentence), notation_text (grammar note),
  entry_head, source_path, pair_method="cambridge_grammar_v2"
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Optional

BASE = "https://dictionary.cambridge.org/us/grammar/british-grammar/"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/109.0"
DELAY_S = 1.0

PAGES: list[tuple[str, str]] = [
    ("noun-phrases",                                        "noun_phrase"),
    ("noun-phrases-uses",                                   "noun_phrase"),
    ("noun-phrases-complements",                            "noun_phrase"),
    ("noun-phrases-postmodifiers",                          "noun_phrase"),
    ("noun-phrases-premodifiers-big-good-red",              "noun_phrase"),
    ("noun-phrases-determiners-a-the-my-his-some-this-etc", "noun_phrase"),
    ("noun-phrases-noun-phrases-and-verbs",                 "noun_phrase"),
    ("verb-phrases",                                        "verb_phrase"),
    ("verb-phrases-verb-phrases",                           "verb_phrase"),
    ("prepositional-phrases",                               "prepositional_phrases"),
    ("prepositional-phrases-prepositional-phrases-and-verb-phrases", "prepositional_phrases"),
    ("adjective-phrases",                                   "adjective_phrase"),
    ("adjective-phrases-adjective-phrases-and-noun-phrases","adjective_phrase"),
    ("adverb-phrases",                                      "adverb_phrase"),
    ("adverb-phrases-position",                             "adverb_phrase"),
    ("non-finite-clauses",                                  "participle_phrase"),
]

MIN_REAL_BYTES = 300_000

_WS = re.compile(r"\s+")
# Bracket role annotations like [MV], [AUX], [DET], [ADJ], [H], [PM (clause)], etc.
_BRACKET_ANNO = re.compile(r"\[[A-Z]{1,4}(?:\s+\([^)]+\))?\]")
_JUNK_RE = re.compile(
    r"See also:|Test your vocabulary|Word of the Day|About this Blog|"
    r"New Words|Learn more|Sign up|Log in|Cambridge Dictionary\+Plus",
    re.I,
)
_GRAMMAR_TERMS = re.compile(
    r"\b(phrase|clause|noun|verb|adjective|adverb|preposition|pronoun|"
    r"subject|object|modifier|auxiliary|modal|passive|active|tense|"
    r"determiner|complement|predicate|dependent|head|postmodifier|"
    r"premodifier|non-finite|participle|infinitive|gerund)\b",
    re.I,
)


def _fetch(slug: str) -> Optional[str]:
    url = BASE + slug
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            if len(raw) < MIN_REAL_BYTES:
                return None
            return raw.decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  WARN fetch {slug}: {exc}")
        return None


def _strip_tags(html: str) -> str:
    """Remove all HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = _WS.sub(" ", text).strip()
    return text


def _clean_sentence(raw: str) -> str:
    """Clean an example sentence: remove bracket annotations, normalise space."""
    text = _BRACKET_ANNO.sub("", raw)
    # Remove parenthetical labels like "(preposition + noun phrase)"
    text = re.sub(r"\([^)]{3,60}\)", "", text)
    text = _WS.sub(" ", text).strip()
    return text


def _is_full_sentence(text: str) -> bool:
    """True if the text looks like a complete sentence (not a phrase fragment)."""
    words = text.split()
    if len(words) < 6:
        return False
    if not re.search(r"[.!?]$", text):
        return False
    if _JUNK_RE.search(text):
        return False
    # Must start with a capital letter (rules out "Not: ..." negative examples)
    if not text[0].isupper():
        return False
    # Reject negative examples (Cambridge uses "Not:" to show incorrect usage)
    if re.match(r"Not:", text):
        return False
    return True


def _is_good_note(text: str) -> bool:
    """True if the paragraph looks like a useful pedagogical note."""
    # Normalise trailing colon (notes often end with ':' before an example list)
    norm = text.rstrip()
    if norm.endswith(":"):
        norm = norm[:-1].rstrip() + "."
    words = norm.split()
    if len(words) < 8 or len(words) > 80:
        return False
    if not re.search(r"[.!?]$", norm):
        return False
    if _JUNK_RE.search(norm):
        return False
    return bool(_GRAMMAR_TERMS.search(norm))


def _extract_pairs(html: str, slug: str, topic_key: str) -> list[dict]:
    """
    Walk the HTML in document order:
      - <p class="p dp"> → candidate note paragraph
      - <blockquote>     → example sentence(s)
    For each full-sentence example, pair with the most recent good note.
    """
    # Strip scripts / styles
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)

    # Find grammar content boundaries
    start = 0
    for marker in ("from English Grammar Today", "lmt-15", "egbt"):
        idx = html.find(marker)
        if idx >= 0:
            start = idx
            break
    for stopper in ("Word of the Day", "About this Blog", "Cambridge Dictionary +Plus",
                    "Test your vocabulary"):
        idx = html.find(stopper, start)
        if idx >= 0:
            html = html[:idx]
            break

    body = html[start:]

    # Build ordered list of (kind, text) items.
    # Examples live inside <blockquote> tags.
    # Notes are standalone <p class="p dp"> tags (NOT inside blockquotes).
    # Strategy: replace each <blockquote> with a unique placeholder, collect
    # blockquote content separately, then parse the resulting HTML in order.

    blockquotes: list[str] = []  # sentence text for each placeholder

    def _replace_bq(m: re.Match) -> str:  # type: ignore[type-arg]
        inner = m.group(1)
        text = _clean_sentence(_strip_tags(inner))
        blockquotes.append(text)
        return f"\x00BQ{len(blockquotes) - 1}\x00"

    body_subst = re.sub(
        r"<blockquote[^>]*>(.*?)</blockquote>", _replace_bq, body, flags=re.DOTALL
    )

    items: list[tuple[str, str]] = []

    # Walk the substituted body in document order
    # Match standalone <p class="p dp"> tags and BQ placeholders
    for m in re.finditer(
        r'(<p\s[^>]*class="p dp"[^>]*>.*?</p>|\x00BQ(\d+)\x00)',
        body_subst, re.DOTALL
    ):
        tag = m.group(1)
        if tag.startswith("\x00BQ"):
            idx = int(m.group(2))
            text = blockquotes[idx]
            if text:
                items.append(("example", text))
        else:
            raw = _strip_tags(tag)
            if not raw:
                continue
            # Strip parenthetical structure labels like "(preposition + noun phrase)"
            # before deciding note vs example — labels contain grammar terms and would
            # cause example sentences to be misclassified as notes.
            raw_no_label = re.sub(r"\([^)]{3,60}\)", "", raw)
            raw_no_label = _WS.sub(" ", raw_no_label).strip()
            if _is_good_note(raw_no_label):
                items.append(("note", raw_no_label))
            else:
                clean = _clean_sentence(raw)
                if clean:
                    items.append(("example", clean))

    # Walk in document order.
    # Use a sliding window: group consecutive examples with their nearest note
    # (either the note immediately before OR immediately after the group).
    rows: list[dict] = []
    url = BASE + slug
    seen: set[str] = set()

    # Build segments: list of (note, [examples])
    # Strategy: forward pass — assign each example to the most recent preceding note.
    # If no note seen yet, defer examples and assign them to the first note found after.
    pending_examples: list[str] = []  # examples seen before first note
    current_note: Optional[str] = None

    def _emit(sentence: str, note: str) -> None:
        if not _is_full_sentence(sentence):
            return
        key = f"{sentence}|||{note}"
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "topic_key": topic_key,
            "context_text": sentence,
            "notation_text": note,
            "entry_head": slug.replace("-", " "),
            "source_path": url,
            "pair_method": "cambridge_grammar_v2",
            "examples": [],
        })

    for kind, text in items:
        if kind == "note":
            # Normalise trailing colon to period for storage
            note_text = text.rstrip()
            if note_text.endswith(":"):
                note_text = note_text[:-1].rstrip() + "."
            # Flush pending examples to this newly-found note
            if current_note is None:
                for ex in pending_examples:
                    _emit(ex, note_text)
                pending_examples = []
            current_note = note_text
        else:  # example
            if current_note is not None:
                _emit(text, current_note)
            else:
                pending_examples.append(text)

    return rows


def main() -> None:
    import os
    os.chdir("/home/vlad/Dev/FYP_LLM")

    output_path = Path("data/reports/cambridge_grammar_phrase_pairs.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    seen_global: set[str] = set()

    for i, (slug, topic_key) in enumerate(PAGES):
        print(f"  [{i+1}/{len(PAGES)}] {slug} ({topic_key})", flush=True)
        html = _fetch(slug)
        if not html:
            print(f"    → skipped (no content)")
            continue
        rows = _extract_pairs(html, slug, topic_key)
        for row in rows:
            key = f"{row['context_text']}|||{row['notation_text']}"
            if key not in seen_global:
                seen_global.add(key)
                all_rows.append(row)
        print(f"    → {len(rows)} pairs ({len(all_rows)} total)")
        time.sleep(DELAY_S)

    with output_path.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nTotal pairs written: {len(all_rows)}")
    print(f"Output: {output_path}")

    from collections import Counter
    by_topic = Counter(r["topic_key"] for r in all_rows)
    for t, n in sorted(by_topic.items()):
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
