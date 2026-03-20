"""Build a sentence-first curated note pack from Mark Lester (2009).

Mark Lester is especially useful for:

- yes-no questions and do-support
- information questions
- negatives and question tags
- passive constructions
- noun clauses

The pack is intentionally dense on sentence notes because the current corpus
still has a sentence-layer bottleneck.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_PATH = "/home/vlad/winshare/Mark Lester - English Grammar Drills - 2009.pdf"
DOCUMENT_ID = "mark_lester_english_grammar_drills_2009"


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
            "audience_level": "intermediate",
            "note_text": note_text,
        },
        "template_projection": _template_projection(note_text),
    }


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    rows.extend(
        [
            _sentence_row(
                sentence="Are you ready to go?",
                topic="yes-no question",
                note_text="A yes-no question is formed by inverting the subject and the first available auxiliary or main be verb.",
                origin_unit="13 questions and negatives / yes-no questions",
            ),
            _sentence_row(
                sentence="Should we call them?",
                topic="yes-no question",
                note_text="With modal auxiliaries, yes-no questions are formed by placing the modal before the subject.",
                origin_unit="13 questions and negatives / modal inversion",
            ),
            _sentence_row(
                sentence="Is he leaving soon?",
                topic="yes-no question",
                note_text="Helping verbs such as be and have can invert with the subject to form a yes-no question.",
                origin_unit="13 questions and negatives / helping verbs",
            ),
            _sentence_row(
                sentence="Are the kids at school?",
                topic="yes-no question with be",
                note_text="When be is the main verb, the question is formed by placing be before the subject.",
                origin_unit="13 questions and negatives / main verb be",
            ),
            _sentence_row(
                sentence="Did John smile?",
                topic="do-support yes-no question",
                note_text="When the clause has no invertible auxiliary, English uses do-support to form a yes-no question.",
                origin_unit="13 questions and negatives / do insertion",
            ),
            _sentence_row(
                sentence="Does the TV work?",
                topic="do-support yes-no question",
                note_text="In a do-support question, tense is carried by do while the main verb appears in its base form.",
                origin_unit="13 questions and negatives / do insertion",
            ),
            _sentence_row(
                sentence="Do you have a question?",
                topic="do-support yes-no question",
                note_text="In modern American English, main verb have normally takes do-support in yes-no questions.",
                origin_unit="13 questions and negatives / have as a main verb",
            ),
            _sentence_row(
                sentence="You are ready to go, aren’t you?",
                topic="question tag",
                note_text="A question tag repeats the clause with auxiliary-pronoun structure and is typically negative after a positive statement.",
                origin_unit="13 questions and negatives / tag questions",
            ),
            _sentence_row(
                sentence="Where did Charlie go?",
                topic="wh-question with do-support",
                note_text="An information question moves the wh-word to the front and still uses auxiliary inversion.",
                origin_unit="13 questions and negatives / information questions",
            ),
            _sentence_row(
                sentence="When will they be back?",
                topic="wh-question",
                note_text="Information questions place the interrogative word first and then invert the subject with the first verb.",
                origin_unit="13 questions and negatives / information questions",
            ),
            _sentence_row(
                sentence="How often have you seen it?",
                topic="wh-question",
                note_text="Interrogative expressions such as how often function as fronted question words in information questions.",
                origin_unit="13 questions and negatives / interrogative adverbs",
            ),
            _sentence_row(
                sentence="What should we give them?",
                topic="wh-question",
                note_text="In an information question, the wh-expression is fronted and the clause keeps inverted question order.",
                origin_unit="13 questions and negatives / question formation steps",
            ),
            _sentence_row(
                sentence="Whom did you want to see?",
                topic="wh-question with do-support",
                note_text="When no auxiliary is available, an object wh-question uses do-support after the wh-expression is fronted.",
                origin_unit="13 questions and negatives / information questions with do",
            ),
            _sentence_row(
                sentence="Why do you want to go there?",
                topic="wh-question with do-support",
                note_text="Wh-questions with lexical verbs require do-support in the same way as yes-no questions.",
                origin_unit="13 questions and negatives / information questions with do",
            ),
            _sentence_row(
                sentence="They do not know where it is.",
                topic="negative clause",
                note_text="In English negation, not is typically placed after the first auxiliary or after do in do-support clauses.",
                origin_unit="13 questions and negatives / negatives",
            ),
            _sentence_row(
                sentence="You do not know where the sugar is.",
                topic="do-support negative clause",
                note_text="When a clause lacks an auxiliary, do-support is used to carry negation.",
                origin_unit="13 questions and negatives / negatives with do",
            ),
            _sentence_row(
                sentence="You know how to fill out these forms, right?",
                topic="question tag",
                note_text="Informal conversation can use a short final tag to check or confirm what the speaker assumes is true.",
                origin_unit="13 questions and negatives / informal tags",
            ),
            _sentence_row(
                sentence="The garage was cleaned out yesterday.",
                topic="general passive voice",
                note_text="A passive clause contains be followed by a past participle and presents the affected participant as subject.",
                origin_unit="14 the passive / basic passive pattern",
            ),
            _sentence_row(
                sentence="The job is being contracted out to a firm in Singapore.",
                topic="passive progressive",
                note_text="A clause can be both progressive and passive when it contains be plus being plus a past participle.",
                origin_unit="14 the passive / progressive passive",
            ),
            _sentence_row(
                sentence="The movie was filmed in Spain.",
                topic="passive form",
                note_text="The passive is identified by a form of be followed by the verb in its past participle form.",
                origin_unit="14 the passive / be plus past participle",
            ),
            _sentence_row(
                sentence="John has been seen by Mary.",
                topic="passive perfect",
                note_text="In a perfect passive, the tense is carried by have while the passive sequence appears as been plus past participle.",
                origin_unit="14 the passive / perfect passive",
            ),
            _sentence_row(
                sentence="The kids are being watched by my parents.",
                topic="passive progressive",
                note_text="A progressive passive combines progressive aspect with passive voice to describe an ongoing action affecting the subject.",
                origin_unit="14 the passive / active to passive conversion",
            ),
            _sentence_row(
                sentence="The bill will be paid by them.",
                topic="passive with modal",
                note_text="With modal auxiliaries, the passive is formed by modal plus be plus past participle.",
                origin_unit="14 the passive / modal auxiliary passive",
            ),
            _sentence_row(
                sentence="The meeting was postponed by Kathy.",
                topic="passive by phrase",
                note_text="A by-phrase can introduce the agent in a passive clause when the performer is expressed.",
                origin_unit="14 the passive / by-phrase",
            ),
            _sentence_row(
                sentence="What they are doing is none of our business.",
                topic="wh-clause noun clause",
                note_text="A noun clause can function as the subject of a sentence even though it contains its own subject and verb.",
                origin_unit="7 noun clauses / subject wh-clause",
            ),
            _sentence_row(
                sentence="I know what you mean.",
                topic="wh-clause noun clause",
                note_text="A wh-clause can function as the object of a verb while keeping statement word order inside the clause.",
                origin_unit="7 noun clauses / object wh-clause",
            ),
            _sentence_row(
                sentence="We worried about where you had gone.",
                topic="wh-clause noun clause",
                note_text="Unlike that-clauses, wh-clauses can function as the object of a preposition.",
                origin_unit="7 noun clauses / object of preposition",
            ),
            _sentence_row(
                sentence="The decision was that we will go ahead as we had planned.",
                topic="that-clause noun clause",
                note_text="A that-clause can function as a noun clause, including as the complement of a linking verb.",
                origin_unit="7 noun clauses / predicate nominative",
            ),
            _sentence_row(
                sentence="They knew that they would have to extend the deadline.",
                topic="that-clause noun clause",
                note_text="That-clauses are formed from a statement in normal word order and often function as objects of verbs.",
                origin_unit="7 noun clauses / object that-clause",
            ),
            _sentence_row(
                sentence="It didn’t come as a big surprise that the flight was going to be delayed.",
                topic="shifted that-clause",
                note_text="A heavy subject that-clause is often shifted to the end of the sentence, with dummy it in subject position.",
                origin_unit="7 noun clauses / shifted subject that-clause",
            ),
            _sentence_row(
                sentence="It seems a little out of character that they would even consider doing it.",
                topic="shifted that-clause",
                note_text="English often uses anticipatory it and places the that-clause later in the sentence when the clause would be a heavy subject.",
                origin_unit="7 noun clauses / shifted subject that-clause",
            ),
            _sentence_row(
                sentence="We decided that we should call a taxi.",
                topic="that-clause noun clause",
                note_text="The introductory that in an object that-clause is often optional, but the clause still functions as a noun clause.",
                origin_unit="7 noun clauses / deleted that",
            ),
            _sentence_row(
                sentence="He claimed he had been working at home all afternoon.",
                topic="deleted-that clause",
                note_text="When a that-clause functions as object, the introductory that is often omitted in everyday English.",
                origin_unit="7 noun clauses / deleted that",
            ),
            _sentence_row(
                sentence="I know where they went.",
                topic="wh-clause noun clause",
                note_text="Inside a wh-clause used as a noun clause, the clause keeps statement order rather than question inversion.",
                origin_unit="7 noun clauses / internal structure of wh-clauses",
            ),
            _sentence_row(
                sentence="I know who that man is.",
                topic="wh-clause noun clause",
                note_text="Wh-clauses used as noun clauses do not use the inverted word order of direct questions.",
                origin_unit="7 noun clauses / avoiding question order",
            ),
            _sentence_row(
                sentence="I know what he said.",
                topic="wh-clause noun clause",
                note_text="A wh-clause is formed by moving the wh-word to the front of the embedded clause while the rest of the clause keeps statement order.",
                origin_unit="7 noun clauses / movement inside wh-clauses",
            ),
            _sentence_row(
                sentence="I know whom you spoke to.",
                topic="wh-clause noun clause",
                note_text="A wh-clause can contain a fronted wh-expression while the related preposition remains later in the clause in ordinary style.",
                origin_unit="7 noun clauses / object of preposition",
            ),
            _sentence_row(
                sentence="I know to whom you spoke.",
                topic="wh-clause noun clause formal",
                note_text="In formal style, the preposition can move to the front together with whom inside a wh-clause.",
                origin_unit="7 noun clauses / formal preposition fronting",
            ),
            _sentence_row(
                sentence="The question is whose idea was it in the first place?",
                topic="wh-clause noun clause",
                note_text="A wh-clause can also function as the complement of a linking verb.",
                origin_unit="7 noun clauses / predicate nominative wh-clause",
            ),
            _sentence_row(
                sentence="Whatever you want to do is OK with me.",
                topic="wh-clause noun clause",
                note_text="Wh-clauses can be introduced by ever-forms such as whatever and function as full noun clauses.",
                origin_unit="7 noun clauses / wh-ever forms",
            ),
        ]
    )

    return rows


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
    parser = argparse.ArgumentParser(description="Build curated book-note rows from Mark Lester (2009).")
    parser.add_argument(
        "--output-jsonl",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_mark_lester_v1/mark_lester_book_note_rows_v1.jsonl",
    )
    parser.add_argument(
        "--report-json",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_mark_lester_v1/mark_lester_book_note_rows_v1.report.json",
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
