from __future__ import annotations

import argparse
import json
import sys
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ela_pipeline.dataset.sentence_patterning import extract_placeholders


def _iter_jsonl(path: Path):
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


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _label_and_reason(input_text: str, note_text: str) -> tuple[str, str]:
    """
    Heuristic labeler for the current sentence-template dataset.

    The output target remains low-entropy: LABEL|note_text.
    """
    inp = _norm(input_text).lower()
    note = _norm(note_text).lower()
    ph = set(extract_placeholders(input_text))

    def has(*needles: str) -> bool:
        return any(n in note for n in needles)

    def inp_has(*needles: str) -> bool:
        return any(n in inp for n in needles)

    # Be going to family first: this is a major source of noise if mislabeled.
    if "be going to" in note or "going to" in note or {"PRESENT_PARTICIPLE", "PARTICLE", "BASE_VERB"} <= ph:
        if has("negative", "not follows be") or inp_has("negation"):
            return "SENT_BE_GOING_TO_NEGATIVE", "be_going_to_negative"
        if has("yes-no question", "subject before the subject") or inp_has("yes-no question"):
            return "SENT_BE_GOING_TO_YES_NO", "be_going_to_yes_no"
        if has("wh-question", "wh-expression") or inp_has("wh-question"):
            return "SENT_BE_GOING_TO_WH", "be_going_to_wh"
        return "SENT_BE_GOING_TO_FUTURE", "be_going_to_future"

    # Existential there.
    if "existential there" in note or inp_has("EXISTENTIAL_THERE") or note.startswith("there "):
        if has("agreement", "agrees with the noun phrase", "form of be agrees"):
            return "SENT_EXISTENTIAL_THERE_AGREEMENT", "existential_there_agreement"
        if has("question", "yes-no question", "inverted"):
            return "SENT_EXISTENTIAL_THERE_QUESTION", "existential_there_question"
        return "SENT_EXISTENTIAL_THERE", "existential_there"

    # Extraposition / cleft.
    if has("preparatory it", "extraposition", "heavy subject that-clause", "shifts the that-clause", "it plus be, an adjective or noun"):
        return "SENT_EXTRAPOSITION_IT_THAT", "extraposition_it_that"
    if has("it-cleft", "split sentence", "cleft", "focuses one constituent", "focus time, place", "focus time or place"):
        return "SENT_CLEFT_IT", "cleft_it"

    # Passive families.
    if has("passive of reporting verbs", "reporting verb") or inp_has("PASSIVE_REPORTING"):
        return "SENT_PASSIVE_REPORTING_IT", "passive_reporting_it"
    if has("progressive passive", "passive progressive", "being passive") or inp_has("PASSIVE_PROGRESSIVE"):
        return "SENT_PASSIVE_PROGRESSIVE", "passive_progressive"
    if has("perfect passive", "passive perfect") or inp_has("PASSIVE_PERFECT"):
        return "SENT_PASSIVE_PERFECT", "passive_perfect"
    if has("agentless", "without performer", "omits the performer") or inp_has("PASSIVE_AGENTLESS"):
        return "SENT_PASSIVE_AGENTLESS", "passive_agentless"
    if has("passive", "passive voice") or inp_has("PAST_PARTICIPLE", "PASSIVE_VOICE"):
        return "SENT_PASSIVE_GENERAL", "passive_general"

    # Questions.
    if has("question tags", "question tag") or inp_has("QUESTION_TAG"):
        return "SENT_QUESTION_TAG", "question_tag"
    if has("do-support question", "question with do-support", "uses do-support to form a yes-no question", "uses do-support in the same way as yes-no questions"):
        if has("wh-question", "wh questions", "wh-word"):
            return "SENT_QUESTION_WH_DO_SUPPORT", "wh_question_do_support"
        return "SENT_QUESTION_YES_NO_DO_SUPPORT", "yes_no_question_do_support"
    if has("information question", "wh-word", "wh-question", "interrogative word"):
        if has("do-support", "no auxiliary", "lexical verbs require do-support", "uses do-support"):
            return "SENT_QUESTION_WH_DO_SUPPORT", "wh_question_do_support"
        if has("statement order", "embedded", "noun clause", "used as a noun clause"):
            return "SENT_NOUN_CLAUSE_WH", "noun_clause_wh"
        return "SENT_QUESTION_WH", "wh_question"
    if has("yes-no question", "subject-auxiliary inversion", "invert the subject and the first available auxiliary"):
        if has("do-support", "no auxiliary", "main verb have normally takes do-support", "carried by do"):
            return "SENT_QUESTION_YES_NO_DO_SUPPORT", "yes_no_question_do_support"
        return "SENT_QUESTION_YES_NO_AUX", "yes_no_question_aux"

    # Conditionals and clause relations.
    if {"IF_CLAUSE"} & ph or has("conditional", "if-clause", "unless", "even if", "only if", "provided", "providing", "as long as", "should", "were to", "had", "future time clause"):
        if has("future possibility") or inp_has("MODAL_RESULT_CLAUSE"):
            return "SENT_CONDITIONAL_PREDICTIVE", "conditional_predictive"
        if has("first conditional", "likely future result", "future result") or inp_has("WILL_RESULT_CLAUSE"):
            return "SENT_CONDITIONAL_FIRST", "conditional_first"
        if has("second conditional", "unreal possibility", "unlikely situation") or inp_has("WOULD_RESULT_CLAUSE", "COULD_RESULT_CLAUSE", "MIGHT_RESULT_CLAUSE"):
            return "SENT_CONDITIONAL_SECOND", "conditional_second"
        if has("third conditional", "unreal past", "unreal past result") or inp_has("WOULD_HAVE_RESULT_CLAUSE", "COULD_HAVE_RESULT_CLAUSE", "MIGHT_HAVE_RESULT_CLAUSE"):
            return "SENT_CONDITIONAL_THIRD", "conditional_third"
        if has("zero conditional", "general truth", "regular result") or inp_has("PRESENT_SIMPLE_GENERAL_CONDITION", "PRESENT_SIMPLE_GENERAL_RESULT"):
            return "SENT_CONDITIONAL_ZERO", "conditional_zero"
        if has("factual", "repeated pattern", "habit") or inp_has("PRESENT_SIMPLE_HABIT_CONDITION", "PRESENT_SIMPLE_HABIT_RESULT"):
            return "SENT_CONDITIONAL_FACTUAL", "conditional_factual"
        if has("even if"):
            return "SENT_CONDITIONAL_CONCESSIVE", "conditional_concessive"
        if has("only if"):
            return "SENT_CONDITIONAL_NECESSARY_CONDITION", "conditional_necessary"
        if has("provided", "providing", "as long as"):
            return "SENT_CONDITIONAL_NECESSARY_CONDITION", "conditional_provided"
        if has("future time clause") or inp_has("TIME_CLAUSE"):
            return "SENT_TIME_CLAUSE_FUTURE_REFERENCE", "time_clause_future"
        if has("should", "formal"):
            return "SENT_CONDITIONAL_FORMAL_SHOULD", "conditional_formal_should"
        if has("were to", "were-clause"):
            return "SENT_CONDITIONAL_COUNTERFACTUAL", "conditional_counterfactual"
        if has("had-inversion", "had inversion", "unreal past"):
            return "SENT_CONDITIONAL_COUNTERFACTUAL_PAST", "conditional_counterfactual_past"
        if has("modal", "may", "might") and "conditional" in note:
            return "SENT_CONDITIONAL_PRESENT_MODAL", "conditional_present_modal"
        if has("imperative", "directive"):
            return "SENT_CONDITIONAL_IMPERATIVE_RESULT", "conditional_imperative"
        return "SENT_CONDITIONAL_GENERAL", "conditional_general"

    if has("future time clause"):
        return "SENT_TIME_CLAUSE_FUTURE_REFERENCE", "time_clause_future"

    # Noun clauses / that-clauses.
    if {"THAT_CLAUSE"} & ph or has("that-clause", "that clause", "noun clause"):
        if has("heavy subject", "preparatory it", "extraposition", "shifts the that-clause"):
            return "SENT_EXTRAPOSITION_IT_THAT", "that_clause_extraposition"
        return "SENT_NOUN_CLAUSE_THAT", "noun_clause_that"

    # Negation.
    if has("negation", "negative", "not follows", "do-support"):
        if has("do-support", "uses do", "do-support clauses", "carried by do"):
            return "SENT_NEGATION_DO_SUPPORT", "negation_do_support"
        if has("auxiliary", "first auxiliary"):
            return "SENT_NEGATION_AUXILIARY", "negation_auxiliary"
        return "SENT_NEGATION_GENERAL", "negation_general"

    # Aspect / mood families.
    if has("modal perfect"):
        return "SENT_MODAL_PERFECT", "modal_perfect"
    if any(token in note for token in (" may ", " might ", " can ", " could ", " must ", " should ", " will ", " would ", " shall ")):
        return "SENT_MODAL_GENERAL", "modal_general"
    if has("modal"):
        return "SENT_MODAL_GENERAL", "modal_general"
    if has("perfect aspect", "perfect construction", "perfects"):
        return "SENT_PERFECT_GENERAL", "perfect_general"
    if has("progressive aspect", "progressive form", "ongoing", "in progress"):
        return "SENT_PROGRESSIVE_GENERAL", "progressive_general"

    # Default sentence types.
    if has("imperative", "directive"):
        return "SENT_IMPERATIVE", "imperative"
    if has("exclamative", "!"):
        return "SENT_EXCLAMATIVE", "exclamative"
    if has("active voice", "active sentence"):
        return "SENT_ACTIVE_VOICE", "active_voice"
    if has("declarative", "statement", "proposition"):
        return "SENT_DECLARATIVE", "declarative"

    # Final fallbacks based on structural clues in the input.
    if "?" in note_text:
        return "SENT_QUESTION_YES_NO_AUX", "fallback_question"
    if "IF_CLAUSE" in ph:
        return "SENT_CONDITIONAL_GENERAL", "fallback_conditional"
    if "WH_CLAUSE" in ph:
        return "SENT_QUESTION_WH", "fallback_wh"
    if "NEGATION" in ph:
        return "SENT_NEGATION_GENERAL", "fallback_negation"
    if "AUXILIARY" in ph and "PAST_PARTICIPLE" in ph:
        return "SENT_PASSIVE_GENERAL", "fallback_passive"
    return "SENT_DECLARATIVE", "fallback_declarative"


