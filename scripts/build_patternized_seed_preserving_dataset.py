"""Build a separate seed-preserving dataset with patternized note targets.

This version keeps the original note in `target_raw` and writes a
placeholder-oriented variant into `target` / `target_pattern` whenever
the note text contains concrete grammar terms, formulas, or quoted spans
that can be abstracted safely.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ela_pipeline.dataset.note_patterning import build_note_pattern


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _iter_jsonl(path: str) -> Iterable[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _replace_terms(text: str, replacements: list[tuple[str, str]]) -> tuple[str, dict[str, str]]:
    pattern_text = text
    slot_values: dict[str, str] = {}
    for phrase, slot_name in replacements:
        slot_token = "{{" + slot_name + "}}"
        regex = re.compile(re.escape(phrase), re.IGNORECASE)
        if not regex.search(pattern_text):
            continue
        pattern_text = regex.sub(slot_token, pattern_text)
        slot_values[slot_name] = phrase
    pattern_text = re.sub(r"\s+", " ", pattern_text).strip()
    pattern_text = pattern_text.replace(" .", ".").replace(" ,", ",")
    return pattern_text, slot_values


def _normalize_template_braces(text: str) -> str:
    cleaned = _normalize(text)
    if not cleaned:
        return cleaned
    cleaned = re.sub(r"\{\{\s*\{\{\s*", "{{", cleaned)
    cleaned = re.sub(r"\s*\}\}\s*\}\}", "}}", cleaned)
    cleaned = re.sub(r"\{\{\s*([A-Z0-9_]+)\s*\}\}", r"{{\1}}", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace(" .", ".").replace(" ,", ",")
    return cleaned


NOTE_REPLACEMENTS: list[tuple[str, str]] = [
    ("passive of reporting verbs", "PASSIVE_OF_REPORTING_VERBS"),
    ("modal perfect", "MODAL_PERFECT"),
    ("have + past participle", "HAVE_PLUS_PAST_PARTICIPLE"),
    ("have + past participles", "HAVE_PLUS_PAST_PARTICIPLES"),
    ("be + past participle", "BE_PLUS_PAST_PARTICIPLE"),
    ("be + past participles", "BE_PLUS_PAST_PARTICIPLES"),
    ("be + ing", "BE_PLUS_ING"),
    ("do-support", "DO_SUPPORT"),
    ("question tags", "QUESTION_TAGS"),
    ("question tag", "QUESTION_TAG"),
    ("existential there", "EXISTENTIAL_THERE"),
    ("passive voice", "PASSIVE_VOICE"),
    ("reporting verbs", "REPORTING_VERBS"),
    ("modal auxiliaries", "MODAL_AUXILIARIES"),
    ("yes-no questions", "YES_NO_QUESTIONS"),
    ("yes/no questions", "YES_NO_QUESTIONS"),
    ("wh-question", "WH_QUESTION"),
    ("if-clause", "IF_CLAUSE"),
    ("conditional clause", "CONDITIONAL_CLAUSE"),
    ("time clause", "TIME_CLAUSE"),
    ("that-clause", "THAT_CLAUSE"),
    ("wh-clause", "WH_CLAUSE"),
    ("noun clause", "NOUN_CLAUSE"),
    ("negation", "NEGATION"),
    ("negative clause", "NEGATIVE_CLAUSE"),
    ("perfect aspect", "PERFECT_ASPECT"),
    ("progressive aspect", "PROGRESSIVE_ASPECT"),
    ("imperative sentence", "IMPERATIVE_SENTENCE"),
    ("exclamative sentence", "EXCLAMATIVE_SENTENCE"),
    ("declarative sentence", "DECLARATIVE_SENTENCE"),
    ("active sentence", "ACTIVE_SENTENCE"),
    ("relative clause", "RELATIVE_CLAUSE"),
    ("prepositional phrase", "PREPOSITIONAL_PHRASE"),
    ("find or think", "FIND_OR_THINK"),
    ("were to", "WERE_TO"),
    ("there was", "EXISTENTIAL_THERE"),
    ("there were", "EXISTENTIAL_THERE"),
    ("extraposition", "EXTRAPOSITION"),
    ("cleft", "CLEFT"),
    ("noun phrase", "NOUN_PHRASE"),
    ("verb phrase", "VERB_PHRASE"),
    ("adjective phrase", "ADJECTIVE_PHRASE"),
    ("adverb phrase", "ADVERB_PHRASE"),
    ("past participle", "PAST_PARTICIPLE"),
    ("present participle", "PRESENT_PARTICIPLE"),
    ("base verb", "BASE_VERB"),
    ("infinitive", "INFINITIVE"),
    ("auxiliary", "AUXILIARY"),
    ("modal", "MODAL"),
    ("preposition", "PREPOSITION"),
    ("pronoun", "PRONOUN"),
    ("article", "ARTICLE"),
    ("determiner", "DETERMINER"),
    ("adjective", "ADJECTIVE"),
    ("adverb", "ADVERB"),
    ("subject", "SUBJECT"),
    ("object", "OBJECT"),
]


def _patternize_note_text(note_text: str, sentence_text: str, note_topic: str = "") -> tuple[str, dict[str, Any], str]:
    text = _normalize(note_text)
    topic = _normalize(note_topic).lower()
    if not text:
        return "", {}, "verbatim"

    if topic.startswith("be going to future"):
        return (
            "{{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} is used to talk about a future plan or intention.",
            {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb"},
            "rule::be_going_to_future_contract",
        )
    if topic.startswith("be going to future negative"):
        return (
            "In negative {{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} clauses, {{NEGATION}} follows {{AUXILIARY}}.",
            {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb", "NEGATION": "not"},
            "rule::be_going_to_negative_contract",
        )
    if topic.startswith("be going to yes-no question"):
        return (
            "A yes-no question with {{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} is formed by placing {{AUXILIARY}} before the {{SUBJECT}}.",
            {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb"},
            "rule::be_going_to_yes_no_contract",
        )
    if topic.startswith("be going to wh-question"):
        return (
            "A wh-question with {{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} begins with the {{WH_CLAUSE}} and keeps {{AUXILIARY}} before the {{SUBJECT}}.",
            {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb", "WH_CLAUSE": "wh-expression"},
            "rule::be_going_to_wh_contract",
        )
    if "going to" in topic and not any(marker in topic for marker in ("negative", "question", "wh-", "future time", "unless", "even if")):
        return (
            "{{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} is used to talk about a future plan or intention.",
            {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb"},
            "rule::be_going_to_future_contract",
        )

    # 1) Specific note-family patterns with higher signal.
    low = text.lower()
    if "modal perfect" in low or ("should have" in low and "past event" in low):
        return (
            "{{MODAL}} have + {{PAST_PARTICIPLE}} expresses modality about a past event.",
            {"MODAL": "modal", "PAST_PARTICIPLE": "past participle"},
            "rule::modal_perfect",
        )
    if "question tags" in low and ("auxiliary" in low or "pronoun" in low):
        return (
            "Question tags repeat {{AUXILIARY}} and use {{PRONOUN}} as the pronoun subject.",
            {"AUXILIARY": "auxiliary", "PRONOUN": "pronoun"},
            "rule::question_tags",
        )
    if "existential there" in low:
        return (
            "Existential there introduces {{NOUN_PHRASE}} as new information.",
            {"NOUN_PHRASE": "noun phrase"},
            "rule::existential_there",
        )
    if "passive of reporting verbs" in low:
        return (
            "The passive of {{REPORTING_VERB}} is often used in impersonal it structures when the source of the report is general or already understood.",
            {"REPORTING_VERB": "reporting verbs"},
            "rule::passive_reporting_verbs",
        )
    if "find or think" in low:
        return (
            "With {{FIND_OR_THINK}}, it can stand as anticipatory object before an adjective and infinitive or clause.",
            {"FIND_OR_THINK": "find or think"},
            "rule::find_think_object",
        )
    if "were to" in low and "infinitive" in low:
        return (
            "{{WERE_TO}} + {{INFINITIVE}} is a formal way to present a remote future possibility.",
            {"WERE_TO": "were to", "INFINITIVE": "infinitive"},
            "rule::were_to",
        )
    if low.startswith("be going to is used to talk about a future plan or intention"):
        return (
            "{{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} is used to talk about a future plan or intention.",
            {"AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb"},
            "rule::be_going_to_future",
        )
    if low.startswith("in negative be going to clauses, not follows be"):
        return (
            "In negative {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} clauses, {{NEGATION}} follows {{AUXILIARY}}.",
            {"AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb", "NEGATION": "not"},
            "rule::be_going_to_negative",
        )
    if low.startswith("a yes-no question with be going to is formed by placing be before the subject"):
        return (
            "A yes-no question with {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} is formed by placing {{AUXILIARY}} before the {{SUBJECT}}.",
            {"AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb", "SUBJECT": "subject"},
            "rule::be_going_to_yes_no",
        )
    if low.startswith("a wh-question with be going to begins with the wh-expression and keeps be before the subject"):
        return (
            "A wh-question with {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} begins with the {{WH_CLAUSE}} and keeps {{AUXILIARY}} before the {{SUBJECT}}.",
            {"AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb", "WH_CLAUSE": "wh-expression", "SUBJECT": "subject"},
            "rule::be_going_to_wh",
        )
    if low.startswith("a future time clause uses the simple present after words like before, after, and when rather than will or be going to"):
        return (
            "A future {{TIME_CLAUSE}} uses the simple present after words like before, after, and when rather than will or {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}}.",
            {"TIME_CLAUSE": "time clause", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb"},
            "rule::future_time_clause",
        )
    if low.startswith("in existential there clauses, the form of be agrees with the noun phrase that follows it"):
        return (
            "In existential {{EXISTENTIAL_THERE}} clauses, the form of {{AUXILIARY}} agrees with the {{NOUN_PHRASE}} that follows it.",
            {"EXISTENTIAL_THERE": "there", "AUXILIARY": "be", "NOUN_PHRASE": "noun phrase"},
            "rule::existential_there_agreement",
        )
    if low.startswith("there is introduces the existence of a singular thing in a place or situation"):
        return (
            "{{EXISTENTIAL_THERE}} {{AUXILIARY}} introduces the existence of a singular thing in a place or situation.",
            {"EXISTENTIAL_THERE": "there", "AUXILIARY": "is"},
            "rule::existential_there_introduces",
        )
    if low.startswith("there plus be introduces the existence or presence of something and makes the following noun phrase new information"):
        return (
            "{{EXISTENTIAL_THERE}} plus {{AUXILIARY}} introduces the existence or presence of something and makes the following {{NOUN_PHRASE}} new information.",
            {"EXISTENTIAL_THERE": "there", "AUXILIARY": "be", "NOUN_PHRASE": "noun phrase"},
            "rule::existential_there_plus_be",
        )
    if low.startswith("a yes-no question is formed by inverting the subject and the first available auxiliary or main be verb"):
        return (
            "A yes-no question is formed by inverting the {{SUBJECT}} and the first available {{AUXILIARY}} or main {{AUXILIARY}} verb.",
            {"SUBJECT": "subject", "AUXILIARY": "auxiliary"},
            "rule::yes_no_question",
        )
    if low.startswith("in an information question, the wh-expression is fronted and the clause keeps inverted question order"):
        return (
            "In an information question, the {{WH_CLAUSE}} is fronted and the clause keeps inverted question order.",
            {"WH_CLAUSE": "wh-expression"},
            "rule::information_question",
        )
    if low.startswith("wh-questions with lexical verbs require do-support in the same way as yes-no questions"):
        return (
            "Wh-questions with lexical verbs require {{DO_SUPPORT}} in the same way as yes-no questions.",
            {"DO_SUPPORT": "do-support"},
            "rule::wh_question_do_support",
        )
    if low.startswith("when no auxiliary is available, an object wh-question uses do-support after the wh-expression is fronted"):
        return (
            "When no {{AUXILIARY}} is available, an object {{WH_CLAUSE}} uses {{DO_SUPPORT}} after the {{WH_CLAUSE}} is fronted.",
            {"AUXILIARY": "auxiliary", "WH_CLAUSE": "wh-expression", "DO_SUPPORT": "do-support"},
            "rule::object_wh_do_support",
        )

    # 2) General term replacements for grammar families and form labels.
    pattern_text, slot_values = _replace_terms(text, NOTE_REPLACEMENTS)
    if pattern_text != text:
        return _normalize_template_braces(pattern_text), slot_values, "rule::term_slots"

    # 3) Quoted fragments from the note text.
    note_pattern = build_note_pattern(
        note_text=text,
        sentence_text=sentence_text,
        slot_template_text="",
        slot_values=None,
    )
    pattern_text = _normalize_template_braces(note_pattern.get("pattern_text"))
    slot_values = dict(note_pattern.get("slot_values") or {})
    pattern_source = _normalize(note_pattern.get("pattern_source")) or "verbatim"
    return pattern_text, slot_values, pattern_source


def _patternize_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_target = _normalize(row.get("target"))
    sentence_text = _normalize(row.get("sentence_text"))
    note_topic = _normalize(row.get("note_topic"))

    pattern_text, slot_values, pattern_source = _patternize_note_text(raw_target, sentence_text, note_topic)
    pattern_low = pattern_text.lower()
    topic_low = note_topic.lower()
    raw_low = raw_target.lower()
    if "going to" in pattern_low or "am/is/are going to" in pattern_low or "be going to" in pattern_low:
        if "negative" in topic_low or "negative" in raw_low or "negative" in pattern_low:
            pattern_text = "In negative {{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} clauses, {{NEGATION}} follows {{AUXILIARY}}."
            slot_values = {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb", "NEGATION": "not"}
            pattern_source = "rule::be_going_to_negative_contract"
        elif "wh" in topic_low or "wh-question" in raw_low or "wh-question" in pattern_low:
            pattern_text = "A wh-question with {{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} begins with the {{WH_CLAUSE}} and keeps {{AUXILIARY}} before the {{SUBJECT}}."
            slot_values = {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb", "WH_CLAUSE": "wh-expression"}
            pattern_source = "rule::be_going_to_wh_contract"
        elif "question" in topic_low or "yes-no" in raw_low or "question" in pattern_low:
            pattern_text = "A yes-no question with {{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} is formed by placing {{AUXILIARY}} before the {{SUBJECT}}."
            slot_values = {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb"}
            pattern_source = "rule::be_going_to_yes_no_contract"
        else:
            pattern_text = "{{SUBJECT}} {{AUXILIARY}} {{PRESENT_PARTICIPLE}} {{PARTICLE}} {{BASE_VERB}} is used to talk about a future plan or intention."
            slot_values = {"SUBJECT": "subject", "AUXILIARY": "be", "PRESENT_PARTICIPLE": "going", "PARTICLE": "to", "BASE_VERB": "verb"}
            pattern_source = "rule::be_going_to_future_contract"
    if not pattern_text:
        pattern_text = raw_target
        pattern_source = "verbatim"
    pattern_text = _normalize_template_braces(pattern_text)

    out = dict(row)
    out["target_raw"] = raw_target
    out["target_pattern"] = pattern_text
    out["target_pattern_slots"] = slot_values
    out["target_pattern_source"] = pattern_source
    out["target"] = pattern_text
    out["target_rendered"] = raw_target
    out["target_is_patternized"] = pattern_source != "verbatim"
    return out


def build_patternized_dataset(
    *,
    train_path: str,
    dev_path: str,
    test_path: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    splits = {
        "train": [_patternize_row(row) for row in _iter_jsonl(train_path)],
        "dev": [_patternize_row(row) for row in _iter_jsonl(dev_path)],
        "test": [_patternize_row(row) for row in _iter_jsonl(test_path)],
    }
    all_rows = splits["train"] + splits["dev"] + splits["test"]

    source_counts = Counter(str(row.get("target_pattern_source") or "") for row in all_rows)
    patternized_rows = sum(1 for row in all_rows if row.get("target_is_patternized"))
    placeholder_rows = sum(1 for row in all_rows if "{{" in str(row.get("target_pattern") or ""))
    unique_pattern_texts = len({str(row.get("target_pattern") or "") for row in all_rows if str(row.get("target_pattern") or "")})

    report = {
        "builder": "seed_preserving_sentence_dataset_patternized_v2",
        "input_train": str(Path(train_path).resolve()),
        "input_dev": str(Path(dev_path).resolve()),
        "input_test": str(Path(test_path).resolve()),
        "rows_total": len(all_rows),
        "total": len(all_rows),
        "total_after_balance": len(all_rows),
        "train": len(splits["train"]),
        "dev": len(splits["dev"]),
        "test": len(splits["test"]),
        "patternized_rows": patternized_rows,
        "placeholder_rows": placeholder_rows,
        "unique_pattern_texts": unique_pattern_texts,
        "pattern_source_counts": dict(source_counts.most_common()),
    }
    return splits, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a patternized version of the seed-preserving dataset.")
    parser.add_argument(
        "--train",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v15/train.jsonl",
    )
    parser.add_argument(
        "--dev",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v15/dev.jsonl",
    )
    parser.add_argument(
        "--test",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v15/test.jsonl",
    )
    parser.add_argument(
        "--out-dir",
        default="data/processed_sentence_seed/seed_preserving_sentence_dataset_v16_patternized_v2",
    )
    args = parser.parse_args()

    splits, report = build_patternized_dataset(train_path=args.train, dev_path=args.dev, test_path=args.test)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(str(out_dir / "train.jsonl"), splits["train"])
    _write_jsonl(str(out_dir / "dev.jsonl"), splits["dev"])
    _write_jsonl(str(out_dir / "test.jsonl"), splits["test"])
    _write_jsonl(str(out_dir / "all.jsonl"), splits["train"] + splits["dev"] + splits["test"])
    _write_json(str(out_dir / "stats.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
