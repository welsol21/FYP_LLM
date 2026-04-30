from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.dataset.sentence_patterning import build_sentence_input_pattern, extract_placeholders
from scripts.build_patternized_seed_preserving_dataset import _patternize_note_text


DEFAULT_INPUT = "data/processed_sentence_seed/seed_preserving_sentence_dataset_v15/all.jsonl"
DEFAULT_OUTPUT_DIR = "data/processed_sentence_seed/seed_preserving_sentence_dataset_v38_paired_template_sentence_nodes_v1"
PAIRED_TEMPLATE_PROMPT_VERSION = "paired_template_sentence_nodes_v1"

WS_RE = re.compile(r"\s+")
TARGET_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")

TARGET_CANONICAL_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"^in existential there (?:clauses|constructions),? (?:the form of be|agreement normally follows|the verb agrees with|the verb in there \+ be agrees with).*noun phrase.*$",
            re.IGNORECASE,
        ),
        "In existential {{EXISTENTIAL_THERE}} clauses, the form of {{AUXILIARY}} agrees with the {{NOUN_PHRASE}} that follows it.",
    ),
    (
        re.compile(
            r"^(?:there is introduces|there plus be introduces|existential there plus be introduces).*(?:existence|presence).*(?:new information|place or situation).*$",
            re.IGNORECASE,
        ),
        "{{EXISTENTIAL_THERE}} plus {{AUXILIARY}} introduces the existence or presence of something and makes the following {{NOUN_PHRASE}} new information.",
    ),
    (
        re.compile(
            r"^(?:a future )?time clause uses the simple present.*(?:rather than|instead of).*(?:will|be going to).*$",
            re.IGNORECASE,
        ),
        "A future {{TIME_CLAUSE}} uses the simple present after words like before, after, and when rather than will or {{AUXILIARY}} going to.",
    ),
    (
        re.compile(
            r"^(?:in a future )?if-clause,? english uses the simple present in the condition clause and a future form in the main clause\.?$",
            re.IGNORECASE,
        ),
        "In a future {{IF_CLAUSE}}, English uses the simple present in the condition clause and a future form in the main clause.",
    ),
    (
        re.compile(
            r"^(?:when a clause lacks an auxiliary|when no auxiliary is available).*(?:do-support|do support).*(?:negation|wh-expression).*$",
            re.IGNORECASE,
        ),
        "When a clause lacks an {{AUXILIARY}}, {{DO_SUPPORT}} is used to carry {{NEGATION}}.",
    ),
    (
        re.compile(
            r"^(?:a )?yes-no question.*(?:placing|formed by inverting|inverting).*(?:subject).*(?:auxiliary|be before).*$",
            re.IGNORECASE,
        ),
        "A yes-no question is formed by inverting the {{SUBJECT}} and the first available {{AUXILIARY}} or main {{AUXILIARY}} verb.",
    ),
    (
        re.compile(
            r"^(?:in an information question|wh-questions with lexical verbs).*(?:wh-expression|wh word|wh-word).*(?:fronted|specific missing information|do-support).*$",
            re.IGNORECASE,
        ),
        "In an information question, the {{WH_CLAUSE}} is fronted and the clause keeps inverted question order.",
    ),
]


def _norm(value: Any) -> str:
    return WS_RE.sub(" ", str(value or "").strip())