def _split_by_group(rows: list[dict[str, Any]], *, seed: int, dev_ratio: float, test_ratio: float):
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("split_group_id") or "unknown")].append(row)

    items = list(grouped.items())
    rng = random.Random(seed)
    rng.shuffle(items)

    total = len(rows)
    target_test = int(total * test_ratio)
    target_dev = int(total * dev_ratio)
    test: list[dict[str, Any]] = []
    dev: list[dict[str, Any]] = []
    train: list[dict[str, Any]] = []

    for _, group_rows in items:
        if len(test) < target_test:
            test.extend(group_rows)
        elif len(dev) < target_dev:
            dev.extend(group_rows)
        else:
            train.extend(group_rows)
    return train, dev, test


def build_dataset(source_jsonl: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_in = list(_iter_jsonl(Path(source_jsonl)))
    out: list[dict[str, Any]] = []
    label_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    input_placeholder_counts: Counter[int] = Counter()
    target_kind_counts: Counter[str] = Counter()
    skipped = 0
    seen: set[tuple[str, str]] = set()

    for row in rows_in:
        input_text = _norm(row.get("input"))
        note_text = _norm(row.get("target"))
        if not input_text or not note_text:
            skipped += 1
            continue

        label, reason = _label_and_reason(input_text, note_text)
        target = f"{label}|{note_text}"
        pair_key = (input_text, target)
        if pair_key in seen:
            continue
        seen.add(pair_key)

        label_counts[label] += 1
        reason_counts[reason] += 1
        input_placeholder_counts[len(extract_placeholders(input_text))] += 1
        target_kind_counts["templated"] += 1

        out.append(
            {
                "input": input_text,
                "target": target,
                "split_group_id": input_text,
            }
        )

    report = {
        "builder": "build_template_id_label_dataset_from_sentence_templates.py",
        "source_jsonl": str(Path(source_jsonl).resolve()),
        "rows_input": len(rows_in),
        "rows_output": len(out),
        "output_rows": len(out),
        "total": len(out),
        "total_after_balance": len(out),
        "rows_skipped_missing": skipped,
        "unique_input": len({row["input"] for row in out}),
        "unique_target": len({row["target"] for row in out}),
        "input_template_rows": len(out),
        "raw_input_rows": 0,
        "label_first_rows": len(out),
        "template_target_rows": 0,
        "raw_target_rows": 0,
        "label_counts": dict(label_counts.most_common()),
        "reason_counts": dict(reason_counts.most_common()),
        "input_placeholder_counts": {str(k): v for k, v in sorted(input_placeholder_counts.items())},
        "target_kind_counts": {"label_first": len(out)},
    }
    return out, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a label-first template-id dataset from sentence-template rows.")
    parser.add_argument(
        "--source-jsonl",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v45_paired_template_sentence_nodes_contractfix4_v1/all.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v46_template_id_label_first_v1",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    args = parser.parse_args()

    rows, report = build_dataset(args.source_jsonl)
    train, dev, test = _split_by_group(rows, seed=args.seed, dev_ratio=args.dev_ratio, test_ratio=args.test_ratio)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "all.jsonl", rows)
    _write_jsonl(out_dir / "train.jsonl", train)
    _write_jsonl(out_dir / "dev.jsonl", dev)
    _write_jsonl(out_dir / "test.jsonl", test)
    stats = {
        **report,
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
    }
    _write_json(out_dir / "stats.json", stats)

    print(json.dumps({
        "status": "ok",
        "rows": len(rows),
        "train": len(train),
        "dev": len(dev),
        "test": len(test),
        "output_dir": str(out_dir.resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
