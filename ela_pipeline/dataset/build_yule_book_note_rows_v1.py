"""Build a dense curated note pack from George Yule (1998).

This importer is intentionally denser than earlier selective book packs.
Yule contains strong explanatory chapters on:

- conditionals
- modals
- indirect objects
- relative clauses
- prepositions and particles

The goal is to extract a high-value sentence-heavy pack that can materially
improve the sentence layer of the projected corpus while still keeping phrase
notes transferable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_PATH = "/home/vlad/winshare/George Yule - Explaining English Grammar - 1998.djvu"
DOCUMENT_ID = "george_yule_explaining_english_grammar_1998"


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


def _phrase_row(
    *,
    sentence: str,
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
        "template_projection": _template_projection(note_text),
    }


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    rows.extend(
        [
            _sentence_row(
                sentence="Nowadays, if people want something, they just buy it.",
                topic="factual conditionals",
                note_text="Factual conditionals present a relationship that is generally true or habitually the case in the circumstances described.",
                origin_unit="conditionals overview and factual conditionals",
            ),
            _sentence_row(
                sentence="If they don't have any money, they use credit cards.",
                topic="factual conditionals",
                note_text="In a factual conditional, both clauses typically describe a regular pattern rather than a single imagined outcome.",
                origin_unit="conditionals overview and factual conditionals",
            ),
            _sentence_row(
                sentence="If you lend me some money, I'll pay you back tomorrow.",
                topic="predictive conditionals",
                note_text="Predictive conditionals present the main-clause event as a future possibility that depends on the if-clause situation.",
                origin_unit="predictive conditionals",
            ),
            _sentence_row(
                sentence="If you don't get paid, I may not get my money back.",
                topic="predictive conditionals",
                note_text="A predictive conditional often uses a modal in the main clause to mark how likely the result is.",
                origin_unit="predictive conditionals",
            ),
            _sentence_row(
                sentence="If the weather is okay, we'll have lunch outside.",
                topic="predictive conditionals",
                note_text="Predictive conditionals are common when speakers talk about future plans and their likely consequences.",
                origin_unit="what will happen if",
            ),
            _sentence_row(
                sentence="If you asked Jack, he might lend you the money.",
                topic="hypothetical conditionals",
                note_text="Hypothetical conditionals present an unlikely but still possible situation and typically use past forms in the if-clause.",
                origin_unit="hypothetical conditionals",
            ),
            _sentence_row(
                sentence="If he did have enough money, he would give you some.",
                topic="hypothetical conditionals",
                note_text="In hypothetical conditionals, the main clause usually contains would, could, or might to mark remoteness of possibility.",
                origin_unit="hypothetical conditionals",
            ),
            _sentence_row(
                sentence="If I had called Jack earlier, he would have helped.",
                topic="counterfactual conditionals",
                note_text="Counterfactual conditionals present an outcome against a past situation that is known not to have happened.",
                origin_unit="counterfactual conditionals",
            ),
            _sentence_row(
                sentence="If I were rich, I wouldn't have this problem.",
                topic="counterfactual conditionals",
                note_text="Counterfactual conditionals can use were to mark a situation presented as contrary to fact.",
                origin_unit="counterfactual conditionals",
            ),
            _sentence_row(
                sentence="If you have a poor connection or are cut off on a long distance call, tell the operator and ask to be reconnected.",
                topic="conditional directives",
                note_text="A conditional may be followed by an instruction when the speaker gives a directive that depends on the condition being met.",
                origin_unit="conditionals in procedures and advice texts",
            ),
            _sentence_row(
                sentence="If the wood has knots or broken lines, don't buy it.",
                topic="conditional directives",
                note_text="Conditionals followed by directives are common in procedural and advisory texts.",
                origin_unit="conditionals in procedures and advice texts",
            ),
            _sentence_row(
                sentence="There's no other choice, if you still want to go there.",
                topic="final if-clause",
                note_text="A final if-clause often works like an afterthought or reminder rather than the main point of the message.",
                origin_unit="initial and final if-clauses",
            ),
            _sentence_row(
                sentence="He may be a Democrat, but he happens to be right on this question.",
                topic="modals",
                note_text="With epistemic may, the speaker presents a proposition as a possibility rather than a certainty.",
                origin_unit="simple modals and meanings",
            ),
            _sentence_row(
                sentence="You should brush your teeth twice a day.",
                topic="should",
                note_text="With should, the core meaning is requirement, often interpreted in practice as advice or weak obligation.",
                origin_unit="the requirements of should",
            ),
            _sentence_row(
                sentence="The journey should take two or three days.",
                topic="should",
                note_text="Should can also express a reasonable assumption or probability about what is likely to happen.",
                origin_unit="the meanings of should",
            ),
            _sentence_row(
                sentence="You're supposed to be studying, not watching TV.",
                topic="be supposed to",
                note_text="Be supposed to expresses an external social expectation rather than a strong personal command from the speaker.",
                origin_unit="be supposed to",
            ),
            _sentence_row(
                sentence="It won't rain.",
                topic="negation and modals",
                note_text="With some epistemic modals, negation affects the action or event rather than the modal meaning itself.",
                origin_unit="negation and modals",
            ),
            _sentence_row(
                sentence="You may not leave.",
                topic="negation and modals",
                note_text="With root may, negation normally blocks permission rather than describing a negative event.",
                origin_unit="negation and modals",
            ),
            _sentence_row(
                sentence="You don't have to do it.",
                topic="negation and modals",
                note_text="Don't have to marks the absence of obligation, not a prohibition against doing the action.",
                origin_unit="negation and modals",
            ),
            _sentence_row(
                sentence="It can't work.",
                topic="negation and modals",
                note_text="Can't often conveys that something is not possible, which is stronger than merely saying it may not happen.",
                origin_unit="negation and modals",
            ),
            _sentence_row(
                sentence="It may not work.",
                topic="negation and modals",
                note_text="May not can mean that a negative outcome is possible rather than impossible.",
                origin_unit="negation and modals",
            ),
            _sentence_row(
                sentence="I sent some photos to my friend.",
                topic="indirect objects",
                note_text="In the after-preposition pattern, the indirect object appears as the goal of transfer in a prepositional phrase.",
                origin_unit="two indirect object constructions",
            ),
            _sentence_row(
                sentence="I sent my friend some photos.",
                topic="indirect objects",
                note_text="In the after-verb pattern, the indirect object is presented as a recipient who comes to have the transferred entity.",
                origin_unit="two indirect object constructions",
            ),
            _sentence_row(
                sentence="He described the picture to us.",
                topic="indirect objects",
                note_text="Many communication verbs prefer the after-preposition pattern because they focus on the act of communication rather than transfer of possession.",
                origin_unit="types of verbs with indirect objects",
            ),
            _sentence_row(
                sentence="It cost me a lot of money.",
                topic="indirect objects",
                note_text="Some verbs such as cost use only the after-verb pattern and express loss of possession rather than transfer to a goal.",
                origin_unit="transfer and not having",
            ),
            _sentence_row(
                sentence="I gave it to Jack.",
                topic="indirect objects and information structure",
                note_text="The after-preposition pattern is preferred when the indirect object is newer, heavier, or more informative than the direct object.",
                origin_unit="indirect objects and information structure",
            ),
            _sentence_row(
                sentence="I gave him some money.",
                topic="indirect objects and information structure",
                note_text="The after-verb pattern is preferred when the indirect object is shorter, more given, or pronominal and the direct object carries the newer information.",
                origin_unit="indirect objects and information structure",
            ),
            _sentence_row(
                sentence="I'm getting a present for Keiko.",
                topic="beneficiary constructions",
                note_text="With verbs of benefitting, a for-phrase can present the indirect object as a beneficiary without necessarily implying immediate possession.",
                origin_unit="indirect objects and benefitting",
            ),
            _sentence_row(
                sentence="I'm the kind of person who is always losing things.",
                topic="subject relative clause",
                note_text="A subject relative clause places the relative pronoun at the start of the clause where it functions as the subject.",
                origin_unit="subject relatives",
            ),
            _sentence_row(
                sentence="I didn't like the woman that I met.",
                topic="object relative clause",
                note_text="An object relative clause can use that to connect the noun to a clause where the relative element functions as the object.",
                origin_unit="object relatives",
            ),
            _sentence_row(
                sentence="I don't want to talk about the woman I met.",
                topic="zero relative clause",
                note_text="In informal English, object relatives often omit the relative pronoun entirely and use a zero relative.",
                origin_unit="object relatives and zero relative",
            ),
            _sentence_row(
                sentence="Can I meet the person that you talked to?",
                topic="stranded preposition relative clause",
                note_text="When the preposition stays at the end of the clause, the relative clause has a stranded-preposition pattern that is common in contemporary English.",
                origin_unit="after-preposition relatives",
            ),
            _sentence_row(
                sentence="Where is the person to whom you talked?",
                topic="fronted preposition relative clause",
                note_text="A fronted-preposition relative clause places the preposition before the relative pronoun and sounds more formal than the stranded pattern.",
                origin_unit="after-preposition relatives",
            ),
            _sentence_row(
                sentence="Did you talk to the girl whose bag was stolen?",
                topic="possessive relative clause",
                note_text="Possessive relative clauses use whose to link the noun to something associated with it inside the relative clause.",
                origin_unit="possessive relatives",
            ),
            _sentence_row(
                sentence="The man who lives next door has a cat.",
                topic="medial relative clause",
                note_text="Relative clauses often occur in medial position when they modify the subject of the main clause.",
                origin_unit="medial and final position",
            ),
            _sentence_row(
                sentence="The woman has a large dog that the cat likes.",
                topic="final relative clause",
                note_text="Relative clauses in final position commonly modify an object from the main clause.",
                origin_unit="medial and final position",
            ),
            _sentence_row(
                sentence="My neighbor, who is an English teacher, plays very loud music.",
                topic="non-restrictive relative clause",
                note_text="A non-restrictive relative clause adds extra information rather than identifying the noun, and it is marked off by separation markers such as commas.",
                origin_unit="restrictive and non-restrictive relatives",
            ),
            _sentence_row(
                sentence="My friend who's Japanese is coming.",
                topic="restrictive relative clause",
                note_text="A restrictive relative clause provides identifying information needed to pick out which person or thing is meant.",
                origin_unit="restrictive and non-restrictive relatives",
            ),
        ]
    )

    rows.extend(
        [
            _phrase_row(
                sentence="In the hallway he saw a young woman.",
                phrase_text="In the hallway",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="preposition phrase in initial position",
                note_text="In initial position, a prepositional phrase can create a starting point, setting, or framework for what follows.",
                origin_unit="prepositions particles and information structure",
            ),
            _phrase_row(
                sentence="She entered his apartment at exactly twelve thirty.",
                phrase_text="at exactly twelve thirty",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="preposition phrase in final position",
                note_text="In final position, a prepositional phrase often contributes additional circumstantial information and may carry the newer detail in the clause.",
                origin_unit="prepositions particles and information structure",
            ),
            _phrase_row(
                sentence="There's a car in the garage.",
                phrase_text="in the garage",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="prepositional phrase as context",
                note_text="A prepositional phrase often expresses the larger context or location within which the main entity is interpreted.",
                origin_unit="prepositions particles and information structure",
            ),
            _phrase_row(
                sentence="I sent some photos to my friend.",
                phrase_text="to my friend",
                part_of_speech="prepositional phrase",
                grammatical_role="complement",
                topic="after-preposition indirect object",
                note_text="In the after-preposition indirect object pattern, the recipient appears in a prepositional phrase headed by to.",
                origin_unit="two indirect object constructions",
            ),
            _phrase_row(
                sentence="I'm getting a present for Keiko.",
                phrase_text="for Keiko",
                part_of_speech="prepositional phrase",
                grammatical_role="complement",
                topic="beneficiary for-phrase",
                note_text="With many beneficiary constructions, the indirect object is presented in a for-phrase rather than in after-verb position.",
                origin_unit="indirect objects and benefitting",
            ),
            _phrase_row(
                sentence="I'm the kind of person who is always losing things.",
                phrase_text="who is always losing things",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="subject relative clause",
                note_text="A relative clause following a noun gives extra information about that noun, and here the relative element functions as the subject of the clause.",
                origin_unit="subject relatives",
            ),
            _phrase_row(
                sentence="I didn't like the woman that I met.",
                phrase_text="that I met",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="object relative clause",
                note_text="This restrictive relative clause identifies the noun and uses the relative element as the object inside the clause.",
                origin_unit="object relatives",
            ),
            _phrase_row(
                sentence="Can I meet the person that you talked to?",
                phrase_text="that you talked to",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="stranded preposition relative clause",
                note_text="This relative clause uses a stranded preposition, leaving the preposition at the end of the clause.",
                origin_unit="after-preposition relatives",
            ),
            _phrase_row(
                sentence="Where is the person to whom you talked?",
                phrase_text="to whom you talked",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="fronted preposition relative clause",
                note_text="This relative clause fronts the preposition together with the relative marker, creating a more formal pattern.",
                origin_unit="after-preposition relatives",
            ),
            _phrase_row(
                sentence="Did you talk to the girl whose bag was stolen?",
                phrase_text="whose bag was stolen",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="possessive relative clause",
                note_text="This possessive relative clause uses whose to connect the noun with something associated with it.",
                origin_unit="possessive relatives",
            ),
            _phrase_row(
                sentence="My neighbor, who is an English teacher, plays very loud music.",
                phrase_text="who is an English teacher",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="non-restrictive relative clause",
                note_text="A non-restrictive relative clause adds extra information about a noun that is already identified.",
                origin_unit="restrictive and non-restrictive relatives",
            ),
            _phrase_row(
                sentence="The woman has a large dog that the cat likes.",
                phrase_text="that the cat likes",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="final object relative clause",
                note_text="This relative clause follows the noun it modifies and identifies it by linking it to another clause.",
                origin_unit="medial and final position",
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
    parser = argparse.ArgumentParser(description="Build curated book-note rows from George Yule (1998).")
    parser.add_argument(
        "--output-jsonl",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_yule_v1/yule_book_note_rows_v1.jsonl",
    )
    parser.add_argument(
        "--report-json",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_yule_v1/yule_book_note_rows_v1.report.json",
    )
    args = parser.parse_args()

    rows = build_rows()
    report = {
        "document_id": DOCUMENT_ID,
        "source_path": SOURCE_PATH,
        "rows_total": len(rows),
        "sentence_rows": sum(1 for row in rows if (row.get("context") or {}).get("node_type") == "Sentence"),
        "phrase_rows": sum(1 for row in rows if (row.get("context") or {}).get("node_type") == "Phrase"),
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
