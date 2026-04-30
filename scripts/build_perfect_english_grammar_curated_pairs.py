#!/usr/bin/env python3
"""Build a curated donor from selected Perfect English Grammar explanation pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROWS = (
    {
        "topic_key": "question_tags",
        "notation_text": "Question tags turn a statement into a question to check information.",
        "context_text": "She's Italian, isn't she?",
        "heading": "tag questions",
        "source_url": "https://www.perfect-english-grammar.com/tag-questions.html",
    },
    {
        "topic_key": "question_tags",
        "notation_text": "If the main clause is positive, the tag is usually negative.",
        "context_text": "They live in London, don't they?",
        "heading": "tag questions",
        "source_url": "https://www.perfect-english-grammar.com/tag-questions.html",
    },
    {
        "topic_key": "question_tags",
        "notation_text": "If the main clause is negative, the tag is usually positive.",
        "context_text": "She doesn't have any children, does she?",
        "heading": "tag questions",
        "source_url": "https://www.perfect-english-grammar.com/tag-questions.html",
    },
    {
        "topic_key": "question_tags",
        "notation_text": "After I am, the question tag is usually aren't I.",
        "context_text": "I'm in charge of the food, aren't I?",
        "heading": "tag questions",
        "source_url": "https://www.perfect-english-grammar.com/tag-questions.html",
    },
    {
        "topic_key": "question_tags",
        "notation_text": "Question tags can match perfect verb forms with the same auxiliary.",
        "context_text": "They've been to Japan, haven't they?",
        "heading": "tag questions",
        "source_url": "https://www.perfect-english-grammar.com/tag-questions.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The passive voice can put the object first when the actor is less important.",
        "context_text": "Two cups of coffee were drunk.",
        "heading": "the passive voice",
        "source_url": "https://www.perfect-english-grammar.com/passive.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The passive is made with be in the needed tense plus a past participle.",
        "context_text": "A cake is made.",
        "heading": "making the passive",
        "source_url": "https://www.perfect-english-grammar.com/passive.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The present continuous passive uses is being plus a past participle.",
        "context_text": "A cake is being made.",
        "heading": "making the passive",
        "source_url": "https://www.perfect-english-grammar.com/passive.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "Some verbs with two objects can form two passive patterns.",
        "context_text": "I was given the book.",
        "heading": "verbs with two objects",
        "source_url": "https://www.perfect-english-grammar.com/passive.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The passive can be used when the actor is unknown or unimportant.",
        "context_text": "My bike has been stolen.",
        "heading": "when should we use the passive",
        "source_url": "https://www.perfect-english-grammar.com/passive.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The passive is common when the result matters more than the actor.",
        "context_text": "The road is being repaired.",
        "heading": "when should we use the passive",
        "source_url": "https://www.perfect-english-grammar.com/passive.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "A relative clause can join two sentences or add more information about something.",
        "context_text": "I bought a new car that is very fast.",
        "heading": "relative clauses",
        "source_url": "https://www.perfect-english-grammar.com/relative-clauses.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "A defining relative clause tells us which noun we are talking about.",
        "context_text": "I like the woman who lives next door.",
        "heading": "defining and non-defining",
        "source_url": "https://www.perfect-english-grammar.com/relative-clauses.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "A non-defining relative clause adds extra information that is not essential to identify the noun.",
        "context_text": "I live in London, which has some fantastic parks.",
        "heading": "defining and non-defining",
        "source_url": "https://www.perfect-english-grammar.com/relative-clauses.html",
    },
    {
        "topic_key": "progressive",
        "notation_text": "The present continuous is used for things happening at the moment of speaking.",
        "context_text": "I'm working at the moment.",
        "heading": "present continuous use",
        "source_url": "https://www.perfect-english-grammar.com/present-continuous-use.html",
    },
    {
        "topic_key": "progressive",
        "notation_text": "The present continuous can describe a temporary situation even if it is not happening right now.",
        "context_text": "John's working in a bar until he finds a job in his field.",
        "heading": "present continuous use",
        "source_url": "https://www.perfect-english-grammar.com/present-continuous-use.html",
    },
    {
        "topic_key": "progressive",
        "notation_text": "The present continuous can describe temporary or new habits.",
        "context_text": "He's eating a lot these days.",
        "heading": "present continuous use",
        "source_url": "https://www.perfect-english-grammar.com/present-continuous-use.html",
    },
    {
        "topic_key": "progressive",
        "notation_text": "The present continuous can describe an annoying habit with adverbs like always or forever.",
        "context_text": "You're forever losing your keys!",
        "heading": "present continuous use",
        "source_url": "https://www.perfect-english-grammar.com/present-continuous-use.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The present perfect continuous can show how long an unfinished action has continued up to the present.",
        "context_text": "I've been living in London for two years.",
        "heading": "present perfect continuous use",
        "source_url": "https://www.perfect-english-grammar.com/present-perfect-continuous-use.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The present perfect continuous can describe a temporary habit or situation continuing into the present.",
        "context_text": "I've been going to the gym a lot recently.",
        "heading": "present perfect continuous use",
        "source_url": "https://www.perfect-english-grammar.com/present-perfect-continuous-use.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The present perfect continuous can describe a recent action with a visible present result.",
        "context_text": "It's been raining so the pavement is wet.",
        "heading": "present perfect continuous use",
        "source_url": "https://www.perfect-english-grammar.com/present-perfect-continuous-use.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The future perfect can show how long something will have continued by a future time.",
        "context_text": "When we get married, I'll have known Robert for four years.",
        "heading": "future perfect use",
        "source_url": "https://www.perfect-english-grammar.com/future-perfect-tense-use.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The future perfect can describe an action finished before a future deadline.",
        "context_text": "By 10 o'clock, I will have finished my homework.",
        "heading": "future perfect use",
        "source_url": "https://www.perfect-english-grammar.com/future-perfect-tense-use.html",
    },
    {
        "topic_key": "conditional_sentences",
        "notation_text": "The second conditional uses the past simple after if and would plus the infinitive in the result clause.",
        "context_text": "If I won the lottery, I would buy a big house.",
        "heading": "second conditional",
        "source_url": "https://www.perfect-english-grammar.com/second-conditional.html",
    },
    {
        "topic_key": "conditional_sentences",
        "notation_text": "The second conditional can describe an unreal present situation.",
        "context_text": "If I had his number, I would call him.",
        "heading": "second conditional",
        "source_url": "https://www.perfect-english-grammar.com/second-conditional.html",
    },
    {
        "topic_key": "conditional_sentences",
        "notation_text": "In formal style, the second conditional often uses were instead of was.",
        "context_text": "If I were you, I wouldn't go out with that man.",
        "heading": "second conditional",
        "source_url": "https://www.perfect-english-grammar.com/second-conditional.html",
    },
)


def _write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: str, rows: list[dict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_rows() -> tuple[list[dict], dict]:
    rows = []
    for row in ROWS:
        rows.append(
            {
                "source_path": row["source_url"],
                "row_type": "perfect_english_grammar_curated",
                "source_book": "perfect_english_grammar",
                "heading": row["heading"],
                "entry_head": row["heading"],
                "topic_key": row["topic_key"],
                "notation_text": row["notation_text"],
                "context_text": row["context_text"],
                "pair_method": "perfect_english_grammar_curated_v1",
            }
        )
    report = {
        "pipeline_version": "perfect_english_grammar_curated_pairs_v1",
        "rows_total": len(rows),
        "topic_counts": {
            key: sum(1 for row in rows if row["topic_key"] == key)
            for key in sorted({row["topic_key"] for row in rows})
        },
        "sources": sorted({row["source_path"] for row in rows}),
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a curated donor from Perfect English Grammar pages.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows, report = build_rows()
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
