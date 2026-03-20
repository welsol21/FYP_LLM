"""Build curated book-note rows from the 2026-03 selected book packet.

This pack is intentionally selective. We only keep books that:

- expose clean machine-readable text,
- contain sentence/phrase-level explanations we can reuse as notes,
- fit the current book -> corpus workflow without manual cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DOCUMENTS = {
    "peter_simon_grammaring_guide_2013": {
        "source_path": "/home/vlad/winshare/Peter Simon - The Grammaring Guide to English Grammar.epub",
        "label": "Peter Simon - The Grammaring Guide to English Grammar",
    },
    "geraldine_woods_grammar_dummies_2017": {
        "source_path": "/home/vlad/winshare/Woods J. - English Grammar Dummies - 2017.epub",
        "label": "Geraldine Woods - English Grammar For Dummies",
    },
    "phyllis_dutwin_grammar_demystified_2010": {
        "source_path": "/home/vlad/winshare/Phyllis Dutwin - English Grammar Demystified - 2010.epub",
        "label": "Phyllis Dutwin - English Grammar Demystified",
    },
}

ASSESSMENT = {
    "wendy_anderson_dummies_2013_pdf": {
        "path": "/home/vlad/winshare/Wendy M. Anderson - English Grammar Essentials For Dummies - 2013.pdf",
        "role": "reject",
        "reason": "broken_or_mislabelled_file",
    },
    "wendy_anderson_dummies_2013_epub": {
        "path": "/home/vlad/winshare/Wendy M. Anderson - English Grammar Essentials For Dummies - 2013.epub",
        "role": "reject",
        "reason": "broken_or_mislabelled_file",
    },
    "oxford_basic_2015_pdf": {
        "path": "/home/vlad/winshare/Michael Swan_&_Catherine Walter-Oxford_English_Grammar_Course_Basic_2015.pdf",
        "role": "reject",
        "reason": "unstable_pdf_text_extraction_for_automation",
    },
    "timesaver3_zip": {
        "path": "/home/vlad/winshare/Timesaver3.zip",
        "role": "reject",
        "reason": "activity_workbook_not_note_source",
    },
    "dutwin_pdf": {
        "path": "/home/vlad/winshare/Phyllis Dutwin - English Grammar Demystified - 2010.pdf",
        "role": "secondary_note_source",
        "reason": "pdf_exists_but_epub_is_cleaner_for_extraction",
    },
    "dutwin_epub": {
        "path": "/home/vlad/winshare/Phyllis Dutwin - English Grammar Demystified - 2010.epub",
        "role": "note_source",
        "reason": "clean_html_structure_with_usable_sentence_and_phrase_notes",
    },
    "vince_ielts_2016_pdf": {
        "path": "/home/vlad/winshare/Vince.M.French.A.IELTS.Language.Practice.English.Grammar.and.Vocabulary.2016.pdf",
        "role": "reject",
        "reason": "text_extraction_failed",
    },
    "peter_simon_epub": {
        "path": "/home/vlad/winshare/Peter Simon - The Grammaring Guide to English Grammar.epub",
        "role": "note_source",
        "reason": "strong_sentence_and_phrase_explanations_with_clean_epub_text",
    },
    "peter_simon_mobi": {
        "path": "/home/vlad/winshare/Peter Simon - The Grammaring Guide to English Grammar.mobi",
        "role": "reject",
        "reason": "redundant_with_cleaner_epub_source",
    },
    "ellsworth_1997_pdf": {
        "path": "/home/vlad/winshare/Ellsworth Blanche, Higgins John A. - English Grammar Simplified -1997.pdf",
        "role": "reject",
        "reason": "scanned_pdf_without_usable_text_layer",
    },
    "ansell_2000_pdf": {
        "path": "/home/vlad/winshare/Ansell M. - Free English Grammar - 2000.pdf",
        "role": "reject",
        "reason": "garbled_text_extraction",
    },
    "woods_2017_epub": {
        "path": "/home/vlad/winshare/Woods J. - English Grammar Dummies - 2017.epub",
        "role": "note_source",
        "reason": "clean_epub_with_useful_passive_imperative_and_prepositional_phrase_notes",
    },
    "kolln_funk_2011_pdf": {
        "path": "/home/vlad/winshare/Understanding English Grammar - Kolln, Funk [9ed] (2011).pdf",
        "role": "reference_only",
        "reason": "good_reference_but_too_academic_for_direct_note_rows",
    },
    "leech_2006_pdf": {
        "path": "/home/vlad/winshare/Leech G. - A Glossary of English Grammar - (Glossaries in Linguistics) - 2006.pdf",
        "role": "reference_only",
        "reason": "terminology_glossary_not_note_source",
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
        },
        "target": {
            "audience_level": "intermediate",
            "note_text": note_text,
        },
        "template_projection": _template_projection(note_text),
    }


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    simon = "peter_simon_grammaring_guide_2013"
    rows.extend(
        [
            _sentence_row(
                document_id=simon,
                sentence="Penicillin was discovered by Alexander Fleming in 1928.",
                topic="passive voice",
                note_text="With the passive voice, the subject is the recipient of the action.",
                origin_unit="the difference between the active and passive voice",
            ),
            _sentence_row(
                document_id=simon,
                sentence="Tom's bike has been stolen.",
                topic="passive voice",
                note_text="We use the passive voice when we do not know who is performing the action.",
                origin_unit="the use of the passive voice",
            ),
            _sentence_row(
                document_id=simon,
                sentence="It has been decided to cancel next week's meeting.",
                topic="passive voice",
                note_text="We use the passive voice when we do not want to mention the agent.",
                origin_unit="the use of the passive voice",
            ),
            _sentence_row(
                document_id=simon,
                sentence="The murderer has been arrested.",
                topic="passive voice",
                note_text="We use the passive voice when the identity of the agent is obvious and can be omitted.",
                origin_unit="the use of the passive voice",
            ),
            _phrase_row(
                document_id=simon,
                sentence="The woman who answered the door was about forty years old.",
                phrase_text="who answered the door",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="relative clause",
                note_text="Relative clauses usually come after the nouns that they describe.",
                origin_unit="what is a relative clause",
            ),
            _phrase_row(
                document_id=simon,
                sentence="Do you know the guy who is talking to Will over there?",
                phrase_text="who is talking to Will over there",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="defining relative clause",
                note_text="A defining relative clause identifies the noun that it refers to.",
                origin_unit="defining relative clause",
            ),
            _phrase_row(
                document_id=simon,
                sentence="The Mona Lisa was painted by Leonardo da Vinci, who was also a prolific engineer and inventor.",
                phrase_text="who was also a prolific engineer and inventor",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="non-defining relative clause",
                note_text="A non-defining relative clause adds extra information about a preceding noun.",
                origin_unit="non-defining relative clause",
            ),
            _phrase_row(
                document_id=simon,
                sentence="The house in which Mozart was born is now a museum.",
                phrase_text="in which Mozart was born",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="relative clause",
                note_text="This pattern uses preposition + whom/which in the relative clause.",
                origin_unit="prepositions in relative clauses",
            ),
            _phrase_row(
                document_id=simon,
                sentence="Sometimes, I like listening to music that makes me sad.",
                phrase_text="that makes me sad",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="defining relative clause",
                note_text="A defining relative clause classifies the noun that it refers to.",
                origin_unit="defining relative clause",
            ),
        ]
    )

    woods = "geraldine_woods_grammar_dummies_2017"
    rows.extend(
        [
            _sentence_row(
                document_id=woods,
                sentence="Eat a balanced diet.",
                topic="imperative",
                note_text="Imperative verbs give commands.",
                origin_unit="commanding your attention: imperative",
            ),
            _sentence_row(
                document_id=woods,
                sentence="No matter what happens, hit the road.",
                topic="imperative",
                note_text="Most imperative verbs do not have a written subject; the subject is understood as you.",
                origin_unit="commanding your attention: imperative",
            ),
            _phrase_row(
                document_id=woods,
                sentence="In the afternoon the snow pelted Raymond on his little bald head.",
                phrase_text="In the afternoon",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="prepositional phrase",
                note_text="A prepositional phrase consists of a preposition and its object.",
                origin_unit="the objects of my affection: prepositional phrases and their objects",
            ),
            _phrase_row(
                document_id=woods,
                sentence="In the afternoon the snow pelted Raymond on his little bald head.",
                phrase_text="on his little bald head",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="prepositional phrase",
                note_text="A prepositional phrase consists of a preposition and its object.",
                origin_unit="the objects of my affection: prepositional phrases and their objects",
            ),
            _phrase_row(
                document_id=woods,
                sentence="Little Jane bounced the rubber ball in the hallway and bedroom.",
                phrase_text="in the hallway and bedroom",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="prepositional phrase",
                note_text="A prepositional phrase consists of a preposition and its object.",
                origin_unit="the objects of my affection: prepositional phrases and their objects",
            ),
        ]
    )

    dutwin = "phyllis_dutwin_grammar_demystified_2010"
    rows.extend(
        [
            _sentence_row(
                document_id=dutwin,
                sentence="The bottles inside the carton are all broken.",
                topic="prepositional phrase and agreement",
                note_text="The prepositional phrase does not determine the number of the verb; the subject does.",
                origin_unit="prepositional phrases",
            ),
            _phrase_row(
                document_id=dutwin,
                sentence="Neither of these boys wants a low-paying job this summer.",
                phrase_text="of these boys",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="prepositional phrase",
                note_text="The subject of a verb is not part of the prepositional phrase that follows it.",
                origin_unit="prepositional phrases",
            ),
            _phrase_row(
                document_id=dutwin,
                sentence="My dog, along with her seven puppies, has chewed all of the stuffing out of the sofa cushions.",
                phrase_text="along with her seven puppies",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="prepositional phrase",
                note_text="The subject of a verb is not part of the prepositional phrase that follows it.",
                origin_unit="prepositional phrases",
            ),
            _phrase_row(
                document_id=dutwin,
                sentence="The bottles inside the carton are all broken.",
                phrase_text="inside the carton",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="prepositional phrase",
                note_text="The prepositional phrase does not determine the number of the verb; the subject does.",
                origin_unit="prepositional phrases",
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


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _stable_topic(row: dict[str, Any]) -> str:
    return _norm((row.get("source") or {}).get("topic"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build curated book-note rows from the 2026-03 selected packet.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--assessment-json", required=True)
    args = parser.parse_args()

    rows = build_rows()
    report = {
        "dataset_version": "selected_books_v2",
        "rows_total": len(rows),
        "sentence_rows": sum(1 for row in rows if row["context"]["node_type"] == "Sentence"),
        "phrase_rows": sum(1 for row in rows if row["context"]["node_type"] == "Phrase"),
        "documents": {
            document_id: {
                "label": meta["label"],
                "source_path": meta["source_path"],
                "rows_total": sum(1 for row in rows if (row.get("source") or {}).get("document_id") == document_id),
            }
            for document_id, meta in DOCUMENTS.items()
        },
        "topics": sorted({_stable_topic(row) for row in rows}),
    }
    _write_jsonl(args.output_jsonl, rows)
    _write_json(args.report_json, report)
    _write_json(args.assessment_json, ASSESSMENT)
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
