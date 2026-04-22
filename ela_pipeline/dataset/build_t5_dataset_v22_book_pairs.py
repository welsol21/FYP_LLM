"""Build T5 train/dev/test dataset from book pairs and Wiktionary.

RLE contract architecture:
- Sentence contract: content = spaCy second-level node markers (NOT {{SENTENCE}}),
  service fields (part_of_speech, grammatical_role, tense, aspect, mood, voice,
  tam_construction) from spaCy. No topic_key in contract.
- Word contract: content = actual word (NOT parametrized), service fields from spaCy.
- Phrase contract: content = {{PHRASE}}, part_of_speech inferred from topic_key,
  grammatical_role = "phrase". Trained from phrase-chapter book pairs.

Target: human-written notation (free natural language).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

ENDS_WITH_PUNCT = re.compile(r"[.!?]\s*$")
CROSS_REF_RE = re.compile(r"\(see\b|see unit\b|see section\b", re.I)
UNIT_PREFIX_RE = re.compile(r"^Unit\s+\d+[^:]*:\s*", re.I)
WS_RE = re.compile(r"\s+")

SOURCES: List[Tuple[str, str]] = [
    ("collins_cobuild_english_grammar_2011", "data/reports/collins_cobuild_2011_pairs_clean.jsonl"),
    ("cobuild_english_grammar_2017", "data/reports/cobuild_grammar_pairs_clean.jsonl"),
    ("english_grammar_in_use_5th_2019", "data/reports/english_grammar_in_use_pairs_clean.jsonl"),
    ("grammar_of_spoken_written_english", "data/reports/gswe_pairs_clean.jsonl"),
    ("longman_grammar_spoken_written_english_1999", "data/reports/lgswe_1999_pairs.jsonl"),
    ("mysteries_of_english_grammar", "data/reports/mysteries_english_grammar_pairs_clean.jsonl"),
    ("farlex_complete_english_grammar_rules_2016", "data/reports/farlex_grammar_2016_pairs.jsonl"),
]

WORD_SOURCES: List[Tuple[str, str]] = [
    ("simple_english_wiktionary", "data/reports/simplewiktionary_grammar_pairs.jsonl"),
]

PROMPT_TEMPLATE_VERSION = "rle_v1"
TASK_NAME = "generate_linguistic_note"

# Only book chapters whose notes describe sentence-level TAM/construction patterns.
# Word-level chapters (prepositions, modal definitions) are excluded —
# word contracts come exclusively from Wiktionary.
SENTENCE_TOPICS: set[str] = {
    "passive_voice",
    "perfect",
    "progressive",
    "conditional_sentences",
    "relative_clauses",
    "that_clause",
    "wh_question",
    "questions_and_negatives",
    "question_tags",
    "double_be",
    "number_agreement",
    "double_negatives",
    "shadow_pronouns",
}

# Phrase-level chapters → Phrase contracts.
# Maps topic_key → canonical POS of the phrase head.
PHRASE_TOPIC_POS: dict[str, str] = {
    "noun_phrase": "NOUN",
    "verb_phrase": "VERB",
    "adjective_phrase": "ADJ",
    "adverb_phrase": "ADV",
    "prepositional_phrases": "ADP",
    "participle_phrase": "VERB",
    "absolute_phrase": "VERB",
}
PHRASE_TOPICS: set[str] = set(PHRASE_TOPIC_POS.keys())


def _norm(s: Any) -> str:
    return WS_RE.sub(" ", str(s or "").strip())


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("||".join(parts).encode()).hexdigest()[:16]


def _clean_notation(text: str) -> str:
    text = _norm(text)
    text = UNIT_PREFIX_RE.sub("", text)
    return _norm(text)


def _is_valid_sentence(text: str) -> bool:
    text = _norm(text)
    words = text.split()
    if len(words) < 3 or len(words) > 80:
        return False
    return sum(ch.isalpha() for ch in text) >= 5


def _is_valid_note(text: str) -> bool:
    text = _norm(text)
    if len(text.split()) < 8:
        return False
    if not ENDS_WITH_PUNCT.search(text):
        return False
    if CROSS_REF_RE.search(text):
        return False
    return True


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _build_node_contract(token: Any, tam_label: str, depth: int = 0, max_depth: int = 2) -> Dict[str, Any]:
    """Recursively build an RLE node contract for a spaCy token.

    Leaf tokens → Word node (content={{WORD}}).
    Tokens with children → Phrase node (content={{PHRASE}}).
    ROOT carries the full TAM label.
    Recursion stops at max_depth to keep inputs within token budget.
    """
    children = sorted(
        [c for c in token.children if not c.is_punct and not c.is_space],
        key=lambda t: t.i,
    )
    has_children = bool(children) and depth < max_depth
    contract: Dict[str, Any] = {
        "node_type": "Phrase" if bool(children) else "Word",
        "content": "{{PHRASE}}" if bool(children) else "{{WORD}}",
        "part_of_speech": token.pos_,
        "grammatical_role": token.dep_,
    }
    if token.dep_ == "ROOT" and tam_label:
        contract["tam_construction"] = tam_label
    if has_children:
        contract["linguistic_elements"] = [
            _build_node_contract(c, tam_label, depth + 1, max_depth) for c in children
        ]
    return contract


def _build_sentence_content(doc: Any, tam_label: str) -> str:
    """Build content field of Sentence contract as serialized child node contracts.

    The Sentence's linguistic_elements are the immediate children of ROOT,
    each represented as a full recursive RLE node contract.
    Specific word forms are not included — only spaCy structural fields.
    """
    root_token = next((t for t in doc if t.dep_ == "ROOT"), None)
    if not root_token:
        return "[]"
    root_contract = _build_node_contract(root_token, tam_label)
    elements = root_contract.get("linguistic_elements", [root_contract])
    return json.dumps(elements, ensure_ascii=False, sort_keys=True)


def _parse_sentence_contract(sentence: str, nlp: Any) -> Tuple[str, Dict[str, Any]]:
    """Return (content_markers, service_fields) for a Sentence node."""
    from ela_pipeline.tam.rules import detect_tam

    doc = nlp(sentence)
    tam = detect_tam(doc)
    label = tam.label or ""
    tense = tam.short_tense or "null"

    voice = "passive" if "passive" in label else "active"
    if "perfect_progressive" in label:
        aspect = "perfect_progressive"
    elif "perfect" in label:
        aspect = "perfect"
    elif "progressive" in label:
        aspect = "progressive"
    else:
        aspect = "simple"

    root_token = next((t for t in doc if t.dep_ == "ROOT"), None)
    root_pos = root_token.pos_ if root_token else "VERB"

    content = _build_sentence_content(doc, label)
    service = {
        "part_of_speech": root_pos,
        "grammatical_role": "ROOT",
        "tense": tense,
        "aspect": aspect,
        "mood": "null",
        "voice": voice,
        "tam_construction": label,
    }
    return content, service


def _build_sentence_input(content: str, service_fields: Dict[str, Any]) -> str:
    payload = {
        "node_type": "Sentence",
        "content": content,
        "part_of_speech": service_fields.get("part_of_speech", "VERB"),
        "grammatical_role": service_fields.get("grammatical_role", "ROOT"),
        "tense": service_fields.get("tense", "null"),
        "aspect": service_fields.get("aspect", "null"),
        "mood": service_fields.get("mood", "null"),
        "voice": service_fields.get("voice", "null"),
        "tam_construction": service_fields.get("tam_construction", ""),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "task": TASK_NAME,
    }
    return f"task: {TASK_NAME} payload: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def _parse_word_contract(word: str, nlp: Any) -> Dict[str, Any]:
    """Return service fields for a Word node via spaCy."""
    doc = nlp(word)
    token = doc[0] if len(doc) > 0 else None
    return {
        "part_of_speech": token.pos_ if token else "X",
        "grammatical_role": token.dep_ if token else "dep",
    }


def _build_word_input(word: str, service_fields: Dict[str, Any]) -> str:
    payload = {
        "node_type": "Word",
        "content": word,
        "part_of_speech": service_fields.get("part_of_speech", "X"),
        "grammatical_role": service_fields.get("grammatical_role", "dep"),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "task": TASK_NAME,
    }
    return f"task: {TASK_NAME} payload: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def _build_phrase_input(topic_key: str) -> str:
    pos = PHRASE_TOPIC_POS.get(topic_key, "X")
    payload = {
        "node_type": "Phrase",
        "content": "{{PHRASE}}",
        "part_of_speech": pos,
        "grammatical_role": "phrase",
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "task": TASK_NAME,
    }
    return f"task: {TASK_NAME} payload: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def load_and_filter_phrase_pairs(base_dir: Path) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    for source_id, rel_path in SOURCES:
        path = base_dir / rel_path
        if not path.exists():
            continue
        count_out = 0
        for row in _iter_jsonl(path):
            if row.get("topic_key") not in PHRASE_TOPICS:
                continue
            note = _clean_notation(row.get("notation_text") or "")
            if not _is_valid_note(note):
                continue
            pairs.append({
                "topic_key": row["topic_key"],
                "note": note,
                "source_id": source_id,
                "entry_head": _norm(row.get("entry_head") or ""),
            })
            count_out += 1
        if count_out:
            print(f"  {source_id} (phrase): {count_out} passed filter")
    return pairs


def build_phrase_rows(pairs: List[Dict[str, Any]], max_per_target: int = 4) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    target_counts: Dict[str, int] = {}
    for pair in pairs:
        input_text = _build_phrase_input(pair["topic_key"])
        target_text = pair["note"]

        dedup_key = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        target_key = hashlib.sha1(target_text.encode()).hexdigest()
        if target_counts.get(target_key, 0) >= max_per_target:
            continue
        target_counts[target_key] = target_counts.get(target_key, 0) + 1

        rows.append({
            "id": _stable_id(pair["source_id"], pair["topic_key"], target_text),
            "input": input_text,
            "target": target_text,
            "node_type": "Phrase",
            "source_id": pair["source_id"],
            "sentence_text": pair["topic_key"],
            "entry_head": pair["entry_head"],
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "service_fields": {"part_of_speech": PHRASE_TOPIC_POS.get(pair["topic_key"], "X"), "grammatical_role": "phrase"},
        })
    return rows


def load_and_filter_pairs(base_dir: Path) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    for source_id, rel_path in SOURCES:
        path = base_dir / rel_path
        if not path.exists():
            print(f"  SKIP (not found): {path}")
            continue
        count_in = count_out = 0
        for row in _iter_jsonl(path):
            count_in += 1
            if row.get("topic_key") not in SENTENCE_TOPICS:
                continue
            sentence = _norm(row.get("context_text") or "")
            note = _clean_notation(row.get("notation_text") or "")
            if not _is_valid_sentence(sentence):
                continue
            if not _is_valid_note(note):
                continue
            pairs.append({
                "sentence": sentence,
                "note": note,
                "source_id": source_id,
                "entry_head": _norm(row.get("entry_head") or ""),
            })
            count_out += 1
        print(f"  {source_id}: {count_in} → {count_out} passed filter")
    return pairs


def build_sentence_rows(pairs: List[Dict[str, Any]], nlp: Any, max_per_target: int = 4) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    target_counts: Dict[str, int] = {}
    for pair in pairs:
        content, service = _parse_sentence_contract(pair["sentence"], nlp)
        input_text = _build_sentence_input(content, service)
        target_text = pair["note"]

        dedup_key = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        target_key = hashlib.sha1(target_text.encode()).hexdigest()
        if target_counts.get(target_key, 0) >= max_per_target:
            continue
        target_counts[target_key] = target_counts.get(target_key, 0) + 1

        rows.append({
            "id": _stable_id(pair["source_id"], pair["sentence"], target_text),
            "input": input_text,
            "target": target_text,
            "node_type": "Sentence",
            "source_id": pair["source_id"],
            "sentence_text": pair["sentence"],
            "entry_head": pair["entry_head"],
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "service_fields": service,
        })
    return rows


def load_and_filter_word_pairs(base_dir: Path) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    for source_id, rel_path in WORD_SOURCES:
        path = base_dir / rel_path
        if not path.exists():
            print(f"  SKIP (not found): {path}")
            continue
        count_in = count_out = 0
        for row in _iter_jsonl(path):
            count_in += 1
            if row.get("pair_method") != "wiktionary_defn_v1":
                continue
            word = _norm(row.get("context_text") or "")
            note = _clean_notation(row.get("notation_text") or "")
            if not word or len(word.split()) > 5:
                continue
            if len(note.split()) < 5 or not ENDS_WITH_PUNCT.search(note):
                continue
            if CROSS_REF_RE.search(note):
                continue
            pairs.append({
                "word": word,
                "note": note,
                "source_id": source_id,
                "entry_head": _norm(row.get("entry_head") or ""),
            })
            count_out += 1
        print(f"  {source_id} (word): {count_in} → {count_out} passed filter")
    return pairs


def build_word_rows(pairs: List[Dict[str, Any]], nlp: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for pair in pairs:
        service = _parse_word_contract(pair["word"], nlp)
        input_text = _build_word_input(pair["word"], service)
        target_text = pair["note"]

        dedup_key = hashlib.sha1(f"{input_text}|||{target_text}".encode()).hexdigest()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        rows.append({
            "id": _stable_id(pair["source_id"], pair["word"], target_text),
            "input": input_text,
            "target": target_text,
            "node_type": "Word",
            "source_id": pair["source_id"],
            "sentence_text": pair["word"],
            "entry_head": pair["entry_head"],
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "service_fields": service,
        })
    return rows


def split_rows(rows: List[Dict[str, Any]], seed: int = 42) -> Tuple[List, List, List]:
    rng = random.Random(seed)
    by_source: Dict[str, List] = defaultdict(list)
    for row in rows:
        by_source[row["source_id"]].append(row)

    train, dev, test = [], [], []
    for source_rows in by_source.values():
        rng.shuffle(source_rows)
        n = len(source_rows)
        n_dev = max(1, int(n * 0.1))
        n_test = max(1, int(n * 0.1))
        test.extend(source_rows[:n_test])
        dev.extend(source_rows[n_test: n_test + n_dev])
        train.extend(source_rows[n_test + n_dev:])
    return train, dev, test


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build T5 RLE v1 dataset")
    parser.add_argument("--base-dir", default="/home/vlad/Dev/FYP_LLM")
    parser.add_argument("--output-dir", default="/home/vlad/Dev/FYP_LLM/data/processed_t5_v22_book_pairs")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    output_dir = Path(args.output_dir)

    from ela_pipeline.parse.spacy_parser import load_nlp
    print("Loading spaCy model...")
    nlp = load_nlp(args.spacy_model)

    print("Loading and filtering sentence pairs...")
    pairs = load_and_filter_pairs(base_dir)
    print(f"  Total: {len(pairs)}")

    print("Building Sentence rows...")
    sentence_rows = build_sentence_rows(pairs, nlp)
    print(f"  Sentence rows after dedup+cap: {len(sentence_rows)}")

    print("Loading and filtering Phrase pairs...")
    phrase_pairs = load_and_filter_phrase_pairs(base_dir)
    print(f"  Phrase pairs: {len(phrase_pairs)}")
    phrase_rows = build_phrase_rows(phrase_pairs)
    print(f"  Phrase rows after dedup+cap: {len(phrase_rows)}")

    print("Loading and filtering Word pairs...")
    word_pairs = load_and_filter_word_pairs(base_dir)
    print(f"  Word pairs: {len(word_pairs)}")
    word_rows = build_word_rows(word_pairs, nlp)
    print(f"  Word rows after dedup: {len(word_rows)}")

    rows = sentence_rows + phrase_rows + word_rows
    train, dev, test = split_rows(rows, seed=args.seed)
    all_rows = train + dev + test

    node_counts = dict(Counter(r["node_type"] for r in all_rows))
    source_counts = dict(Counter(r["source_id"] for r in all_rows))

    stats = {
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "total": len(all_rows),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "node_counts": node_counts,
        "sources": source_counts,
    }

    write_jsonl(output_dir / "train.jsonl", train)
    write_jsonl(output_dir / "dev.jsonl", dev)
    write_jsonl(output_dir / "test.jsonl", test)
    write_jsonl(output_dir / "all.jsonl", all_rows)
    write_json(output_dir / "stats.json", stats)

    print(json.dumps(stats, ensure_ascii=False, indent=2))

    # Print a few examples
    print("\n--- Sample Sentence input ---")
    for r in sentence_rows[:2]:
        print(f"  input : {r['input'][:200]}")
        print(f"  target: {r['target'][:100]}")
        print()
    print("--- Sample Phrase input ---")
    for r in phrase_rows[:2]:
        print(f"  input : {r['input'][:200]}")
        print(f"  target: {r['target'][:100]}")
        print()
    print("--- Sample Word input ---")
    for r in word_rows[:2]:
        print(f"  input : {r['input'][:200]}")
        print(f"  target: {r['target'][:100]}")
        print()


if __name__ == "__main__":
    main()
