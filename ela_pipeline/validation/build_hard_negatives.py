"""Build hard-negative phrase list from rejected candidates in inference outputs."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from typing import Any, Dict, Iterable, List

from ela_pipeline.validation.notes_quality import sanitize_note


def _iter_nodes(node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield node
    for child in node.get("linguistic_elements", []):
        if isinstance(child, dict):
            yield from _iter_nodes(child)


def _collect_rejected_candidates(payload: Any) -> Counter:
    counts: Counter = Counter()

    docs: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        docs = [payload]
    elif isinstance(payload, list):
        docs = [item for item in payload if isinstance(item, dict)]

    for doc in docs:
        for sentence_node in doc.values():
            if not isinstance(sentence_node, dict):
                continue
            for node in _iter_nodes(sentence_node):
                rejected = node.get("rejected_candidates", [])
                if not isinstance(rejected, list):
                    continue
                for item in rejected:
                    if isinstance(item, str):
                        clean = sanitize_note(item)
                        if clean:
                            counts[clean] += 1
    return counts


def build_hard_negative_payload(counts: Counter, min_count: int, max_items: int) -> Dict[str, Any]:
    items = [
        {"text": text, "count": count}
        for text, count in counts.most_common()
        if count >= min_count
    ][:max_items]
    return {
        "version": "v1",
        "source": "rejected_candidates",
        "min_count": min_count,
        "max_items": max_items,
        "phrases": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build hard-negative patterns from rejected_candidates")
    parser.add_argument("--input", required=True, help="Path to JSON contract output file")
    parser.add_argument("--output", default="artifacts/quality/hard_negative_patterns.json")
    parser.add_argument("--min-count", type=int, default=2)
    parser.add_argument("--max-items", type=int, default=200)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    counts = _collect_rejected_candidates(payload)
    result = build_hard_negative_payload(
        counts=counts,
        min_count=max(1, args.min_count),
        max_items=max(1, args.max_items),
    )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "input": args.input,
                "output": args.output,
                "unique_rejected_candidates": len(counts),
                "saved_patterns": len(result["phrases"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
