"""Build curated note rows from open-access grammar books.

This importer is intentionally selective. It only keeps explanations that:

- map cleanly to sentence- or phrase-level notes,
- add useful construction coverage,
- fit the current book -> corpus workflow without mass generic duplication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DOCUMENTS = {
    "brehe_grammar_anatomy_2019": {
        "source_path": "/home/vlad/Dev/FYP_LLM/data/open_book_sources_2026_03/brehe_grammar_anatomy.pdf",
        "label": "Steven Brehe - Brehe's Grammar Anatomy",
        "license": "CC BY-SA 4.0",
    },
    "thiessen_academic_grammar_2025": {
        "source_path": "/home/vlad/Dev/FYP_LLM/data/open_book_sources_2026_03/advanced_academic_grammar_esl.pdf",
        "label": "Randal Thiessen - English Grammar for Academic Purposes",
        "license": "CC BY-NC-ND 4.0",
    },
}


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


def _sentence_row(
    *,
    document_id: str,
    sentence: str,
    topic: str,
    note_text: str,
    origin_unit: str,
) -> dict[str, Any]:
    source_record_id = _stable_id(document_id, topic, sentence, note_text)
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
            "document_id": document_id,
            "source_path": DOCUMENTS[document_id]["source_path"],
            "topic": topic,
            "origin_unit": origin_unit,
            "source_record_id": source_record_id,
            "source_label": DOCUMENTS[document_id]["label"],
            "source_license": DOCUMENTS[document_id]["license"],
        },
        "target": {
            "audience_level": "intermediate",
            "note_text": note_text,
        },
        "template_projection": _template_projection(note_text),
    }


def _phrase_row(
    *,
    document_id: str,
    sentence: str,
    phrase_text: str,
    part_of_speech: str,
    grammatical_role: str,
    topic: str,
    note_text: str,
    origin_unit: str,
) -> dict[str, Any]:
    source_record_id = _stable_id(document_id, topic, sentence, phrase_text, note_text)
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
            "document_id": document_id,
            "source_path": DOCUMENTS[document_id]["source_path"],
            "topic": topic,
            "origin_unit": origin_unit,
            "source_record_id": source_record_id,
            "source_label": DOCUMENTS[document_id]["label"],
            "source_license": DOCUMENTS[document_id]["license"],
        },
        "target": {
            "audience_level": "intermediate",
            "note_text": note_text,
        },
        "template_projection": _template_projection(note_text),
    }


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    brehe = "brehe_grammar_anatomy_2019"
    rows.extend(
        [
            _sentence_row(
                document_id=brehe,
                sentence="Get out of here!",
                topic="imperatives",
                note_text="In an imperative sentence, the subject is often omitted and understood as the second-person pronoun you.",
                origin_unit="imperative sentences",
            ),
            _sentence_row(
                document_id=brehe,
                sentence="I went to the garage, and I found my bike.",
                topic="compound sentence",
                note_text="A compound sentence contains two or more independent clauses joined by a coordinating conjunction.",
                origin_unit="simple compound complex and compound-complex sentences",
            ),
            _sentence_row(
                document_id=brehe,
                sentence="I went to the garage because I needed my bike.",
                topic="complex sentence",
                note_text="A complex sentence contains one independent clause and one or more dependent clauses.",
                origin_unit="simple compound complex and compound-complex sentences",
            ),
            _sentence_row(
                document_id=brehe,
                sentence="I went to the garage because I needed my bike, and I found it.",
                topic="compound-complex sentence",
                note_text="A compound-complex sentence contains at least two independent clauses together with at least one dependent clause.",
                origin_unit="simple compound complex and compound-complex sentences",
            ),
            _sentence_row(
                document_id=brehe,
                sentence="Because he wanted to leave, he left.",
                topic="subordinate clause",
                note_text="Subordinate clauses are adverbial and can often be moved to the beginning or the end of the sentence.",
                origin_unit="subordinate clauses",
            ),
            _sentence_row(
                document_id=brehe,
                sentence="The job that you want is part-time.",
                topic="relative clause",
                note_text="A relative clause can combine two clauses into one complex sentence by embedding extra information after a noun.",
                origin_unit="relative clauses",
            ),
            _phrase_row(
                document_id=brehe,
                sentence="The dog in the yard barked loudly.",
                phrase_text="in the yard",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="adjectival prepositional phrase",
                note_text="Adjectival prepositional phrases usually follow the nouns they modify.",
                origin_unit="prepositions",
            ),
            _phrase_row(
                document_id=brehe,
                sentence="I arrived at noon.",
                phrase_text="at noon",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="adverbial prepositional phrase",
                note_text="As adverbs, prepositional phrases can tell us when, where, why, or how the action of the verb was performed.",
                origin_unit="prepositions",
            ),
            _phrase_row(
                document_id=brehe,
                sentence="We drove the car into the garage.",
                phrase_text="into the garage",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="adverbial prepositional phrase",
                note_text="A prepositional phrase can be adverbial even when it follows a noun; here it answers where the car was driven.",
                origin_unit="prepositions",
            ),
            _phrase_row(
                document_id=brehe,
                sentence="The man who spoke to you is my uncle.",
                phrase_text="who spoke to you",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="relative clause",
                note_text="Relative clauses modify nouns and appear after the nouns they modify.",
                origin_unit="relative clauses",
            ),
            _phrase_row(
                document_id=brehe,
                sentence="The car that you hit is a Chevrolet.",
                phrase_text="that you hit",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="relative clause antecedent",
                note_text="The antecedent of the relative pronoun is the noun modified by the relative clause.",
                origin_unit="relative clauses",
            ),
        ]
    )

    thiessen = "thiessen_academic_grammar_2025"
    rows.extend(
        [
            _sentence_row(
                document_id=thiessen,
                sentence="Jordan is rich, but he owns an old car.",
                topic="compound sentence",
                note_text="In a compound sentence, two independent clauses are linked by a coordinating conjunction.",
                origin_unit="combining clauses into compound and complex sentences",
            ),
            _sentence_row(
                document_id=thiessen,
                sentence="Because it was raining, he brought an umbrella.",
                topic="adverb clause",
                note_text="When an adverb clause comes first, the subordinating conjunction stays with that clause and a comma follows it.",
                origin_unit="complex sentences adverb clauses",
            ),
            _sentence_row(
                document_id=thiessen,
                sentence="We will watch a movie after we eat dinner.",
                topic="adverb clause of time",
                note_text="An adverb clause can tell when the action in the main clause happens.",
                origin_unit="complex sentences adverb clauses",
            ),
            _sentence_row(
                document_id=thiessen,
                sentence="If she comes late, I will leave without her.",
                topic="first conditional",
                note_text="The first conditional uses an if-clause for a possible future condition and a main clause for the expected result.",
                origin_unit="the first conditional",
            ),
            _sentence_row(
                document_id=thiessen,
                sentence="If I were an astronaut, I would love to travel to Mars.",
                topic="second conditional",
                note_text="The second conditional presents a hypothetical or unreal situation and typically uses would or could in the main clause.",
                origin_unit="the second conditional",
            ),
            _sentence_row(
                document_id=thiessen,
                sentence="He is neither rich, nor is he famous.",
                topic="paired conjunctions",
                note_text="With neither...nor, the second clause is coordinated with a negative alternative and often shows inversion after nor.",
                origin_unit="paired conjunctions",
            ),
            _sentence_row(
                document_id=thiessen,
                sentence="Not only is she kind, but she also donates a lot of money to charity.",
                topic="paired conjunctions",
                note_text="Not only...but also links parallel ideas and gives extra emphasis to the second clause.",
                origin_unit="paired conjunctions",
            ),
            _sentence_row(
                document_id=thiessen,
                sentence="While we are watching a movie, we will eat pizza.",
                topic="dependent clause",
                note_text="A dependent clause may be grammatically complete on its own, but its idea remains incomplete until it is attached to an independent clause.",
                origin_unit="independent and dependent clauses",
            ),
            _sentence_row(
                document_id=thiessen,
                sentence="If you are available for a meeting, please call me.",
                topic="conditional with imperative result",
                note_text="In a conditional sentence, the result clause can be an imperative when the speaker gives a directive based on the condition.",
                origin_unit="the first conditional",
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


def _stable_topic(row: dict[str, Any]) -> str:
    return _norm((row.get("source") or {}).get("topic"))


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build curated open-access book note rows.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    rows = build_rows()
    report = {
        "importer_version": "open_access_book_note_rows_v1",
        "documents": DOCUMENTS,
        "rows_total": len(rows),
        "sentence_rows": sum(1 for row in rows if row["context"]["node_type"] == "Sentence"),
        "phrase_rows": sum(1 for row in rows if row["context"]["node_type"] == "Phrase"),
        "topics": sorted({_stable_topic(row) for row in rows}),
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
