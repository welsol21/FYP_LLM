"""Build curated book-note rows from Börjars & Burridge (2010).

This importer is intentionally narrow: it produces a clean note pack for
sentence types and a few phrase-level adverbial examples that fit our
current book-to-corpus pipeline well.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_PATH = "/home/vlad/winshare/Börjars K., Burridge K. - Introducing English Grammar. Second Edition - 2010.pdf"
DOCUMENT_ID = "borjars_burridge_2010"


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:16]


def _sentence_row(sentence: str, *, topic: str, note_text: str, origin_unit: str) -> dict[str, Any]:
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
        "template_projection": {
            "template_projection_version": "book_note_template_v4",
            "original_note_text": note_text,
            "template_kind": "passthrough",
            "note_template": note_text,
            "slot_values": {},
            "rendered_note": note_text,
            "template_risk_flags": [],
            "templated": False,
        },
    }


def _phrase_row(
    sentence: str,
    *,
    phrase_text: str,
    part_of_speech: str,
    grammatical_role: str,
    topic: str,
    note_text: str,
    origin_unit: str,
) -> dict[str, Any]:
    source_record_id = _stable_id(DOCUMENT_ID, topic, sentence, phrase_text, note_text)
    return {
        "id": source_record_id,
        "context": {
            "node_type": "Phrase",
            "content": phrase_text,
            "sentence_text": sentence,
            "part_of_speech": part_of_speech,
            "grammatical_role": grammatical_role,
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
        "template_projection": {
            "template_projection_version": "book_note_template_v4",
            "original_note_text": note_text,
            "template_kind": "passthrough",
            "note_template": note_text,
            "slot_values": {},
            "rendered_note": note_text,
            "template_risk_flags": [],
            "templated": False,
        },
    }


def build_rows() -> list[dict[str, Any]]:
    sentence_rows = [
        _sentence_row(
            "Did Esther Luer discover a giant arachnid in her weekly groceries?",
            topic="yes-no interrogatives",
            note_text="Yes-no interrogatives use subject-operator inversion and typically ask for a yes-or-no answer.",
            origin_unit="different sentence types",
        ),
        _sentence_row(
            "What did Esther Luer discover?",
            topic="wh-interrogatives",
            note_text="Wh-interrogatives front a wh-constituent and use subject-operator inversion.",
            origin_unit="different sentence types",
        ),
        _sentence_row(
            "Where did she discover this arachnid?",
            topic="wh-interrogatives",
            note_text="Wh-interrogatives front a wh-constituent and use subject-operator inversion.",
            origin_unit="different sentence types",
        ),
        _sentence_row(
            "Are you a Mod or a Rocker?",
            topic="alternative questions",
            note_text="Alternative questions offer a choice between two or more alternatives.",
            origin_unit="different sentence types",
        ),
        _sentence_row(
            "You will take all the swear words out, won’t you?",
            topic="question tags",
            note_text="Question tags are short reduced questions added to declaratives to seek confirmation.",
            origin_unit="different sentence types",
        ),
        _sentence_row(
            "That sort of thing doesn’t really happen, does it?",
            topic="question tags",
            note_text="Question tags are short reduced questions added to declaratives to seek confirmation.",
            origin_unit="different sentence types",
        ),
        _sentence_row(
            "What is the difference between a push and a shove?",
            topic="wh-interrogatives",
            note_text="Wh-interrogatives front a wh-constituent and use subject-operator inversion.",
            origin_unit="different sentence types",
        ),
        _sentence_row(
            "Discover arachnids in your weekly groceries!",
            topic="imperatives",
            note_text="Imperatives typically omit an overt subject and are commonly used to issue directives.",
            origin_unit="different sentence types",
        ),
        _sentence_row(
            "And what an arachnid it was!",
            topic="exclamatives",
            note_text="Exclamatives begin with a what- or how-phrase and express an exclamation rather than a question.",
            origin_unit="different sentence types",
        ),
    ]

    phrase_rows = [
        _phrase_row(
            "He began his career at the tender age of 13 with the Latin boy-band Menudo.",
            phrase_text="at the tender age of 13",
            part_of_speech="prepositional phrase",
            grammatical_role="modifier",
            topic="adverbials",
            note_text="Adjuncts are optional adverbials that add circumstantial information such as time, place, or manner.",
            origin_unit="functions within the clause",
        ),
        _phrase_row(
            "He began his career at the tender age of 13 with the Latin boy-band Menudo.",
            phrase_text="with the Latin boy-band Menudo",
            part_of_speech="prepositional phrase",
            grammatical_role="modifier",
            topic="adverbials",
            note_text="Adjuncts are optional adverbials that add circumstantial information such as time, place, or manner.",
            origin_unit="functions within the clause",
        ),
        _phrase_row(
            "The bride’s mother threw a large pickled gherkin at the tormented lover.",
            phrase_text="at the tormented lover",
            part_of_speech="prepositional phrase",
            grammatical_role="modifier",
            topic="adverbials",
            note_text="This adjunct functions as an adverbial and adds circumstantial information to the clause.",
            origin_unit="functions within the clause",
        ),
        _phrase_row(
            "The other guests pelted the weeping Lothario with an assortment of crustless sandwiches and condiments.",
            phrase_text="with an assortment of crustless sandwiches and condiments",
            part_of_speech="prepositional phrase",
            grammatical_role="modifier",
            topic="adverbials",
            note_text="This adjunct functions as an adverbial and adds circumstantial information to the clause.",
            origin_unit="functions within the clause",
        ),
        _phrase_row(
            "Phil Spector put the wall of sound around the Christmas tree.",
            phrase_text="around the Christmas tree",
            part_of_speech="prepositional phrase",
            grammatical_role="modifier",
            topic="adverbial complements",
            note_text="Some adverbials are complements required by the verb rather than optional modifiers.",
            origin_unit="functions within the clause",
        ),
    ]

    return sentence_rows + phrase_rows


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
    parser = argparse.ArgumentParser(description="Build curated Börjars/Burridge book note rows.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows = build_rows()
    report = {
        "document_id": DOCUMENT_ID,
        "source_path": SOURCE_PATH,
        "rows_total": len(rows),
        "sentence_rows": sum(1 for row in rows if row["context"]["node_type"] == "Sentence"),
        "phrase_rows": sum(1 for row in rows if row["context"]["node_type"] == "Phrase"),
        "topics": sorted({_stable_topic(row) for row in rows}),
    }
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    print(json.dumps({"status": "ok", "rows": len(rows), "output_jsonl": str(Path(args.output_jsonl).resolve())}, ensure_ascii=False, indent=2))


def _stable_topic(row: dict[str, Any]) -> str:
    return _norm((row.get("source") or {}).get("topic"))


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


if __name__ == "__main__":
    main()