def _normalize_target_placeholders(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return "{{" + match.group(1).strip().upper() + "}}"

    return TARGET_PLACEHOLDER_RE.sub(repl, text)


def canonicalize_target_text(target_text: str) -> tuple[str, str]:
    normalized = _normalize_target_placeholders(_norm(target_text))
    if not normalized:
        return "", "empty"

    low = normalized.lower()
    if low.startswith("a wh-question with {{auxiliary}} going to begins with the {{wh_clause}} and keeps {{auxiliary}} before the {{subject}}"):
        return (
            "A wh-question with {{AUXILIARY}} going to begins with the {{WH_CLAUSE}} and keeps {{AUXILIARY}} before the {{SUBJECT}}.",
            "canonical_rule::be_going_to_wh",
        )
    if low.startswith("a yes-no question with {{auxiliary}} going to is formed by placing {{auxiliary}} before the {{subject}}"):
        return (
            "A yes-no question with {{AUXILIARY}} going to is formed by placing {{AUXILIARY}} before the {{SUBJECT}}.",
            "canonical_rule::be_going_to_yes_no",
        )
    if low.startswith("in negative {{auxiliary}} going to clauses, {{negation}} follows {{auxiliary}}"):
        return (
            "In negative {{AUXILIARY}} going to clauses, {{NEGATION}} follows {{AUXILIARY}}.",
            "canonical_rule::be_going_to_negative",
        )
    if low.startswith("{{auxiliary}} going to is used to talk about a future plan or intention"):
        return (
            "{{AUXILIARY}} going to is used to talk about a future plan or intention.",
            "canonical_rule::be_going_to_future",
        )

    for pattern, replacement in TARGET_CANONICAL_RULES:
        if pattern.match(normalized):
            return replacement, "canonical_rule::regex_family"
    return normalized, "identity"


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _input_template(sentence_node: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    template_text, slot_values, pattern_source = build_sentence_input_pattern(sentence_node)
    return template_text, slot_values, pattern_source


def _seed_row_to_training_row(row: dict[str, Any], *, nlp: Any) -> dict[str, Any] | None:
    note_text = _norm(row.get("target_rendered") or row.get("target_raw") or row.get("target") or row.get("note_text"))
    sentence_text = _norm(row.get("sentence_text") or row.get("target_content") or row.get("sentence"))
    if not note_text or not sentence_text:
        return None

    parsed = build_skeleton(sentence_text, nlp)
    if not parsed:
        return None
    sentence_node = next(iter(parsed.values()))
    input_text, input_slot_values, input_pattern_source = _input_template(sentence_node)
    input_placeholders = set(extract_placeholders(input_text))
    if not input_text:
        return None
    target_text, slot_values, pattern_source = _patternize_note_text(note_text, sentence_text)
    target_text = _norm(target_text or note_text)
    canonical_target_text, canonical_target_source = canonicalize_target_text(target_text)
    slot_values = dict(slot_values or {})
    pattern_source = _norm(pattern_source or "verbatim") or "verbatim"
    target_placeholders = set(extract_placeholders(canonical_target_text))
    target_is_template = pattern_source != "verbatim"

    source_name = _norm(row.get("source_name") or row.get("note_source_book") or row.get("source_document_id") or row.get("source") or "")
    split_group_id = _norm(row.get("split_group_id") or row.get("source_document_id") or source_name or sentence_text[:80])

    return {
        "input": input_text,
        "target": canonical_target_text,
        "split_group_id": split_group_id,
        "_meta": {
            "source_name": source_name,
            "input_pattern_source": input_pattern_source,
            "input_placeholder_count": len(input_placeholders),
            "pattern_source": pattern_source,
            "canonical_target_source": canonical_target_source,
            "slot_count": len(slot_values),
            "target_placeholder_count": len(target_placeholders),
            "template_match": target_is_template,
        },
    }


def _filter_rows_by_target_mode(rows: list[dict[str, Any]], *, target_mode: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if target_mode == "all":
        return list(rows), {"dropped_raw_targets": 0, "dropped_template_targets": 0}

    kept: list[dict[str, Any]] = []
    dropped_raw = 0
    dropped_template = 0
    for row in rows:
        is_template = "{{" in str(row.get("target") or "")
        if target_mode == "template_only":
            if is_template:
                kept.append(row)
            else:
                dropped_raw += 1
        elif target_mode == "raw_only":
            if is_template:
                dropped_template += 1
            else:
                kept.append(row)
        else:
            raise ValueError(f"Unsupported target_mode: {target_mode}")
    return kept, {
        "dropped_raw_targets": dropped_raw,
        "dropped_template_targets": dropped_template,
    }


def _drop_ambiguous_inputs(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_norm(row.get("input"))].append(row)

    kept: list[dict[str, Any]] = []
    dropped_groups = 0
    dropped_rows = 0
    max_targets_for_dropped_input = 0
    dropped_examples: list[dict[str, Any]] = []
    for input_text, group_rows in grouped.items():
        unique_targets = sorted({_norm(row.get("target")) for row in group_rows if _norm(row.get("target"))})
        if len(unique_targets) <= 1:
            kept.extend(group_rows)
            continue
        dropped_groups += 1
        dropped_rows += len(group_rows)
        max_targets_for_dropped_input = max(max_targets_for_dropped_input, len(unique_targets))
        if len(dropped_examples) < 10:
            dropped_examples.append(
                {
                    "input": input_text,
                    "target_count": len(unique_targets),
                    "targets_sample": unique_targets[:5],
                }
            )
    return kept, {
        "ambiguous_input_groups_dropped": dropped_groups,
        "ambiguous_input_rows_dropped": dropped_rows,
        "max_targets_for_dropped_input": max_targets_for_dropped_input,
        "ambiguous_input_examples": dropped_examples,
    }


def _split_by_group(rows: list[dict[str, Any]], *, seed: int, dev_ratio: float, test_ratio: float):
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("split_group_id") or "unknown")].append(row)

    group_items = list(grouped.items())
    rng = random.Random(seed)
    rng.shuffle(group_items)

    total = len(rows)
    target_test = int(total * test_ratio)
    target_dev = int(total * dev_ratio)

    test: list[dict[str, Any]] = []
    dev: list[dict[str, Any]] = []
    train: list[dict[str, Any]] = []
    for _, group_rows in group_items:
        if len(test) < target_test:
            test.extend(group_rows)
        elif len(dev) < target_dev:
            dev.extend(group_rows)
        else:
            train.extend(group_rows)
    return train, dev, test


def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (_norm(row.get("input")), _norm(row.get("target")))


def build_dataset(
    seed_notes_input: str,
    *,
    target_mode: str = "all",
    drop_ambiguous_inputs: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nlp = load_nlp("en_core_web_sm")
    seed_rows_raw = list(_iter_jsonl(Path(seed_notes_input)))
    converted: list[dict[str, Any]] = []
    input_pattern_source_counts: Counter[str] = Counter()
    target_pattern_source_counts: Counter[str] = Counter()
    slot_count_counts: Counter[int] = Counter()
    dropped_missing = 0
    input_placeholder_counts: Counter[int] = Counter()
    target_placeholder_counts: Counter[int] = Counter()
    input_placeholder_usage: Counter[str] = Counter()
    target_placeholder_usage: Counter[str] = Counter()
    template_match_counts: Counter[str] = Counter()
    canonical_target_source_counts: Counter[str] = Counter()

    for row in seed_rows_raw:
        converted_row = _seed_row_to_training_row(row, nlp=nlp)
        if not converted_row:
            dropped_missing += 1
            continue
        converted.append(converted_row)
        meta = converted_row.pop("_meta")
        input_pattern_source_counts[str(meta.get("input_pattern_source") or "node_template")] += 1
        target_pattern_source_counts[str(meta.get("pattern_source") or "verbatim")] += 1
        canonical_target_source_counts[str(meta.get("canonical_target_source") or "identity")] += 1
        slot_count_counts[int(meta.get("slot_count") or 0)] += 1
        input_placeholder_counts[int(meta.get("input_placeholder_count") or 0)] += 1
        target_placeholder_counts[int(meta.get("target_placeholder_count") or 0)] += 1
        template_match_counts[str(bool(meta.get("template_match"))).lower()] += 1
        for ph in extract_placeholders(converted_row.get("input", "")):
            input_placeholder_usage[ph] += 1
        for ph in extract_placeholders(converted_row.get("target", "")):
            target_placeholder_usage[ph] += 1

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in converted:
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)

    filtered_rows, target_mode_report = _filter_rows_by_target_mode(merged, target_mode=target_mode)
    ambiguity_report = {
        "ambiguous_input_groups_dropped": 0,
        "ambiguous_input_rows_dropped": 0,
        "max_targets_for_dropped_input": 0,
        "ambiguous_input_examples": [],
    }
    if drop_ambiguous_inputs:
        filtered_rows, ambiguity_report = _drop_ambiguous_inputs(filtered_rows)

    report = {
        "seed_rows_input": len(seed_rows_raw),
        "seed_rows_converted": len(converted),
        "seed_rows_dropped_missing": dropped_missing,
        "merged_rows": len(merged),
        "target_mode": target_mode,
        "drop_ambiguous_inputs": bool(drop_ambiguous_inputs),
        "output_rows_after_filters": len(filtered_rows),
        "unique_inputs": len({row["input"] for row in filtered_rows}),
        "unique_targets": len({row["target"] for row in filtered_rows}),
        "input_template_rows": sum(1 for row in filtered_rows if "{{" in str(row.get("input") or "")),
        "raw_input_rows": sum(1 for row in filtered_rows if "{{" not in str(row.get("input") or "")),
        "template_target_rows": sum(1 for row in filtered_rows if "{{" in str(row.get("target") or "")),
        "raw_target_rows": sum(1 for row in filtered_rows if "{{" not in str(row.get("target") or "")),
        "input_pattern_source_counts": dict(input_pattern_source_counts.most_common()),
        "target_pattern_source_counts": dict(target_pattern_source_counts.most_common()),
        "canonical_target_source_counts": dict(canonical_target_source_counts.most_common()),
        "slot_count_counts": {str(k): v for k, v in slot_count_counts.most_common()},
        "input_placeholder_counts": {str(k): v for k, v in input_placeholder_counts.most_common()},
        "target_placeholder_counts": {str(k): v for k, v in target_placeholder_counts.most_common()},
        "input_placeholder_usage_counts": dict(input_placeholder_usage.most_common()),
        "target_placeholder_usage_counts": dict(target_placeholder_usage.most_common()),
        "template_match_counts": dict(template_match_counts.most_common()),
        **target_mode_report,
        **ambiguity_report,
    }
    return filtered_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a paired-template sentence dataset with matched placeholders.")
    parser.add_argument("--seed-notes-input", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument(
        "--target-mode",
        choices=["all", "template_only", "raw_only"],
        default="all",
    )
    parser.add_argument(
        "--drop-ambiguous-inputs",
        action="store_true",
        help="Drop every input template that maps to more than one canonical target.",
    )
    args = parser.parse_args()

    rows, report = build_dataset(
        args.seed_notes_input,
        target_mode=args.target_mode,
        drop_ambiguous_inputs=bool(args.drop_ambiguous_inputs),
    )
    train, dev, test = _split_by_group(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    clean_rows = [{"input": row["input"], "target": row["target"]} for row in rows]
    clean_train = [{"input": row["input"], "target": row["target"]} for row in train]
    clean_dev = [{"input": row["input"], "target": row["target"]} for row in dev]
    clean_test = [{"input": row["input"], "target": row["target"]} for row in test]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "all.jsonl", clean_rows)
    _write_jsonl(out_dir / "train.jsonl", clean_train)
    _write_jsonl(out_dir / "dev.jsonl", clean_dev)
    _write_jsonl(out_dir / "test.jsonl", clean_test)
    _write_json(
        out_dir / "stats.json",
        {
            "builder": "build_paired_template_signature_dataset.py",
            "seed_notes_input": str(Path(args.seed_notes_input).resolve()),
            "output_rows": len(clean_rows),
            "train": len(clean_train),
            "dev": len(clean_dev),
            "test": len(clean_test),
            "prompt_template_version": PAIRED_TEMPLATE_PROMPT_VERSION,
            **report,
        },
    )
    print(json.dumps({"status": "ok", "rows": len(clean_rows), "output_dir": str(out_dir.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
