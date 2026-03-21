"""Extract word → definition pairs from WordNet (Princeton WordNet 3.1 via NLTK).

Output: JSONL with one entry per (lemma, pos), using the most frequent synset as
the primary definition. Includes up to 3 senses for multi-sense words.

Usage:
    python -m ela_pipeline.dataset.extract_wordnet_definitions \
        --output data/wordnet/wordnet_definitions.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from nltk.corpus import wordnet as wn

# Map WordNet POS codes to human-readable labels
_POS_LABEL = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}

# Auxiliary / function verbs that should never get a lexical note
# (their meaning at word level is irrelevant when covered by phrase-level grammar notes)
_SKIP_LEMMAS_VERB = {
    "be", "is", "am", "are", "was", "were", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did",
    "will", "would", "shall", "should", "can", "could",
    "may", "might", "must", "ought", "need", "dare",
    "get", "got", "gotten",
}


def _build_entry(lemma_str: str, pos: str, synsets: list) -> dict | None:
    if not synsets:
        return None

    # WordNet returns synsets in frequency order (most common first) — preserve that.
    primary = synsets[0]

    senses = []
    for ss in synsets[:3]:
        sense: dict = {"synset": ss.name(), "definition": ss.definition()}
        examples = ss.examples()
        if examples:
            sense["examples"] = examples[:2]
        senses.append(sense)

    return {
        "lemma": lemma_str,
        "pos": pos,
        "pos_label": _POS_LABEL.get(pos, pos),
        "primary_definition": primary.definition(),
        "primary_examples": primary.examples()[:2],
        "senses": senses,
    }


def extract_all(output_path: Path) -> None:
    # Collect unique (lemma, pos) pairs by scanning all synsets.
    unique_pairs: set[tuple[str, str]] = set()

    for synset in wn.all_synsets():
        pos = synset.pos()
        if pos == "s":
            pos = "a"
        for lemma_obj in synset.lemmas():
            lemma_str = lemma_obj.name().replace("_", " ").lower()
            if " " in lemma_str:
                continue
            if pos == "v" and lemma_str in _SKIP_LEMMAS_VERB:
                continue
            unique_pairs.add((lemma_str, pos))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with output_path.open("w", encoding="utf-8") as fh:
        for lemma_str, pos in sorted(unique_pairs):
            # wn.synsets() returns synsets in the correct frequency order for this lemma.
            wn_pos = pos if pos != "a" else wn.ADJ
            synsets = wn.synsets(lemma_str, pos=wn_pos)
            # Re-filter: drop synsets where this lemma isn't present
            synsets = [s for s in synsets if any(
                l.name().replace("_", " ").lower() == lemma_str for l in s.lemmas()
            )]
            entry = _build_entry(lemma_str, pos, synsets)
            if entry:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                total += 1

    print(f"Written {total} entries to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract WordNet word definitions.")
    parser.add_argument(
        "--output",
        default="data/wordnet/wordnet_definitions.jsonl",
        help="Output JSONL path",
    )
    args = parser.parse_args()
    extract_all(Path(args.output))


if __name__ == "__main__":
    main()
