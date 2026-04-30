"""Extract (example_text, note) training pairs from Leech (2006) A Glossary of English Grammar.

Algorithm (per entry):
  1. Entry head (bold at left margin) = primary term.
  2. Within the entry, walk spans in order.
     - Italic span = example candidate.
     - Bold span inline = cross-reference sub-term.
     - Regular span = definition text.
  3. Split definition into atomic sentences; filter junk.
  4. Emit all (example, note_sentence) pairs — let build_dataset.py
     decide whether each example is Word / Phrase / Sentence via spaCy.
  5. Additional extraction: "for example X" and "Compare: A with B" patterns.

Output: data/reports/leech_glossary_pairs.jsonl
  Fields: example_text, note, entry_head, topic_key, source_id, pair_method
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

PDF_PATH = "/home/vlad/winshare/books/Leech G. - A Glossary of English Grammar - (Glossaries in Linguistics) - 2006.pdf"
GLOSS_START_PAGE = 11
GLOSS_END_PAGE = 134

SOURCE_ID = "leech_glossary_2006"
PAIR_METHOD = "leech_glossary_v1"

BOLD_BIT = 2 ** 4
ITALIC_BIT = 2 ** 1

# ── Topic map ─────────────────────────────────────────────────────────────────
TOPIC_MAP: Dict[str, Tuple[str, str]] = {
    # Phrase
    "adjective phrase": ("Phrase", "adjective_phrase"),
    "adjectival phrase": ("Phrase", "adjective_phrase"),
    "adjectival clause": ("Phrase", "adjective_phrase"),
    "adverb phrase": ("Phrase", "adverb_phrase"),
    "adverbial phrase": ("Phrase", "adverb_phrase"),
    "noun phrase": ("Phrase", "noun_phrase"),
    "nominal phrase": ("Phrase", "noun_phrase"),
    "nominal clause": ("Phrase", "noun_phrase"),
    "prepositional phrase": ("Phrase", "prepositional_phrases"),
    "verb phrase": ("Phrase", "verb_phrase"),
    "verbal group": ("Phrase", "verb_phrase"),
    "participial": ("Phrase", "participle_phrase"),
    "participial phrase": ("Phrase", "participle_phrase"),
    "non-finite clause": ("Phrase", "participle_phrase"),
    "infinitival clause": ("Phrase", "infinitival_clause"),
    "infinitive clause": ("Phrase", "infinitival_clause"),
    "comparative phrase": ("Phrase", "comparative_phrase"),
    "comparative clause": ("Phrase", "comparative_phrase"),
    "apposition": ("Phrase", "noun_phrase"),
    # Sentence
    "passive": ("Sentence", "passive_voice"),
    "passive voice": ("Sentence", "passive_voice"),
    "active, active voice": ("Sentence", "passive_voice"),
    "agentless passive": ("Sentence", "passive_voice"),
    "progressive": ("Sentence", "progressive"),
    "present progressive": ("Sentence", "progressive"),
    "past progressive": ("Sentence", "progressive"),
    "continuous": ("Sentence", "progressive"),
    "present continuous": ("Sentence", "progressive"),
    "perfect": ("Sentence", "perfect"),
    "present perfect": ("Sentence", "perfect"),
    "past perfect": ("Sentence", "perfect"),
    "future perfect": ("Sentence", "perfect"),
    "pluperfect": ("Sentence", "perfect"),
    "conditional clause": ("Sentence", "conditional_sentences"),
    "first conditional": ("Sentence", "conditional_sentences"),
    "second conditional": ("Sentence", "conditional_sentences"),
    "third conditional": ("Sentence", "conditional_sentences"),
    "hypothetical": ("Sentence", "conditional_sentences"),
    "hypothetical past": ("Sentence", "conditional_sentences"),
    "relative clause": ("Sentence", "relative_clauses"),
    "defining relative clause": ("Sentence", "relative_clauses"),
    "non-defining relative clause": ("Sentence", "relative_clauses"),
    "restrictive and non-restrictive relative clauses": ("Sentence", "relative_clauses"),
    "integrated relative clause": ("Sentence", "relative_clauses"),
    "supplementary relative clause": ("Sentence", "relative_clauses"),
    "sentential relative clause": ("Sentence", "relative_clauses"),
    "zero relative clause": ("Sentence", "relative_clauses"),
    "content clause": ("Sentence", "that_clause"),
    "complement clause": ("Sentence", "that_clause"),
    "noun clause": ("Sentence", "that_clause"),
    "cleft construction": ("Sentence", "cleft_construction"),
    "pseudo-cleft construction": ("Sentence", "cleft_construction"),
    "interrogative": ("Sentence", "interrogative"),
    "interrogative clause": ("Sentence", "interrogative"),
    "alternative question": ("Sentence", "interrogative"),
    "direct question": ("Sentence", "interrogative"),
    "echo question": ("Sentence", "wh_question"),
    "tag question": ("Sentence", "question_tags"),
    "reported speech": ("Sentence", "reported_speech"),
    "indirect speech": ("Sentence", "reported_speech"),
    "reported command": ("Sentence", "reported_speech"),
    "reported question": ("Sentence", "reported_speech"),
    "reported statement": ("Sentence", "reported_speech"),
    "coordination": ("Sentence", "coordination"),
    "coordinate clause": ("Sentence", "coordination"),
    "subordinate clause": ("Sentence", "subordination"),
    "adverbial clause": ("Sentence", "adverbial_clause"),
    "concessive adverbial, concessive clause": ("Sentence", "adverbial_clause"),
    "existential construction": ("Sentence", "existential"),
    "imperative": ("Sentence", "imperative"),
    "exclamative, exclamative clause": ("Sentence", "exclamative"),
    "double negative": ("Sentence", "double_negatives"),
    "negation, negative": ("Sentence", "negation"),
    "inversion": ("Sentence", "inversion"),
    # Word
    "adjective": ("Word", "ADJ"),
    "attributive adjective": ("Word", "ADJ"),
    "predicative adjective": ("Word", "ADJ"),
    "gradable adjectives": ("Word", "ADJ"),
    "adverb": ("Word", "ADV"),
    "degree adverb/adverbial": ("Word", "ADV"),
    "frequency adverb/adverbial": ("Word", "ADV"),
    "manner adverb/adverbial": ("Word", "ADV"),
    "preposition": ("Word", "ADP"),
    "prepositional adverb": ("Word", "ADP"),
    "complex conjunction/preposition": ("Word", "ADP"),
    "conjunction": ("Word", "CCONJ"),
    "coordinating conjunction, coordinator": ("Word", "CCONJ"),
    "subordinating conjunction": ("Word", "SCONJ"),
    "pronoun": ("Word", "PRON"),
    "personal pronouns": ("Word", "PRON"),
    "demonstrative pronoun": ("Word", "PRON"),
    "indefinite pronoun, indefinite determiner": ("Word", "PRON"),
    "reflexive pronouns": ("Word", "PRON"),
    "reciprocal pronouns": ("Word", "PRON"),
    "relative pronoun": ("Word", "PRON"),
    "determiner": ("Word", "DET"),
    "articles": ("Word", "DET"),
    "definite article": ("Word", "DET"),
    "indefinite article": ("Word", "DET"),
    "demonstrative": ("Word", "DET"),
    "possessive determiner": ("Word", "DET"),
    "modal (auxiliary) (verb)": ("Word", "AUX"),
    "modal": ("Word", "AUX"),
    "auxiliary verb": ("Word", "AUX"),
    "noun": ("Word", "NOUN"),
    "abstract noun": ("Word", "NOUN"),
    "common noun": ("Word", "NOUN"),
    "collective noun": ("Word", "NOUN"),
    "count noun": ("Word", "NOUN"),
    "non-count noun": ("Word", "NOUN"),
    "proper noun": ("Word", "PROPN"),
    "verb": ("Word", "VERB"),
    "transitive verb": ("Word", "VERB"),
    "intransitive verb": ("Word", "VERB"),
    "catenative verb": ("Word", "VERB"),
    "copular verb": ("Word", "VERB"),
    "phrasal verb": ("Word", "VERB"),
    "light verb": ("Word", "VERB"),
    "numeral": ("Word", "NUM"),
    "cardinal number/numeral": ("Word", "NUM"),
    "ordinal number/numeral": ("Word", "NUM"),
    "interjection": ("Word", "INTJ"),
    "particle": ("Word", "PART"),
}

_WS = re.compile(r"\s+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
_ABBREV_RE = re.compile(r"\b(e\.g|i\.e|cf|etc|viz|vs|fig|pp|no|vol|ch)\.$", re.I)
_SEE_RE = re.compile(r"^\s*(see|another term for|see also)\b", re.I)
_FOR_EXAMPLE_RE = re.compile(
    r"for example[,:]?\s*|e\.g\.[,:]?\s*|for instance[,:]?\s*|such as\s+",
    re.I,
)
_COMPARE_RE = re.compile(r"Compare:\s*", re.I)

# Junk example filters
_SUFFIX_RE = re.compile(r"^-[a-z]")
_TILDE_RE = re.compile(r"~")
_ASTERISK_RE = re.compile(r"^\*")
_BRACKET_START_RE = re.compile(r"^[\[\|]")
_DIGIT_START_RE = re.compile(r"^\d")


def _norm(text: str) -> str:
    text = _WS.sub(" ", text)
    # Collapse PDF span-join artifacts: "good,,bad" → "good, bad"
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r",(\S)", r", \1", text)
    return text.strip()


def _is_bold(flags: int) -> bool:
    return bool(flags & BOLD_BIT)


def _is_italic(flags: int) -> bool:
    return bool(flags & ITALIC_BIT)


def _is_entry_head(span: dict) -> bool:
    text = span["text"].strip()
    if not text or len(text) < 3:
        return False
    flags = span["flags"]
    x0 = span["bbox"][0]
    return (
        _is_bold(flags)
        and not _is_italic(flags)
        and x0 < 90
        and text[0].islower()
    )


def _is_junk_example(text: str) -> bool:
    t = text.strip()
    if not t or len(t) < 2:
        return True
    if _SUFFIX_RE.match(t):
        return True
    if _TILDE_RE.search(t):
        return True
    if _ASTERISK_RE.match(t):
        return True
    if _BRACKET_START_RE.match(t):
        return True
    if _DIGIT_START_RE.match(t):
        return True
    if t.startswith("(") and t.endswith(")"):
        return True
    # Ellipsis placeholders are structural fragments, not real examples
    if "..." in t or ". . ." in t:
        return True
    # Pure punctuation / slash-separated abbreviation
    if re.match(r"^[^a-zA-Z]+$", t):
        return True
    # Very short lowercase strings are morpheme fragments (e.g. "ly", "ed", "ing")
    if len(t) <= 3 and t.isalpha() and t.islower():
        return True
    # Book-internal cross-references: "Table 1", "Figure 3", "Appendix A"
    if re.match(r"^(Table|Figure|Fig\.?|Appendix|Example)\s+[\dA-Z]", t, re.I):
        return True
    return False


def _join_spans(parts: List[str]) -> str:
    """Join span texts, inserting space where alphanumeric chars meet."""
    joined = ""
    for part in parts:
        if joined and part:
            if joined[-1].isalnum() and part[0].isalnum():
                joined += " "
            elif joined[-1] == "-" and part[0].isalnum():
                joined = joined[:-1]  # soft-hyphen removal
        joined += part
    return _norm(joined)


# ── PDF extraction ─────────────────────────────────────────────────────────────

class EntrySpan:
    """A single span with metadata."""
    __slots__ = ("text", "bold", "italic")

    def __init__(self, text: str, bold: bool, italic: bool):
        self.text = text
        self.bold = bold
        self.italic = italic


def extract_raw_entries(doc: fitz.Document) -> List[Dict]:
    """Return list of {term, spans: list[EntrySpan]}."""
    entries: List[Dict] = []
    current_term: Optional[str] = None
    current_spans: List[EntrySpan] = []

    for pg_idx in range(GLOSS_START_PAGE, GLOSS_END_PAGE + 1):
        page = doc[pg_idx]
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                line_spans = line["spans"]
                for si, span in enumerate(line_spans):
                    text = span["text"]
                    if not text.strip():
                        continue
                    flags = span["flags"]
                    bold = _is_bold(flags)
                    italic = _is_italic(flags)

                    if _is_entry_head(span):
                        if current_term:
                            entries.append({"term": current_term, "spans": current_spans[:]})
                        current_term = _norm(text)
                        current_spans = []
                    elif current_term is not None:
                        # For italic spans: peek at next span for trailing punctuation
                        if italic and si + 1 < len(line_spans):
                            ntext = line_spans[si + 1]["text"]
                            if re.match(r"^[.!?,;:\s]{1,3}$", ntext):
                                text = text + ntext
                        current_spans.append(EntrySpan(text, bold, italic))

    if current_term:
        entries.append({"term": current_term, "spans": current_spans[:]})

    return entries


# ── Entry parsing ─────────────────────────────────────────────────────────────

def _split_sentences(text: str) -> List[str]:
    parts = _SENT_SPLIT.split(text)
    result, buf = [], ""
    for part in parts:
        if buf:
            if _ABBREV_RE.search(buf.rstrip()):
                buf += " " + part
                continue
            result.append(buf.strip())
        buf = part
    if buf.strip():
        result.append(buf.strip())
    return [s for s in result if len(s.split()) >= 5]


def _clean_note(s: str) -> str:
    s = re.sub(r"\(See[^)]*\)", "", s)
    s = re.sub(r"\(see[^)]*\)", "", s)
    s = re.sub(r"\(Compare[^)]*\)", "", s)
    s = re.sub(r"\(cf\.[^)]*\)", "", s)
    # Strip trailing "Compare: ..." meta-commentary
    s = re.sub(r"\s*Compare:.*$", "", s, flags=re.DOTALL)
    # Fix double-period run-on artifacts from PDF line breaks
    s = re.sub(r"\.{2,}", ".", s)
    return _norm(s)


def _is_bad_note(s: str) -> bool:
    """Return True if a note sentence is a fragment or meta-comment."""
    if not s:
        return True
    # Fragment: starts with punctuation (mid-sentence split)
    if s[0] in ".,;:)":
        return True
    # Fragment: starts with lowercase
    if s[0].islower():
        return True
    # Numbered-list marker without context — artifact of (1)/(2) lists
    if re.match(r"^\(\d+\)", s):
        return True
    # Meta-commentary lines
    if re.match(r"^Compare\b", s):
        return True
    if re.match(r"^(See|Note:|NB:)\b", s, re.I):
        return True
    # Dangling hyphen = word truncated at PDF line break (e.g. "demon-", "pro-")
    if s.rstrip().endswith("-"):
        return True
    # Book header / page number leaked into text
    # e.g. "W 124 A GLOSSARY OF ENGLISH GRAMMAR wh-"
    if re.search(r"\bGLOSSARY\b|\bGRAMMAR\b[^a-z]", s):
        return True
    if re.search(r"\b\d{2,4}\s+[A-Z]{2,}", s):
        return True
    return False


def parse_entry(entry: Dict) -> Dict:
    """
    Parse raw entry into:
      - note_sents: list of cleaned note sentences
      - italic_examples: list of italic example texts (all sizes)
      - is_see_only: bool
    """
    spans: List[EntrySpan] = entry["spans"]

    def_parts: List[str] = []
    italic_groups: List[str] = []
    current_italic: List[str] = []

    def flush_italic() -> None:
        combined = _join_spans(current_italic)
        if not combined:
            return
        # Split comma/semicolon separated lists
        for cand in re.split(r"[,;]\s+", combined):
            cand = cand.strip(" .,;")
            if cand and not _is_junk_example(cand):
                italic_groups.append(cand)
        current_italic.clear()

    # Track when we enter a Compare/Contrast section so italic examples
    # from that clause are not collected (they are contrast examples, not
    # primary examples of the entry's own topic).
    in_compare = False

    for sp in spans:
        if sp.italic:
            if not in_compare:
                current_italic.append(sp.text)
            def_parts.append(sp.text)
        else:
            if current_italic:
                flush_italic()
            def_parts.append(sp.text)
            t = sp.text.strip()
            # Enter compare-suppression after explicit comparison triggers
            if re.search(
                r"\bCompare\b|\bContrast\b|\bcontrast with\b"
                r"|\bOn the other hand\b|\bIn contrast\b",
                t, re.I,
            ):
                in_compare = True
            # Exit suppression at a sentence boundary.
            # In this PDF the period often appears at the START of the next
            # non-italic span (e.g. ". The delayed subject …"), so check both
            # ends. Parenthetical continuations ("(where …") don't end the
            # compare clause and are excluded.
            elif in_compare and not t.startswith("("):
                if re.match(r"^[.!?]", t) or re.search(r"[.!?]\s*$", t):
                    in_compare = False

    if current_italic:
        flush_italic()

    def_text = _join_spans(def_parts)
    is_see_only = bool(_SEE_RE.match(def_text.lstrip()))

    note_sents = []
    if not is_see_only:
        for s in _split_sentences(def_text):
            s = _clean_note(s)
            if not s or len(s.split()) < 5:
                continue
            if _is_bad_note(s):
                continue
            if _SEE_RE.match(s):
                continue
            if "another term for" in s.lower():
                continue
            # Skip sentences that embed numbered lists — they're structurally
            # incomplete without the surrounding context
            if re.search(r"\(\d+\)", s):
                continue
            if len(s.split()) > 60:
                continue
            note_sents.append(s)

    return {
        "term": entry["term"],
        "note_sents": note_sents,
        "italic_examples": italic_groups,
        "is_see_only": is_see_only,
    }


# ── Additional extraction from "for example" and "Compare:" ──────────────────

def _extract_inline_examples(def_text: str) -> List[str]:
    """Pull examples from 'for example X, Y' and 'Compare: A with B' patterns."""
    extras: List[str] = []

    # "for example X, Y, Z" — take up to 3 words after the trigger
    for m in _FOR_EXAMPLE_RE.finditer(def_text):
        tail = def_text[m.end():].split(".")[0]  # up to next period
        # grab 1-6 word chunks separated by commas
        for chunk in re.split(r",\s+", tail)[:4]:
            chunk = chunk.strip(" .,;()")
            if chunk and 1 <= len(chunk.split()) <= 6 and not _is_junk_example(chunk):
                extras.append(chunk)

    return extras


# ── Category lookup ────────────────────────────────────────────────────────────

def _norm_term(term: str) -> str:
    t = term.lower().strip(" ,;.")
    t = re.sub(r"\s*\(\d+\)\s*$", "", t).strip()
    return t


def get_category(term: str) -> Optional[Tuple[str, str]]:
    norm = _norm_term(term)
    if norm in TOPIC_MAP:
        return TOPIC_MAP[norm]
    for key, val in TOPIC_MAP.items():
        if norm.startswith(key) or key.startswith(norm):
            return val
    return None


# ── Pair generation ───────────────────────────────────────────────────────────

MAX_PAIRS_PER_NOTE = 8   # cap examples per note sentence to avoid explosion

# Token-count guardrails per node_type.
# Min: prevents single words from being paired with Phrase/Sentence notes
#      (would produce a categorical mismatch when spaCy builds the RLE contract).
# Max: prevents full sentences from appearing as Phrase examples
#      (spaCy would classify them as Sentence, contradicting the Phrase note).
NODE_TYPE_MIN_TOKENS: Dict[str, int] = {
    "Word": 1,
    "Phrase": 2,
    "Sentence": 3,
}
NODE_TYPE_MAX_TOKENS: Dict[str, int] = {
    "Word": 4,
    "Phrase": 8,
    "Sentence": 999,
}


def generate_pairs(parsed: Dict, category: Tuple[str, str]) -> List[Dict]:
    node_type, topic_key = category
    note_sents = parsed["note_sents"]
    italic_examples = parsed["italic_examples"]
    term = parsed["term"]

    if not note_sents or not italic_examples:
        return []

    min_tokens = NODE_TYPE_MIN_TOKENS.get(node_type, 1)
    max_tokens = NODE_TYPE_MAX_TOKENS.get(node_type, 999)

    _punct_re = re.compile(r"[^\w\s]")
    _ex_lower = [ex.lower().strip() for ex in italic_examples]
    _ex_clean = [_punct_re.sub("", el) for el in _ex_lower]

    def _note_contains_entry_example(note_text: str, skip_ex: str) -> bool:
        note_clean = _punct_re.sub("", note_text.lower()).strip()
        skip_lower = skip_ex.lower().strip()
        skip_clean = _punct_re.sub("", skip_lower)

        # Case 1: the note text itself is a substring of some entry example.
        if len(note_clean) > 8:
            for ec in _ex_clean:
                if ec != skip_clean and note_clean in ec:
                    return True

        # Case 2: the note STARTS WITH another entry example
        # (e.g. "Come here, please.However, ..." — starts with "Come here").
        for ec in _ex_clean:
            if ec == skip_clean or len(ec) < 4:
                continue
            if note_clean.startswith(ec):
                return True

        # Case 3: the note cites another example after its last colon.
        colon_pos = note_text.rfind(":")
        if colon_pos < 0:
            return False
        after_colon = note_text[colon_pos + 1:].lower()
        for el in _ex_lower:
            if el == skip_lower or len(el.split()) < 2:
                continue
            if el in after_colon:
                return True
        return False

    seen: set = set()
    pairs: List[Dict] = []

    for note in note_sents:
        count = 0
        for ex in italic_examples:
            if count >= MAX_PAIRS_PER_NOTE:
                break
            n_tok = len(ex.split())
            if n_tok < min_tokens or n_tok > max_tokens:
                continue
            # Self-referential: example contains the note or note contains the example.
            ex_norm = _punct_re.sub("", ex.lower()).strip()
            note_norm = _punct_re.sub("", note.lower()).strip()
            if ex_norm in note_norm or note_norm in ex_norm:
                continue
            # Cross-contamination: note specifically describes a DIFFERENT
            # example from this entry — skip for the current example.
            if _note_contains_entry_example(note, ex):
                continue
            key = f"{note[:60]}|||{ex}"
            if key in seen:
                continue
            seen.add(key)
            count += 1
            pairs.append({
                "example_text": ex,
                "note": note,
                "entry_head": term,
                "topic_key": topic_key,
                "source_id": SOURCE_ID,
                "pair_method": PAIR_METHOD,
            })

    return pairs


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import os
    os.chdir("/home/vlad/Dev/FYP_LLM")

    print("Opening PDF…", flush=True)
    doc = fitz.open(PDF_PATH)

    print("Extracting raw entries…", flush=True)
    raw_entries = extract_raw_entries(doc)
    print(f"  Entry heads found: {len(raw_entries)}", flush=True)

    all_pairs: List[Dict] = []
    cat_counts: Counter = Counter()
    skipped_see = skipped_no_cat = skipped_no_pairs = 0

    for raw in raw_entries:
        parsed = parse_entry(raw)
        if parsed["is_see_only"]:
            skipped_see += 1
            continue

        cat = get_category(raw["term"])
        if cat is None:
            skipped_no_cat += 1
            continue

        pairs = generate_pairs(parsed, cat)
        if not pairs:
            skipped_no_pairs += 1
            continue

        node_type, topic_key = cat
        cat_counts[f"{node_type}/{topic_key}"] += len(pairs)
        all_pairs.extend(pairs)

    # Deduplicate globally
    seen_global: set = set()
    deduped: List[Dict] = []
    for p in all_pairs:
        key = f"{p['example_text']}|||{p['note'][:80]}"
        if key not in seen_global:
            seen_global.add(key)
            deduped.append(p)
    all_pairs = deduped

    print(f"\nStats:")
    print(f"  Skipped (see-only):    {skipped_see}")
    print(f"  Skipped (no category): {skipped_no_cat}")
    print(f"  Skipped (no pairs):    {skipped_no_pairs}")
    print(f"\nTotal pairs: {len(all_pairs)}")
    print(f"\nPer-category breakdown:")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:50s} {n}")

    out_path = Path("data/reports/leech_glossary_pairs.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in all_pairs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nWritten → {out_path}")

    # ── Sample pairs ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SAMPLE PAIRS (5 examples)")
    print("=" * 70)
    printed = 0
    seen_topics: set = set()
    for p in all_pairs:
        if p["topic_key"] not in seen_topics:
            seen_topics.add(p["topic_key"])
            print(f"\n  entry={p['entry_head']}  topic={p['topic_key']}")
            print(f"  example: {p['example_text']}")
            print(f"  note:    {p['note'][:110]}")
            printed += 1
            if printed >= 5:
                break


if __name__ == "__main__":
    main()
