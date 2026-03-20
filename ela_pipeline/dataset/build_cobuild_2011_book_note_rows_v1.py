"""Build a dense curated note pack from Collins COBUILD English Grammar (2011).

This importer is intentionally sentence-first. The current corpus bottleneck is
the sentence layer, so the pack emphasizes:

- conditional clauses
- passive constructions
- split / cleft sentences
- impersonal it
- existential there

Phrase notes are included selectively, mostly for relative clauses where the
book gives strong, transferable explanations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_PATH = "/home/vlad/winshare/Collins Cobuild English Grammar - 2011.epub"
DOCUMENT_ID = "collins_cobuild_english_grammar_2011"


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
                sentence="If they lose weight during an illness, they soon regain it afterwards.",
                topic="general conditional clause",
                note_text="A conditional clause presents a possible or typical situation together with its consequence.",
                origin_unit="8.25 conditional clauses",
            ),
            _sentence_row(
                sentence="Government cannot operate effectively unless it is free to take its own decisions.",
                topic="unless clause",
                note_text="Unless means except if and introduces the condition that would prevent the result.",
                origin_unit="8.25-8.26 unless",
            ),
            _sentence_row(
                sentence="If you do that I shall be very pleased.",
                topic="if clause consequence",
                note_text="Conditional clauses usually begin with if and link the consequence in the main clause to a stated condition.",
                origin_unit="8.26 if-clauses",
            ),
            _sentence_row(
                sentence="If you weren’t here, she would get rid of me in no time.",
                topic="unreal conditional with modal main clause",
                note_text="When the condition is unreal, the main clause normally uses a modal such as would, could, or might.",
                origin_unit="8.27 modals in conditional sentences",
            ),
            _sentence_row(
                sentence="If you dry your washing outdoors, wipe the line first.",
                topic="imperative conditional clause",
                note_text="Conditional clauses are often used with imperatives when an instruction depends on a condition.",
                origin_unit="8.27 imperatives in conditional sentences",
            ),
            _sentence_row(
                sentence="I’ll scream if you say that again.",
                topic="first conditional",
                note_text="In the first conditional, the if-clause uses the present simple while the main clause presents a future result.",
                origin_unit="8.28 first conditional",
            ),
            _sentence_row(
                sentence="If I had more time, I would happily offer to help.",
                topic="second conditional",
                note_text="In the second conditional, a past form in the if-clause combines with would or should to present an unlikely situation.",
                origin_unit="8.28 second conditional",
            ),
            _sentence_row(
                sentence="If I had tried a bit harder, I would have passed that exam.",
                topic="third conditional",
                note_text="In the third conditional, the if-clause uses the past perfect and the main clause uses would have or should have for an unreal past result.",
                origin_unit="8.28 third conditional",
            ),
            _sentence_row(
                sentence="Water boils if you heat it to 100°C.",
                topic="zero conditional",
                note_text="The zero conditional uses present forms in both clauses to express a general truth or regular result.",
                origin_unit="8.28 zero conditional",
            ),
            _sentence_row(
                sentence="If anyone doubts this, they should look at the facts.",
                topic="present possibility conditional",
                note_text="For a possible present situation, the if-clause often uses the present simple and the main clause uses a modal.",
                origin_unit="8.31 possible situations in the present",
            ),
            _sentence_row(
                sentence="If I survive this experience, I’ll never leave you again.",
                topic="future conditional",
                note_text="When talking about something that may happen in the future, the conditional clause typically uses the present simple and the main clause uses will or shall.",
                origin_unit="8.32 future possibility",
            ),
            _sentence_row(
                sentence="If that should happen, you will be blamed.",
                topic="formal should conditional",
                note_text="In formal style, should in the conditional clause presents a possible future situation.",
                origin_unit="8.33 formal should",
            ),
            _sentence_row(
                sentence="If we were to move north, we would be able to buy a bigger house.",
                topic="were-to conditional",
                note_text="Were to with an infinitive is a formal way to present a remote future possibility.",
                origin_unit="8.33 were to",
            ),
            _sentence_row(
                sentence="If I were a guy, I would look like my dad.",
                topic="unlikely conditional",
                note_text="An unlikely present situation is often expressed with a past form in the if-clause and would, should, or might in the main clause.",
                origin_unit="8.34 unlikely situations",
            ),
            _sentence_row(
                sentence="Perhaps if he had realized that, he would have run away while there was still time.",
                topic="counterfactual past conditional",
                note_text="A counterfactual conditional presents what might have happened in the past but did not happen.",
                origin_unit="8.35 what might have been",
            ),
            _sentence_row(
                sentence="Should ministers demand an inquiry, we would welcome it.",
                topic="inverted conditional",
                note_text="In formal English, should, were, or had can be fronted and if omitted in a conditional clause.",
                origin_unit="8.36 inverted conditionals",
            ),
            _sentence_row(
                sentence="If in doubt, ask at your local library.",
                topic="reduced if phrase",
                note_text="A reduced if-phrase can replace a fuller conditional clause with be when the meaning is clear.",
                origin_unit="8.37 reduced if-phrase",
            ),
            _sentence_row(
                sentence="Ordering is quick and easy provided you have access to the internet.",
                topic="necessary-condition clause",
                note_text="Provided, providing, as long as, and only if introduce a condition that is necessary for the result.",
                origin_unit="8.38 necessary conditions",
            ),
            _sentence_row(
                sentence="Even if you don’t get the job this time, there will be many exciting opportunities in the future.",
                topic="even if clause",
                note_text="Even if marks a condition that does not change the outcome stated in the main clause.",
                origin_unit="8.39 even if",
            ),
            _sentence_row(
                sentence="A girl from my class was chosen to do the reading.",
                topic="general passive voice",
                note_text="The passive lets you present an event from the point of view of the person or thing affected rather than the performer.",
                origin_unit="9.3 the passive",
            ),
            _sentence_row(
                sentence="He was being treated for a stomach ulcer.",
                topic="passive form",
                note_text="Passive forms consist of an appropriate form of be followed by the -ed participle of the verb.",
                origin_unit="9.9 formation of the passive",
            ),
            _sentence_row(
                sentence="The fence between the two properties had been removed.",
                topic="passive without performer",
                note_text="A passive clause often omits the performer when the performer is unknown, unimportant, or already understood.",
                origin_unit="9.10 omitted performer",
            ),
            _sentence_row(
                sentence="Such items should be carefully packed in boxes.",
                topic="passive without performer",
                note_text="The passive is common when the focus is on what should be done rather than on who does it.",
                origin_unit="9.10 omitted performer",
            ),
            _sentence_row(
                sentence="Food is put in jars, the jars and their contents are heated to a temperature which is maintained long enough to ensure that all bacteria, moulds and viruses are destroyed.",
                topic="process passive",
                note_text="In accounts of processes and experiments, the passive keeps the focus on what happens rather than on the performer.",
                origin_unit="9.11 process descriptions",
            ),
            _sentence_row(
                sentence="It was agreed that he would come and see us again the next day.",
                topic="passive reporting it structure",
                note_text="The passive of reporting verbs is often used in impersonal it structures when the source of the report is general or already understood.",
                origin_unit="9.12 passive reporting verbs",
            ),
            _sentence_row(
                sentence="Some of the children were adopted by local couples.",
                topic="passive by phrase",
                note_text="A by-phrase can name the performer at the end of a passive clause, where it receives end focus.",
                origin_unit="9.14 performer with by",
            ),
            _sentence_row(
                sentence="A circle was drawn in the dirt with a stick.",
                topic="passive with instrument",
                note_text="With can name the instrument or means used to perform the action in a passive clause.",
                origin_unit="9.15 mentioning things or methods used",
            ),
            _sentence_row(
                sentence="The strong taste can be removed by changing the cooking water.",
                topic="passive by ing method",
                note_text="By plus an -ing form can express the method by which a result is achieved.",
                origin_unit="9.15 by + -ing method",
            ),
            _sentence_row(
                sentence="The room was filled with people.",
                topic="state passive with with",
                note_text="Some state passives use with to introduce what creates or characterizes the state.",
                origin_unit="9.16 passive of state verbs",
            ),
            _sentence_row(
                sentence="Such expectations are drummed into every growing child.",
                topic="passive phrasal verb",
                note_text="Transitive phrasal verbs can also appear in the passive.",
                origin_unit="9.17 passive phrasal verbs",
            ),
            _sentence_row(
                sentence="The meeting is scheduled for February 14.",
                topic="lexically common passive",
                note_text="Some verbs are especially common in passive form because the performer is not normally mentioned.",
                origin_unit="9.18 verbs usually used in the passive",
            ),
            _sentence_row(
                sentence="It was Ted who broke the news to me.",
                topic="it cleft",
                note_text="An it-cleft focuses one constituent by placing it after It is or It was and following it with a relative clause.",
                origin_unit="9.25-9.26 split sentences",
            ),
            _sentence_row(
                sentence="It was in Paris that I first saw these films.",
                topic="it cleft adverbial focus",
                note_text="A split sentence can focus time, place, or other circumstances rather than the subject or object.",
                origin_unit="9.27 focus on circumstances",
            ),
            _sentence_row(
                sentence="What I did was to make a plan.",
                topic="what cleft action",
                note_text="A what-cleft can focus an action by placing it after be.",
                origin_unit="9.28 what to focus on an action",
            ),
            _sentence_row(
                sentence="What you need is a doctor.",
                topic="what cleft need/want",
                note_text="A what-cleft with want or need highlights the thing wanted or needed.",
                origin_unit="9.30 what someone wants or needs",
            ),
            _sentence_row(
                sentence="All they want is a holiday.",
                topic="all cleft",
                note_text="All can replace what when the construction emphasizes that just one thing is wanted or needed.",
                origin_unit="9.30 all instead of what",
            ),
            _sentence_row(
                sentence="It’s lovely here.",
                topic="impersonal it place or situation",
                note_text="Impersonal it can describe a situation or place without referring to a concrete antecedent.",
                origin_unit="9.31-9.34 place or situation",
            ),
            _sentence_row(
                sentence="It’s still raining.",
                topic="impersonal it weather",
                note_text="Impersonal it is used in weather expressions.",
                origin_unit="9.36 weather",
            ),
            _sentence_row(
                sentence="It’s eight o’clock.",
                topic="impersonal it time",
                note_text="Impersonal it is also used to give the time or date.",
                origin_unit="9.37 time and date",
            ),
            _sentence_row(
                sentence="It was 11 o’clock at night when 16 armed men came to my house.",
                topic="it time-focus split sentence",
                note_text="It is or It was with a time expression and a when-clause gives special emphasis to the time of an event.",
                origin_unit="9.38 emphasizing time",
            ),
            _sentence_row(
                sentence="It’s nice to see you with your books for a change.",
                topic="it extraposition to infinitive",
                note_text="It plus be, an adjective, and a to-infinitive lets the clause comment on an action while keeping the heavier information at the end.",
                origin_unit="9.39 adjective + to-infinitive",
            ),
            _sentence_row(
                sentence="It is strange that it hasn’t been noticed before.",
                topic="it extraposition that clause",
                note_text="It plus be, an adjective or noun, and a that-clause comments on a fact or situation.",
                origin_unit="9.42 adjective + that-clause",
            ),
            _sentence_row(
                sentence="It takes an hour to get to Northampton.",
                topic="it with take or cost",
                note_text="It with take or cost introduces the amount of time, effort, or money needed for an action.",
                origin_unit="9.40 take and cost",
            ),
            _sentence_row(
                sentence="He found it hard to make friends.",
                topic="anticipatory object it",
                note_text="With find or think, it can stand as anticipatory object before an adjective and infinitive or clause.",
                origin_unit="9.40 find and think",
            ),
            _sentence_row(
                sentence="There were thirty boys in the class.",
                topic="existential there basic",
                note_text="There plus be introduces the existence or presence of something and makes the following noun phrase new information.",
                origin_unit="9.46 existence or presence",
            ),
            _sentence_row(
                sentence="There was a knock at his door.",
                topic="existential there event",
                note_text="There plus be can also introduce an event as something that happened.",
                origin_unit="9.48 event introduction",
            ),
            _sentence_row(
                sentence="There was a storm raging outside.",
                topic="existential there with ing",
                note_text="There plus be, a noun phrase, and an -ing participle can describe what is present in a scene or situation.",
                origin_unit="9.49 scene description",
            ),
            _sentence_row(
                sentence="There were a lot of people there.",
                topic="existential there agreement",
                note_text="In existential there constructions, agreement normally follows the noun phrase that comes after be.",
                origin_unit="9.50 verb agreement",
            ),
            _sentence_row(
                sentence="There appears to be a lot of confusion on this point.",
                topic="existential there with seem or appear",
                note_text="There can occur with seem or appear to present something as apparently existing.",
                origin_unit="9.53 there with seem or appear",
            ),
            _sentence_row(
                sentence="There is expected to be an announcement about the proposed building.",
                topic="existential there with passive reporting verb",
                note_text="There can be followed by a passive reporting verb to relay what is said or expected to exist or happen.",
                origin_unit="9.53 there with passive reporting verb",
            ),
            _sentence_row(
                sentence="There remained a risk of war.",
                topic="existential there formal literary",
                note_text="In formal style, verbs such as remain, follow, and come can appear after there.",
                origin_unit="9.54 formal and literary uses",
            ),
        ]
    )

    rows.extend(
        [
            _phrase_row(
                sentence="I met the woman who lives next door.",
                phrase_text="who lives next door",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="defining relative clause",
                note_text="A defining relative clause identifies which person or thing is meant.",
                origin_unit="8.85 defining relative clause",
            ),
            _phrase_row(
                sentence="I saw Miley Cyrus, who was staying at the hotel opposite.",
                phrase_text="who was staying at the hotel opposite",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="non-defining relative clause",
                note_text="A non-defining relative clause adds extra information that is not needed to identify the noun.",
                origin_unit="8.85 non-defining relative clause",
            ),
            _phrase_row(
                sentence="He is the only person who might be able to help.",
                phrase_text="who might be able to help",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="subject relative clause",
                note_text="A relative pronoun usually acts as the subject or object inside the relative clause.",
                origin_unit="8.84 relative pronouns",
            ),
            _phrase_row(
                sentence="Give it to the man wearing the sunglasses.",
                phrase_text="wearing the sunglasses",
                part_of_speech="participle clause",
                grammatical_role="modifier",
                topic="reduced relative clause",
                note_text="A relative clause can sometimes be reduced to an -ing participle clause.",
                origin_unit="8.88 -ing participle clauses",
            ),
            _phrase_row(
                sentence="These are the people to whom Catherine was referring.",
                phrase_text="to whom Catherine was referring",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="fronted preposition relative clause",
                note_text="In formal English, the preposition can be placed before whom or which at the start of a relative clause.",
                origin_unit="8.98 formal use with preposition fronting",
            ),
            _phrase_row(
                sentence="I am writing a letter to Nigel, whose father is ill.",
                phrase_text="whose father is ill",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="possessive relative clause",
                note_text="Relative clauses with whose link the noun to something associated with it inside the clause.",
                origin_unit="8.101 using whose",
            ),
            _phrase_row(
                sentence="He came from Brighton, where Lisa had once spent a holiday.",
                phrase_text="where Lisa had once spent a holiday",
                part_of_speech="relative clause",
                grammatical_role="modifier",
                topic="relative adverb clause",
                note_text="Where can function as a relative marker in a clause that adds information about a place.",
                origin_unit="8.104 where in non-defining clauses",
            ),
            _phrase_row(
                sentence="It was from Francis that she first heard the news.",
                phrase_text="from Francis",
                part_of_speech="prepositional phrase",
                grammatical_role="modifier",
                topic="focused prepositional phrase",
                note_text="A split sentence can focus a prepositional phrase in order to emphasize the circumstances of an event.",
                origin_unit="9.27 focus on prepositional phrase",
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
    parser = argparse.ArgumentParser(description="Build curated book-note rows from Collins COBUILD English Grammar (2011).")
    parser.add_argument(
        "--output-jsonl",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_cobuild_2011_v1/cobuild_2011_book_note_rows_v1.jsonl",
    )
    parser.add_argument(
        "--report-json",
        default="/home/vlad/Dev/FYP_LLM/data/processed_book_notes_cobuild_2011_v1/cobuild_2011_book_note_rows_v1.report.json",
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
