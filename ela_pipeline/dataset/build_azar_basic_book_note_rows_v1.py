"""Build a selective note pack from Betty Azar (1996).

Azar is treated as a secondary source:

- basic be going to future
- there is / there are
- future time clauses
- basic if-clauses for future time

The source is exercise-heavy, so the importer stays conservative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_PATH = "/home/vlad/winshare/Betty Scrampfer Azar - Basic English Grammar, Second Edition - 1996.pdf"
DOCUMENT_ID = "betty_azar_basic_english_grammar_1996"


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:16]


def _template_projection(note_text: str) -> dict[str, Any]:
    return {
        "template_projection_version": "book_note_template_v4",
        "original_note_text": note_text,
        "template_kind": "passthrough",
        "note_template": note_text,
        "slot_values": {},
        "rendered_note": note_text,
        "template_risk_flags": [],
        "templated": False,
    }


def _sentence_row(*, sentence: str, topic: str, note_text: str, origin_unit: str) -> dict[str, Any]:
    source_record_id = _stable_id(DOCUMENT_ID, topic, sentence, note_text)
    return {
        "id": source_record_id,
        "context": {
            "node_type": "Sentence",
            "content": sentence,
            "sentence_text": sentence,
            "part_of_speech": "sentence",
            "grammatical_role": "clause",
        },
        "source": {
            "document_id": DOCUMENT_ID,
            "source_path": SOURCE_PATH,
            "topic": topic,
            "origin_unit": origin_unit,
            "source_record_id": source_record_id,
        },
        "target": {
            "audience_level": "elementary",
            "note_text": note_text,
        },
        "template_projection": _template_projection(note_text),
    }


def build_rows() -> list[dict[str, Any]]:
    return [
        _sentence_row(
            sentence="I’m going to go downtown tomorrow.",
            topic="be going to future",
            note_text="Be going to is used to talk about a future plan or intention.",
            origin_unit="chapter 6 / be going to",
        ),
        _sentence_row(
            sentence="Ann isn’t going to study tonight.",
            topic="be going to future negative",
            note_text="In negative be going to clauses, not follows be.",
            origin_unit="chapter 6 / be going to negative",
        ),
        _sentence_row(
            sentence="Are you going to come to class tomorrow?",
            topic="be going to yes-no question",
            note_text="A yes-no question with be going to is formed by placing be before the subject.",
            origin_unit="chapter 6 / be going to question",
        ),
        _sentence_row(
            sentence="What time are you going to eat dinner tonight?",
            topic="be going to wh-question",
            note_text="A wh-question with be going to begins with the wh-expression and keeps be before the subject.",
            origin_unit="chapter 6 / be going to wh-question",
        ),
        _sentence_row(
            sentence="There is a book on my desk.",
            topic="existential there basic",
            note_text="There is introduces the existence of a singular thing in a place or situation.",
            origin_unit="chapter 3 / there is",
        ),
        _sentence_row(
            sentence="There are some books on Ali’s desk.",
            topic="existential there agreement",
            note_text="In existential there clauses, the form of be agrees with the noun phrase that follows it.",
            origin_unit="chapter 3 / there are",
        ),
        _sentence_row(
            sentence="Is there any milk in the refrigerator?",
            topic="existential there yes-no question",
            note_text="Questions with existential there are formed by placing be before there.",
            origin_unit="chapter 3 / there + be questions",
        ),
        _sentence_row(
            sentence="Are there any eggs in the refrigerator?",
            topic="existential there yes-no question",
            note_text="With plural following nouns, existential there questions use are there.",
            origin_unit="chapter 3 / there + be questions",
        ),
        _sentence_row(
            sentence="Maybe Abdullah will be in class tomorrow.",
            topic="maybe adverb",
            note_text="Maybe is an adverb meaning possibly and it appears before the subject and verb.",
            origin_unit="chapter 6 / maybe vs may be",
        ),
        _sentence_row(
            sentence="Abdullah may be here tomorrow.",
            topic="modal clause",
            note_text="May and might express possibility rather than certainty.",
            origin_unit="chapter 6 / may and might",
        ),
        _sentence_row(
            sentence="It may rain tomorrow.",
            topic="modal clause",
            note_text="May can present a future event as possible rather than certain.",
            origin_unit="chapter 6 / may and might",
        ),
        _sentence_row(
            sentence="Before Ann goes to work tomorrow, she will eat breakfast.",
            topic="future time clause",
            note_text="A future time clause uses the simple present after words like before, after, and when rather than will or be going to.",
            origin_unit="chapter 6 / future time clauses",
        ),
        _sentence_row(
            sentence="I’m going to finish my homework after I eat dinner tonight.",
            topic="future time clause",
            note_text="In a future time clause, the time-marker clause uses the simple present while the main clause carries the future meaning.",
            origin_unit="chapter 6 / future time clauses",
        ),
        _sentence_row(
            sentence="When I go to New York next week, I’m going to stay at the Hilton Hotel.",
            topic="future time clause",
            note_text="When-clauses that refer to the future use the simple present instead of will.",
            origin_unit="chapter 6 / future time clauses",
        ),
        _sentence_row(
            sentence="If it rains tomorrow, we will stay home.",
            topic="first conditional",
            note_text="In a future if-clause, English uses the simple present in the condition clause and a future form in the main clause.",
            origin_unit="chapter 6 / if-clause future meaning",
        ),
        _sentence_row(
            sentence="I’m going to buy a new car next year if I have enough money.",
            topic="first conditional",
            note_text="An if-clause can come before or after the main clause, but it still uses the simple present for future time.",
            origin_unit="chapter 6 / if-clause position",
        ),
    ]


def _write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: str, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build selective book-note rows from Betty Azar (1996).")
    parser.add_argument(
        "--output-jsonl",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_azar_basic_v1/azar_basic_book_note_rows_v1.jsonl",
    )
    parser.add_argument(
        "--report-json",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_azar_basic_v1/azar_basic_book_note_rows_v1.report.json",
    )
    args = parser.parse_args()

    rows = build_rows()
    report = {
        "document_id": DOCUMENT_ID,
        "source_path": SOURCE_PATH,
        "rows_total": len(rows),
        "sentence_rows": len(rows),
        "phrase_rows": 0,
        "topics": sorted(
            {
                str((row.get("source") or {}).get("topic"))
                for row in rows
                if str((row.get("source") or {}).get("topic")).strip()
            }
        ),
    }
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(rows),
                "output_jsonl": str(Path(args.output_jsonl).resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
