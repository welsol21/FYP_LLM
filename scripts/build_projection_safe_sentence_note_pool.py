"""Build a projection-safe sentence note pool for fast-track cycle 1.

The sentence projector currently indexes sentence notes by topic, so generic
topics such as `conditional_sentences` or `passive_voice` are too noisy.

This script keeps rows whose topics already map cleanly to the current
projection compatibility layer and remaps a narrow set of generic topics into
projection-safe topics using conservative sentence-shape heuristics.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_INPUT = "data/processed_sentence_seed/fasttrack_sentence_note_pool_v1.jsonl"
DEFAULT_OUTPUT_JSONL = "data/processed_sentence_seed/projection_safe_sentence_note_pool_v1.jsonl"
DEFAULT_REPORT_JSON = "data/processed_sentence_seed/projection_safe_sentence_note_pool_v1.report.json"

SAFE_TOPICS = {
    "general passive voice",
    "passive form",
    "passive without performer",
    "passive reporting it structure",
    "passive by phrase",
    "passive with instrument",
    "passive by ing method",
    "state passive with with",
    "lexically common passive",
    "question tag",
    "yes-no question",
    "yes-no question with be",
    "do-support yes-no question",
    "wh-question",
    "wh-question with do-support",
    "negative clause",
    "do-support negative clause",
    "general conditional clause",
    "unless clause",
    "if clause consequence",
    "first conditional",
    "second conditional",
    "third conditional",
    "present possibility conditional",
    "future conditional",
    "formal should conditional",
    "were-to conditional",
    "inverted conditional",
    "reduced if phrase",
    "necessary-condition clause",
    "even if clause",
    "it cleft",
    "it cleft adverbial focus",
    "it time-focus split sentence",
    "what cleft action",
    "what cleft need/want",
    "all cleft",
    "impersonal it weather",
    "impersonal it time",
    "it extraposition to infinitive",
    "it extraposition that clause",
    "it with take or cost",
    "anticipatory object it",
    "be going to future",
    "be going to future negative",
    "be going to yes-no question",
    "be going to wh-question",
    "future time clause",
    "that-clause noun clause",
    "deleted-that clause",
    "shifted that-clause",
    "wh-clause noun clause",
    "wh-clause noun clause formal",
    "existential there yes-no question",
    "maybe adverb",
    "existential there basic",
    "existential there with ing",
    "existential there agreement",
    "existential there with seem or appear",
    "existential there with passive reporting verb",
    "existential there formal literary",
}

_SPACE_RE = re.compile(r"\s+")


def _norm(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "").strip())


def _low(value: Any) -> str:
    return _norm(value).lower().replace("’", "'")


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


def _has_question_tag_pattern(text: str) -> bool:
    return bool(re.search(r",\s*[^,?!]{1,30}\?\s*$", text))


def _starts_with_yes_no_auxiliary(text: str) -> bool:
    return bool(re.match(r"^(am|is|are|was|were|do|does|did|have|has|had|can|could|will|would|should|may|might|must)\b", text))


def _looks_like_do_support_question(text: str) -> bool:
    return bool(re.match(r"^(do|does|did)\b", text))


def _starts_with_wh_question(text: str) -> bool:
    return bool(re.match(r"^(what|where|when|why|who|whom|whose|which|how)\b", text))


def _starts_with_existential_there(text: str) -> bool:
    return bool(re.match(r"^there\s+(is|are|was|were|has|have|had)\b", text))


def _looks_like_existential_there_question(text: str) -> bool:
    return bool(re.match(r"^(is|are|was|were|has|have|had)\s+there\b", text))


def _looks_like_first_conditional(text: str) -> bool:
    return " if " in f" {text} " and bool(re.search(r"\bwill\b|\bshall\b", text))


def _looks_like_second_conditional(text: str) -> bool:
    return (
        " if " in f" {text} "
        and bool(re.search(r"\bwould\b|\bcould\b|\bmight\b", text))
        and not bool(re.search(r"\b(?:would|could|might)\s+have\b", text))
    )


def _looks_like_third_conditional(text: str) -> bool:
    return (
        " if " in f" {text} "
        and bool(re.search(r"\bhad\b", text))
        and bool(re.search(r"\b(?:would|could|might)\s+have\b", text))
    )


def _looks_like_formal_should_conditional(text: str) -> bool:
    return bool(re.search(r"\bif\b.+\bshould\b", text))


def _looks_like_were_to_conditional(text: str) -> bool:
    return bool(re.search(r"\bif\b.+\bwere to\b", text))


def _looks_like_inverted_conditional(text: str) -> bool:
    return bool(re.match(r"^(should|were|had)\b", text))


def _looks_like_reduced_if_phrase(text: str) -> bool:
    return bool(re.match(r"^if\s+[a-z-]+,?", text)) and len(text.split()) <= 8


def _looks_like_necessary_condition(text: str) -> bool:
    return any(marker in f" {text} " for marker in (" provided ", " providing ", " as long as ", " only if "))


def _looks_like_even_if(text: str) -> bool:
    return " even if " in f" {text} "


def _looks_like_modal_main_conditional(text: str) -> bool:
    return " if " in f" {text} " and bool(re.search(r"\b(can|could|may|might|should|would|must)\b", text))


def _looks_like_future_time_clause(text: str) -> bool:
    return any(marker in f" {text} " for marker in (" when ", " before ", " after ", " until ", " as soon as "))


def _looks_like_that_clause(text: str) -> bool:
    return " that " in f" {text} "


def _looks_like_shifted_that_clause(text: str) -> bool:
    return text.startswith("it ") and " that " in f" {text} "


def _looks_like_be_going_to(text: str) -> bool:
    return bool(re.search(r"\b(am|is|are|was|were)\s+going\s+to\b", text))


def _looks_like_passive_by_phrase(text: str) -> bool:
    return " by " in f" {text} " and bool(re.search(r"\b(am|is|are|was|were|be|been|being)\b", text))


def _looks_like_passive(text: str) -> bool:
    return bool(re.search(r"\b(am|is|are|was|were|be|been|being)\b", text))


def _remap_topic(topic: str, sentence_text: str) -> str | None:
    t = _low(sentence_text)
    topic = _norm(topic).lower()

    if topic in SAFE_TOPICS:
        return topic

    if topic == "question_tags":
        return "question tag" if _has_question_tag_pattern(t) else None

    if topic == "existential":
        if _looks_like_existential_there_question(t):
            return "existential there yes-no question"
        if _starts_with_existential_there(t):
            return "existential there basic"
        return None

    if topic == "conditional_sentences":
        if _looks_like_even_if(t):
            return "even if clause"
        if _looks_like_necessary_condition(t):
            return "necessary-condition clause"
        if " unless " in f" {t} ":
            return "unless clause"
        if _looks_like_third_conditional(t):
            return "third conditional"
        if _looks_like_second_conditional(t):
            return "second conditional"
        if _looks_like_first_conditional(t):
            return "first conditional"
        if _looks_like_formal_should_conditional(t):
            return "formal should conditional"
        if _looks_like_were_to_conditional(t):
            return "were-to conditional"
        if _looks_like_inverted_conditional(t):
            return "inverted conditional"
        if _looks_like_reduced_if_phrase(t):
            return "reduced if phrase"
        if _looks_like_modal_main_conditional(t):
            return "present possibility conditional"
        if " if " in f" {t} ":
            return "general conditional clause"
        return None

    if topic == "passive_voice":
        if _looks_like_passive_by_phrase(t):
            return "passive by phrase"
        if _looks_like_passive(t):
            return "general passive voice"
        return None

    if topic == "that_clause":
        if _looks_like_shifted_that_clause(t):
            return "shifted that-clause"
        if _looks_like_that_clause(t):
            return "that-clause noun clause"
        return None

    if topic == "interrogative":
        if _starts_with_wh_question(t):
            return "wh-question"
        if _looks_like_do_support_question(t):
            return "do-support yes-no question"
        if _starts_with_yes_no_auxiliary(t):
            return "yes-no question"
        return None

    if topic == "adverbial_clause":
        return "future time clause" if _looks_like_future_time_clause(t) else None

    if topic == "relative_clauses":
        return None
    if topic == "perfect":
        return None
    if topic == "progressive":
        return None
    if topic == "reported_speech":
        return None

    return None


def build_projection_safe_pool(input_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reject_counts: Counter[str] = Counter()
    remap_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()
    total_seen = 0

    for row in _iter_jsonl(Path(input_path)):
        total_seen += 1
        context = row.get("context") or {}
        source = row.get("source") or {}
        topic = _norm(source.get("topic"))
        sentence_text = _norm(context.get("sentence_text"))
        if _norm(context.get("node_type")) != "Sentence":
            reject_counts["non_sentence_row"] += 1
            continue
        mapped = _remap_topic(topic, sentence_text)
        if not mapped:
            reject_counts[f"topic_unsafe::{topic or 'unknown'}"] += 1
            continue
        new_row = json.loads(json.dumps(row))
        new_row["source"]["topic"] = mapped
        if _norm(topic).lower() != mapped:
            remap_counts[f"{topic} -> {mapped}"] += 1
        topic_counts[mapped] += 1
        rows.append(new_row)

    report = {
        "builder": "build_projection_safe_sentence_note_pool.py",
        "input_path": str(Path(input_path).resolve()),
        "rows_seen": total_seen,
        "rows_kept": len(rows),
        "rows_rejected": total_seen - len(rows),
        "reject_counts": dict(reject_counts),
        "remap_counts": dict(remap_counts),
        "topic_counts": dict(topic_counts),
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a projection-safe sentence note pool.")
    parser.add_argument("--input-jsonl", default=DEFAULT_INPUT)
    parser.add_argument("--output-jsonl", default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--report-json", default=DEFAULT_REPORT_JSON)
    args = parser.parse_args()

    rows, report = build_projection_safe_pool(args.input_jsonl)
    output_jsonl = Path(args.output_jsonl)
    report_json = Path(args.report_json)
    _write_jsonl(output_jsonl, rows)
    _write_json(report_json, report)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows_kept": len(rows),
                "output_jsonl": str(output_jsonl.resolve()),
                "report_json": str(report_json.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
