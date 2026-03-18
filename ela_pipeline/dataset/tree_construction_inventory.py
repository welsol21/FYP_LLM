"""Inventory sentence/phrase tree skeletons from full contract trees.

This audit works on full sentence trees produced by ``build_skeleton``.
It supports:

- phrase-only structural analysis
- collapsing short/noisy phrase nodes into their parent instead of dropping them
- limiting phrase nesting depth when building skeleton signatures
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton


DEFAULT_CHECKPOINTS = (1, 10, 25, 50, 100, 250, 500, 1000, 1500, 2000, 2500)
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?")
PREPOSITIONS = {
    "aboard",
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "amid",
    "among",
    "anti",
    "around",
    "as",
    "at",
    "before",
    "behind",
    "below",
    "beneath",
    "beside",
    "besides",
    "between",
    "beyond",
    "but",
    "by",
    "concerning",
    "considering",
    "despite",
    "down",
    "during",
    "except",
    "excepting",
    "excluding",
    "following",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "like",
    "minus",
    "near",
    "of",
    "off",
    "on",
    "onto",
    "opposite",
    "outside",
    "over",
    "past",
    "per",
    "plus",
    "regarding",
    "round",
    "save",
    "since",
    "than",
    "through",
    "throughout",
    "till",
    "to",
    "toward",
    "towards",
    "under",
    "underneath",
    "unlike",
    "until",
    "up",
    "upon",
    "versus",
    "via",
    "with",
    "within",
    "without",
}


def _norm(value: Any) -> str:
    text = str(value if value is not None else "null").strip().lower()
    return "null" if text in {"", "none", "null"} else text


def _tokenize(text: str | None) -> list[str]:
    return TOKEN_RE.findall(str(text or "").lower())


def _phrase_label(node: dict[str, Any]) -> tuple[str, str]:
    return (_norm(node.get("part_of_speech")), _norm(node.get("grammatical_role")))


def _iter_phrase_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = node.get("linguistic_elements") or []
    return [child for child in children if isinstance(child, dict) and child.get("type") == "Phrase"]


def _phrase_filter_reason(node: dict[str, Any]) -> str:
    tokens = _tokenize(node.get("content"))
    if len(tokens) <= 1:
        return "single_token_phrase"
    if len(tokens) == 2 and any(token in PREPOSITIONS for token in tokens):
        return "two_token_phrase_with_preposition"
    return "keep"


def _has_effective_phrase_descendants(node: dict[str, Any]) -> bool:
    for child in _iter_phrase_children(node):
        if _phrase_filter_reason(child) == "keep":
            return True
        if _has_effective_phrase_descendants(child):
            return True
    return False


def _effective_phrase_depth(node: dict[str, Any], current_depth: int = 0) -> int:
    max_depth = current_depth
    for child in _iter_phrase_children(node):
        if _phrase_filter_reason(child) == "keep":
            max_depth = max(max_depth, _effective_phrase_depth(child, current_depth + 1))
        else:
            max_depth = max(max_depth, _effective_phrase_depth(child, current_depth))
    return max_depth


def _normalize_phrase_node(
    node: dict[str, Any],
    *,
    depth: int,
    max_depth: int,
    stats: Counter[str],
) -> dict[str, Any]:
    stats["kept_phrase_nodes"] += 1
    truncated = depth >= max_depth and _has_effective_phrase_descendants(node)
    if truncated:
        stats["truncated_phrase_nodes"] += 1
        return {
            "label": _phrase_label(node),
            "content": str(node.get("content") or ""),
            "part_of_speech": _norm(node.get("part_of_speech")),
            "grammatical_role": _norm(node.get("grammatical_role")),
            "children": [],
            "truncated": True,
        }

    children: list[dict[str, Any]] = []
    for child in _iter_phrase_children(node):
        reason = _phrase_filter_reason(child)
        if reason == "keep":
            children.append(
                _normalize_phrase_node(
                    child,
                    depth=depth + 1,
                    max_depth=max_depth,
                    stats=stats,
                )
            )
            continue
        stats[f"collapsed_{reason}"] += 1
        children.extend(_normalize_phrase_children(child, depth=depth + 1, max_depth=max_depth, stats=stats))

    return {
        "label": _phrase_label(node),
        "content": str(node.get("content") or ""),
        "part_of_speech": _norm(node.get("part_of_speech")),
        "grammatical_role": _norm(node.get("grammatical_role")),
        "children": children,
        "truncated": False,
    }


def _normalize_phrase_children(
    node: dict[str, Any],
    *,
    depth: int,
    max_depth: int,
    stats: Counter[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for child in _iter_phrase_children(node):
        reason = _phrase_filter_reason(child)
        if reason == "keep":
            out.append(_normalize_phrase_node(child, depth=depth, max_depth=max_depth, stats=stats))
            continue
        stats[f"collapsed_{reason}"] += 1
        out.extend(_normalize_phrase_children(child, depth=depth, max_depth=max_depth, stats=stats))
    return out


def _phrase_signature(node: dict[str, Any]) -> tuple[Any, ...]:
    label = node["label"]
    if node.get("truncated"):
        return (label, "truncated")
    children = tuple(_phrase_signature(child) for child in node.get("children") or [])
    return (label, children)


def _sentence_signature(children: list[dict[str, Any]]) -> tuple[Any, ...]:
    return ("sentence", tuple(_phrase_signature(child) for child in children))


def _iter_phrase_signatures(children: list[dict[str, Any]]):
    for child in children:
        yield _phrase_signature(child)
        yield from _iter_phrase_signatures(child.get("children") or [])


def _compress_phrase_signature_presence(signature: tuple[Any, ...]) -> tuple[Any, ...]:
    label = signature[0]
    payload = signature[1] if len(signature) > 1 else ()
    if payload == "truncated":
        return (label, "truncated")
    children = tuple(sorted({_compress_phrase_signature_presence(child) for child in payload}, key=repr))
    return (label, children)


def _compress_sentence_signature_presence(signature: tuple[Any, ...]) -> tuple[Any, ...]:
    children = signature[1] if len(signature) > 1 else ()
    compressed = tuple(sorted({_compress_phrase_signature_presence(child) for child in children}, key=repr))
    return ("sentence", compressed)


def _compress_phrase_signature_bucketed(signature: tuple[Any, ...]) -> tuple[Any, ...]:
    label = signature[0]
    payload = signature[1] if len(signature) > 1 else ()
    if payload == "truncated":
        return (label, "truncated")
    child_counter: Counter[tuple[Any, ...]] = Counter(_compress_phrase_signature_bucketed(child) for child in payload)
    children = tuple(
        sorted(
            ((child_sig, "1" if count == 1 else "2+") for child_sig, count in child_counter.items()),
            key=repr,
        )
    )
    return (label, children)


def _compress_sentence_signature_bucketed(signature: tuple[Any, ...]) -> tuple[Any, ...]:
    children = signature[1] if len(signature) > 1 else ()
    child_counter: Counter[tuple[Any, ...]] = Counter(_compress_phrase_signature_bucketed(child) for child in children)
    compressed = tuple(
        sorted(
            ((child_sig, "1" if count == 1 else "2+") for child_sig, count in child_counter.items()),
            key=repr,
        )
    )
    return ("sentence", compressed)


def _iter_input_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def build_tree_inventory_report(
    *,
    input_path: str,
    spacy_model: str = "en_core_web_sm",
    max_phrase_depth: int = 2,
    sentence_limit: int | None = None,
) -> dict[str, Any]:
    rows = _iter_input_rows(Path(input_path))
    if sentence_limit is not None:
        rows = rows[: int(sentence_limit)]

    nlp = load_nlp(spacy_model)
    parse_errors = 0
    document_rows = 0
    sentence_count = 0
    sentence_signature_counts: Counter[tuple[Any, ...]] = Counter()
    sentence_presence_family_counts: Counter[tuple[Any, ...]] = Counter()
    sentence_bucketed_family_counts: Counter[tuple[Any, ...]] = Counter()
    phrase_signature_counts: Counter[tuple[Any, ...]] = Counter()
    phrase_presence_family_counts: Counter[tuple[Any, ...]] = Counter()
    phrase_bucketed_family_counts: Counter[tuple[Any, ...]] = Counter()
    effective_depth_distribution: Counter[int] = Counter()
    stats: Counter[str] = Counter()
    saturation_curve: list[dict[str, int]] = []
    seen_sentence_signatures: set[tuple[Any, ...]] = set()
    seen_sentence_presence_families: set[tuple[Any, ...]] = set()
    seen_sentence_bucketed_families: set[tuple[Any, ...]] = set()

    checkpoints = set(DEFAULT_CHECKPOINTS)

    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        document_rows += 1
        try:
            contract_doc = build_skeleton(text, nlp)
        except Exception:
            parse_errors += 1
            continue

        for sentence_node in contract_doc.values():
            sentence_count += 1
            effective_children = _normalize_phrase_children(
                sentence_node,
                depth=1,
                max_depth=max_phrase_depth,
                stats=stats,
            )
            sentence_sig = _sentence_signature(effective_children)
            sentence_signature_counts[sentence_sig] += 1
            seen_sentence_signatures.add(sentence_sig)
            sentence_presence_family = _compress_sentence_signature_presence(sentence_sig)
            sentence_presence_family_counts[sentence_presence_family] += 1
            seen_sentence_presence_families.add(sentence_presence_family)
            sentence_bucketed_family = _compress_sentence_signature_bucketed(sentence_sig)
            sentence_bucketed_family_counts[sentence_bucketed_family] += 1
            seen_sentence_bucketed_families.add(sentence_bucketed_family)
            effective_depth_distribution[_effective_phrase_depth(sentence_node, current_depth=0)] += 1
            for phrase_sig in _iter_phrase_signatures(effective_children):
                phrase_signature_counts[phrase_sig] += 1
                phrase_presence_family_counts[_compress_phrase_signature_presence(phrase_sig)] += 1
                phrase_bucketed_family_counts[_compress_phrase_signature_bucketed(phrase_sig)] += 1

            if sentence_count in checkpoints:
                saturation_curve.append(
                    {
                        "sentences": sentence_count,
                        "unique_sentence_skeletons": len(seen_sentence_signatures),
                        "unique_sentence_presence_families": len(seen_sentence_presence_families),
                        "unique_sentence_bucketed_families": len(seen_sentence_bucketed_families),
                    }
                )

    if sentence_count not in checkpoints:
        saturation_curve.append(
            {
                "sentences": sentence_count,
                "unique_sentence_skeletons": len(seen_sentence_signatures),
                "unique_sentence_presence_families": len(seen_sentence_presence_families),
                "unique_sentence_bucketed_families": len(seen_sentence_bucketed_families),
            }
        )

    return {
        "inventory_version": "tree_phrase_sentence_depth_limited_v1",
        "input_path": str(Path(input_path).resolve()),
        "spacy_model": spacy_model,
        "max_phrase_depth": int(max_phrase_depth),
        "collapse_rule": "collapse phrase into parent if token_count <= 1 or token_count == 2 with at least one preposition token",
        "document_rows": document_rows,
        "parse_errors": parse_errors,
        "sentence_nodes_total": sentence_count,
        "kept_phrase_nodes_total": int(stats["kept_phrase_nodes"]),
        "collapsed_single_token_phrase_total": int(stats["collapsed_single_token_phrase"]),
        "collapsed_two_token_phrase_with_preposition_total": int(stats["collapsed_two_token_phrase_with_preposition"]),
        "truncated_phrase_nodes_total": int(stats["truncated_phrase_nodes"]),
        "unique_sentence_skeletons_total": len(sentence_signature_counts),
        "unique_phrase_skeletons_total": len(phrase_signature_counts),
        "unique_sentence_presence_families_total": len(sentence_presence_family_counts),
        "unique_sentence_bucketed_families_total": len(sentence_bucketed_family_counts),
        "unique_phrase_presence_families_total": len(phrase_presence_family_counts),
        "unique_phrase_bucketed_families_total": len(phrase_bucketed_family_counts),
        "most_common_sentence_skeleton_count": sentence_signature_counts.most_common(1)[0][1] if sentence_signature_counts else 0,
        "most_common_phrase_skeleton_count": phrase_signature_counts.most_common(1)[0][1] if phrase_signature_counts else 0,
        "most_common_sentence_presence_family_count": sentence_presence_family_counts.most_common(1)[0][1] if sentence_presence_family_counts else 0,
        "most_common_sentence_bucketed_family_count": sentence_bucketed_family_counts.most_common(1)[0][1] if sentence_bucketed_family_counts else 0,
        "effective_phrase_depth_distribution": {str(depth): count for depth, count in sorted(effective_depth_distribution.items())},
        "saturation_curve": saturation_curve,
        "top_sentence_skeletons": [
            {"count": count, "signature": repr(signature)}
            for signature, count in sentence_signature_counts.most_common(15)
        ],
        "top_sentence_presence_families": [
            {"count": count, "signature": repr(signature)}
            for signature, count in sentence_presence_family_counts.most_common(15)
        ],
        "top_sentence_bucketed_families": [
            {"count": count, "signature": repr(signature)}
            for signature, count in sentence_bucketed_family_counts.most_common(15)
        ],
        "top_phrase_skeletons": [
            {"count": count, "signature": repr(signature)}
            for signature, count in phrase_signature_counts.most_common(15)
        ],
        "top_phrase_presence_families": [
            {"count": count, "signature": repr(signature)}
            for signature, count in phrase_presence_family_counts.most_common(15)
        ],
        "top_phrase_bucketed_families": [
            {"count": count, "signature": repr(signature)}
            for signature, count in phrase_bucketed_family_counts.most_common(15)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory sentence/phrase tree skeletons from raw sentence JSONL.")
    parser.add_argument("--input", required=True, help="Input JSONL with field 'text'")
    parser.add_argument("--output", required=True, help="Output JSON report")
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--max-phrase-depth", type=int, default=2)
    parser.add_argument("--sentence-limit", type=int, default=None)
    args = parser.parse_args()

    report = build_tree_inventory_report(
        input_path=args.input,
        spacy_model=args.spacy_model,
        max_phrase_depth=args.max_phrase_depth,
        sentence_limit=args.sentence_limit,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(output_path.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
