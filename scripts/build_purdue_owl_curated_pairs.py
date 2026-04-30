#!/usr/bin/env python3
"""Build a curated sentence-pair donor from selected Purdue OWL grammar pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROWS = (
    {
        "topic_key": "relative_clauses",
        "notation_text": "A defining relative clause adds essential information about a noun without commas.",
        "context_text": "This is the house that had a great Christmas decoration.",
        "heading": "restrictive relative clauses",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/relative_pronouns/index.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "A relative pronoun can refer to people in a defining clause.",
        "context_text": "It took me a while to get used to people who eat popcorn during the movie.",
        "heading": "restrictive relative clauses",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/relative_pronouns/index.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "In formal English, whom may appear after a preposition in a relative clause.",
        "context_text": "This is the man to whom I wanted to speak and whose name I had forgotten.",
        "heading": "restrictive relative clauses",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/relative_pronouns/index.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "In informal English, the object relative pronoun may be omitted.",
        "context_text": "The library didn't have the book I wanted.",
        "heading": "restrictive relative clauses",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/relative_pronouns/index.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "A relative clause can use where or in which to refer to a place.",
        "context_text": "This is the house where I lived when I first came to the United States.",
        "heading": "restrictive relative clauses",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/relative_pronouns/index.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "Whose is the possessive relative pronoun used for people and things.",
        "context_text": "The book whose author won a Pulitzer has become a bestseller.",
        "heading": "restrictive relative clauses",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/relative_pronouns/index.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "A non-defining relative clause adds extra information and is usually set off with commas.",
        "context_text": "The science fair, which lasted all day, ended with an awards ceremony.",
        "heading": "non-restrictive relative clauses",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/relative_pronouns/index.html",
    },
    {
        "topic_key": "relative_clauses",
        "notation_text": "In informal English, that can replace who or which in restrictive clauses.",
        "context_text": "He is the kind of person that will never let you down.",
        "heading": "that vs who and which",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/relative_pronouns/index.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The passive voice is useful when the actor is unknown, irrelevant, or intentionally omitted.",
        "context_text": "Crimes were committed.",
        "heading": "passive verbs",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/verb_tenses/passive_verbs.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The passive voice can foreground the thing affected by the action.",
        "context_text": "Penicillin was developed in 1928.",
        "heading": "passive verbs",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/verb_tenses/passive_verbs.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "In the simple present passive, the object of the active clause becomes the grammatical subject.",
        "context_text": "Computers are shipped to many foreign countries.",
        "heading": "simple present passive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/verb_tenses/passive_verbs.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The present progressive passive uses be being plus a past participle.",
        "context_text": "A thunderstorm is being formed.",
        "heading": "present progressive passive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/verb_tenses/passive_verbs.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The simple past passive presents a past event without focusing on the actor.",
        "context_text": "The package was delivered yesterday.",
        "heading": "simple past passive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/verb_tenses/passive_verbs.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The past progressive passive describes an action that was in progress in the past.",
        "context_text": "An announcement was being made.",
        "heading": "past progressive passive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/verb_tenses/passive_verbs.html",
    },
    {
        "topic_key": "passive_voice",
        "notation_text": "The future passive uses will be plus a past participle.",
        "context_text": "The computer will be picked up.",
        "heading": "future passive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/verb_tenses/passive_verbs.html",
    },
    {
        "topic_key": "progressive",
        "notation_text": "The present progressive describes an activity in progress now.",
        "context_text": "I am playing soccer now.",
        "heading": "present progressive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "progressive",
        "notation_text": "The present progressive can be used with some perception or feeling verbs.",
        "context_text": "He is feeling sad.",
        "heading": "present progressive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "progressive",
        "notation_text": "The past progressive can describe an action that continued over a period in the past.",
        "context_text": "They were climbing for twenty-seven days.",
        "heading": "past progressive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "progressive",
        "notation_text": "The past progressive can provide background for an interrupted past event.",
        "context_text": "We were eating dinner when she told me.",
        "heading": "past progressive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The present perfect can describe a state that began in the past and continues into the present.",
        "context_text": "He has lived here for many years.",
        "heading": "present perfect",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The present perfect can express habitual or continued action up to the present.",
        "context_text": "He has worn glasses all his life.",
        "heading": "present perfect",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The present perfect can refer to an unspecified past experience.",
        "context_text": "Have you ever been to Tokyo before?",
        "heading": "present perfect",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The present perfect progressive emphasizes duration from the past into the present.",
        "context_text": "David has been working for two hours, and he hasn't finished yet.",
        "heading": "present perfect progressive",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The past perfect describes an event completed before another past event.",
        "context_text": "When I arrived home, he had already called.",
        "heading": "past perfect",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
    {
        "topic_key": "perfect",
        "notation_text": "The future perfect describes an action completed by a future time.",
        "context_text": "By next month we will have finished the job.",
        "heading": "future perfect",
        "source_url": "https://owl.purdue.edu/owl/general_writing/grammar/active_verb_tenses.html",
    },
)


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


def build_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in ROWS:
        rows.append(
            {
                "source_path": row["source_url"],
                "row_type": "purdue_owl_curated",
                "source_book": "purdue_owl_grammar",
                "heading": row["heading"],
                "entry_head": row["heading"],
                "topic_key": row["topic_key"],
                "notation_text": row["notation_text"],
                "context_text": row["context_text"],
                "pair_method": "purdue_owl_curated_v1",
            }
        )
    report = {
        "pipeline_version": "purdue_owl_curated_pairs_v1",
        "rows_total": len(rows),
        "topic_counts": {
            key: sum(1 for row in rows if row["topic_key"] == key)
            for key in sorted({row["topic_key"] for row in rows})
        },
        "sources": sorted({row["source_path"] for row in rows}),
    }
    return rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a curated Purdue OWL grammar donor dataset.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows, report = build_rows()
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
