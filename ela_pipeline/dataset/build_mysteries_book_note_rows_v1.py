"""Build curated book-note rows from Mysteries of English Grammar (Calude & Bauer, 2022).

The book explores contested, variable, and frequently misunderstood areas of
English grammar. Its strength is in providing clear example sentences alongside
nuanced linguistic explanations of phenomena such as double negatives, the
progressive with stative verbs, countability shifts, number agreement, and
possessive alternation.

Curation selects sentence and phrase rows that carry a self-contained,
learner-facing explanation grounded in the book's content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_PATH = (
    "/home/vlad/winshare/books/"
    "Calude Andreea S., Bauer Laurie - "
    "Mysteries of English Grammar. A Guide to Complexities of the English Language - 2022.pdf"
)
DOCUMENT_ID = "calude_bauer_mysteries_english_grammar_2022"


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

    # ── adjectives ────────────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="This red car.",
            topic="adjectives attributive",
            note_text="An adjective used before a noun is in attributive position; it directly modifies the noun as part of the noun phrase.",
            origin_unit="functions of adjectives",
        ),
        _sentence_row(
            sentence="My car is red.",
            topic="adjectives predicative",
            note_text="An adjective used after a copular verb is in predicative position; it describes the subject of the sentence rather than modifying the noun directly.",
            origin_unit="functions of adjectives",
        ),
        _sentence_row(
            sentence="The painting seems beautiful.",
            topic="adjectives predicative",
            note_text="Copular verbs such as seem, appear, become, and feel link the subject to a predicative adjective that describes a property of the subject.",
            origin_unit="copular verbs and predicative adjectives",
        ),
        _sentence_row(
            sentence="This performance was very theatrical.",
            topic="adjectives gradability",
            note_text="Most adjectives are gradable, meaning they can be modified by degree adverbs such as very, quite, and rather.",
            origin_unit="gradable adjectives",
        ),
        _sentence_row(
            sentence="The water is growing shallow.",
            topic="adjectives predicative",
            note_text="Verbs of change such as grow, turn, and go can function as copular verbs and take a predicative adjective.",
            origin_unit="copular verbs and predicative adjectives",
        ),
        _sentence_row(
            sentence="The rich are not like you and me: they have more money.",
            topic="adjectives as nouns",
            note_text="Some adjectives can function as nouns when preceded by the definite article, referring to a class of people sharing that property.",
            origin_unit="adjectives used as nouns",
        ),
        _sentence_row(
            sentence="The improbable we do at once, the impossible takes a little longer.",
            topic="adjectives as nouns",
            note_text="Adjectives used as nouns with the definite article can refer to abstract concepts or qualities treated as a collective category.",
            origin_unit="adjectives used as nouns",
        ),
        _sentence_row(
            sentence="I left the house quiet.",
            topic="adjectives vs adverbs",
            note_text="An adjective after the verb and its object describes the state of the subject or object rather than the manner of the action.",
            origin_unit="adjectives and adverbs",
        ),
        _sentence_row(
            sentence="I left the house quietly.",
            topic="adjectives vs adverbs",
            note_text="An adverb ending in -ly modifies the verb and describes the manner in which the action is performed.",
            origin_unit="adjectives and adverbs",
        ),
        _sentence_row(
            sentence="New stock arriving daily.",
            topic="adjectives vs adverbs",
            note_text="Some adverbs have the same form as adjectives without the -ly suffix; daily, weekly, and monthly can serve as either adjective or adverb depending on position.",
            origin_unit="flat adverbs",
        ),
    ])

    # ── comparatives ──────────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="This was the most unkindest cut of all.",
            topic="double comparative",
            note_text="The double comparative adds both the -est suffix and the word most to the same adjective; once common in earlier English, it is now considered non-standard in formal writing.",
            origin_unit="double comparative construction",
        ),
        _sentence_row(
            sentence="She is prettier than me.",
            topic="comparatives and case",
            note_text="After than used as a preposition, the object form of the pronoun is standard; after than used as a conjunction, the subject form is also possible.",
            origin_unit="than as preposition or conjunction",
        ),
        _sentence_row(
            sentence="He looked a bit younger than she, perhaps in his early eighties.",
            topic="comparatives and case",
            note_text="When than introduces a full understood clause, the subject pronoun is appropriate; the sentence reads as 'younger than she was'.",
            origin_unit="than as conjunction",
        ),
    ])

    # ── countability ──────────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="There were a certain amount of mothers and prams.",
            topic="countability amount of",
            note_text="Amount of is traditionally used with mass nouns, but it frequently appears with count nouns in everyday usage, reflecting a gradual shift in English countability norms.",
            origin_unit="amount of with count and mass nouns",
        ),
        _sentence_row(
            sentence="There would be just the right amount of people on the street.",
            topic="countability amount of",
            note_text="Amount of followed by a plural count noun is now common enough that many speakers do not notice it; prescriptive grammars may still prefer number of for countable items.",
            origin_unit="amount of with count and mass nouns",
        ),
        _sentence_row(
            sentence="We're getting very little results from it.",
            topic="countability instability",
            note_text="Little is traditionally a quantifier for mass nouns, but its use with countable plurals illustrates how the boundary between count and mass nouns is not always stable.",
            origin_unit="instability of countability",
        ),
        _sentence_row(
            sentence="I've ordered some rice, but none has arrived yet.",
            topic="none agreement mass",
            note_text="None with a mass noun typically takes a singular verb because the noun is treated as an undivided quantity.",
            origin_unit="none with count and mass nouns",
        ),
        _sentence_row(
            sentence="I've ordered some biscuits, but none have arrived yet.",
            topic="none agreement count",
            note_text="None with a countable plural noun can take either a singular or plural verb; plural agreement is common in contemporary English.",
            origin_unit="none with count and mass nouns",
        ),
        _sentence_row(
            sentence="None of the milk I've ordered has arrived yet.",
            topic="none agreement mass",
            note_text="None of followed by a mass noun phrase strongly favours singular verb agreement because the reference is to an undivided substance.",
            origin_unit="none agreement patterns",
        ),
        _sentence_row(
            sentence="None of the books I've ordered have arrived yet.",
            topic="none agreement count",
            note_text="None of followed by a plural count noun phrase allows plural agreement, which treats each item in the set individually.",
            origin_unit="none agreement patterns",
        ),
    ])

    # ── double negatives ───────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="I didn't give nothing to nobody.",
            topic="double negatives negative concord",
            note_text="In negative concord, multiple negative words within a clause reinforce a single negative meaning rather than cancelling each other out, as formal logic would predict.",
            origin_unit="negative concord and mathematical logic",
        ),
        _sentence_row(
            sentence="I know nothing, nor you neither.",
            topic="double negatives negative concord",
            note_text="Negative concord was once standard in English and remains natural in many dialects; formal written English now typically treats each negative element as logically independent.",
            origin_unit="history of negative concord",
        ),
    ])

    # ── gender ────────────────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="Whoever your professor is, they will not appreciate you handing in essays late.",
            topic="singular they",
            note_text="Singular they is used to refer to an individual whose sex is unknown or irrelevant; this usage has a long history in English going back to Shakespeare.",
            origin_unit="singular they and gender-neutral reference",
        ),
    ])

    # ── number agreement ──────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="The cars are in the garage.",
            topic="subject verb agreement plural",
            note_text="A plural subject requires a plural verb form in standard English; the verb must agree with the number of the subject.",
            origin_unit="number agreement basics",
        ),
        _sentence_row(
            sentence="The oak grows in England.",
            topic="subject verb agreement singular generic",
            note_text="A singular generic noun phrase, referring to a whole species or category, takes a singular verb even when the reference is general.",
            origin_unit="generic reference and agreement",
        ),
        _sentence_row(
            sentence="Oaks grow in England.",
            topic="subject verb agreement plural generic",
            note_text="A bare plural noun phrase used generically takes a plural verb and can refer to the species as a whole rather than specific individuals.",
            origin_unit="generic reference and agreement",
        ),
        _sentence_row(
            sentence="The owl and the pussy cat are in the boat.",
            topic="coordinated subjects agreement",
            note_text="When two subjects are joined by and, the resulting noun phrase is normally treated as plural and takes a plural verb.",
            origin_unit="coordinated subjects and agreement",
        ),
        _sentence_row(
            sentence="My friend and sponsor is Kim.",
            topic="coordinated subjects single referent",
            note_text="When two conjoined nouns refer to a single person or entity, a singular verb may be used because only one individual is intended.",
            origin_unit="coordinated subjects with single referent",
        ),
        _sentence_row(
            sentence="One and a half letters are still visible, painted on the wall.",
            topic="fractional expressions agreement",
            note_text="Fractional expressions greater than one can take a plural verb because the overall quantity is understood as more than a single unit.",
            origin_unit="fractional expressions and agreement",
        ),
        _sentence_row(
            sentence="Our international students is a branch of that business.",
            topic="agreement error proximity",
            note_text="Agreement errors can arise when the verb is attracted to a nearby noun rather than the true grammatical subject; this is called attraction or proximity agreement.",
            origin_unit="lack of concord and proximity attraction",
        ),
    ])

    # ── possession ────────────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="The woman's ideas were stimulating.",
            topic="possessive s genitive",
            note_text="The 's genitive is the default possessive form in English and is most natural with animate possessors.",
            origin_unit="s genitive and of genitive",
        ),
        _sentence_row(
            sentence="The woman I spoke to's ideas were stimulating.",
            topic="group genitive",
            note_text="The group genitive attaches 's to the end of an entire phrase rather than to the head noun alone; it is grammatical but can sound awkward with longer phrases.",
            origin_unit="group genitive",
        ),
    ])

    # ── prepositions ──────────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="He is from Waikato.",
            topic="prepositions with place names",
            note_text="The choice of preposition with place names can vary by region and register; from signals the origin or source location of the subject.",
            origin_unit="prepositions with place names",
        ),
        _sentence_row(
            sentence="To whom it may concern.",
            topic="prepositions fronted formal",
            note_text="In formal style, a preposition can be placed before the relative or interrogative pronoun rather than left at the end of the clause.",
            origin_unit="preposition placement formal vs informal",
        ),
        _sentence_row(
            sentence="Our father, which art in heaven.",
            topic="prepositions relative pronouns",
            note_text="Which was once used to refer to persons in certain formal and religious registers; modern English normally uses who for personal reference.",
            origin_unit="which vs who in relative clauses",
        ),
    ])

    # ── progressive ───────────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="I'm lovin' it!",
            topic="progressive stative verb",
            note_text="Stative verbs like love traditionally resist the progressive, but they appear in it for expressive or marketing effect, highlighting an ongoing emotional experience.",
            origin_unit="stative verbs with progressive",
        ),
        _sentence_row(
            sentence="Look at him, he is always sitting there doing nothing.",
            topic="progressive habitual disapproval",
            note_text="The progressive combined with always can express irritation or disapproval of a repeated action, adding an emotional charge that the simple present lacks.",
            origin_unit="always with progressive for disapproval",
        ),
        _sentence_row(
            sentence="Michael is always taking cigarette breaks.",
            topic="progressive habitual disapproval",
            note_text="Always with the progressive marks a habitual action and typically signals the speaker's negative attitude toward the frequency of that behaviour.",
            origin_unit="always with progressive for disapproval",
        ),
        _sentence_row(
            sentence="They are always being desperate and tragic.",
            topic="progressive with be",
            note_text="The progressive of be followed by an adjective can describe temporary or performed behaviour rather than a permanent state.",
            origin_unit="progressive with stative be",
        ),
    ])

    # ── double be ─────────────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="What John moved to the cupboard was her cheese.",
            topic="what cleft",
            note_text="A what-cleft sentence moves a constituent into focus by embedding it in a what-clause linked to the main clause by a form of be.",
            origin_unit="cleft constructions overview",
        ),
        _sentence_row(
            sentence="It was John who moved her cheese to the cupboard.",
            topic="it cleft",
            note_text="An it-cleft places the focused element between it was and a relative clause, highlighting that element as the new or contrastive information.",
            origin_unit="cleft constructions overview",
        ),
        _sentence_row(
            sentence="What Dostoevsky is is a murder witness.",
            topic="double be construction",
            note_text="The double be construction arises when a what-cleft places a form of be at the boundary between the embedded clause and the main clause, producing two adjacent be forms.",
            origin_unit="double be construction",
        ),
        _sentence_row(
            sentence="The fact remains is that people's living standards are being cut.",
            topic="double be intrusion",
            note_text="Double be can also arise through syntactic blending, where a speaker merges two constructions and inserts an extra is into the result.",
            origin_unit="double be as blending",
        ),
    ])

    # ── shadow pronouns ───────────────────────────────────────────────────────
    rows.extend([
        _sentence_row(
            sentence="This is the girl that Peter gave her some cakes.",
            topic="shadow pronouns resumptive",
            note_text="A shadow pronoun repeats the reference of the relative operator inside the relative clause; it can help speakers process complex relative clauses in real time.",
            origin_unit="shadow pronouns and island rescue",
        ),
        _sentence_row(
            sentence="This is the girl that Peter said that John gave some cakes to her.",
            topic="shadow pronouns long distance",
            note_text="Shadow pronouns appear more often when the gap between the relative operator and its position inside the clause is long or crosses multiple clause boundaries.",
            origin_unit="shadow pronouns and processing",
        ),
    ])

    # ── phrase rows ───────────────────────────────────────────────────────────
    rows.extend([
        _phrase_row(
            sentence="This red car.",
            phrase_text="red",
            part_of_speech="adjective",
            grammatical_role="modifier",
            topic="adjectives attributive",
            note_text="An attributive adjective appears before the noun it modifies and forms part of the noun phrase.",
            origin_unit="functions of adjectives",
        ),
        _phrase_row(
            sentence="My car is red.",
            phrase_text="is red",
            part_of_speech="verb phrase",
            grammatical_role="predicate",
            topic="adjectives predicative",
            note_text="A predicative adjective follows a copular verb and ascribes a property to the subject of the clause.",
            origin_unit="functions of adjectives",
        ),
        _phrase_row(
            sentence="The rich are not like you and me: they have more money.",
            phrase_text="The rich",
            part_of_speech="noun phrase",
            grammatical_role="subject",
            topic="adjectives as nouns",
            note_text="The rich functions as a noun phrase referring collectively to wealthy people; the adjective takes on a nominal role with the definite article.",
            origin_unit="adjectives used as nouns",
        ),
        _phrase_row(
            sentence="Whoever your professor is, they will not appreciate you handing in essays late.",
            phrase_text="they",
            part_of_speech="pronoun",
            grammatical_role="subject",
            topic="singular they",
            note_text="They used as a singular pronoun avoids specifying the sex of the referent and is now accepted in formal written English.",
            origin_unit="singular they and gender-neutral reference",
        ),
        _phrase_row(
            sentence="The owl and the pussy cat are in the boat.",
            phrase_text="The owl and the pussy cat",
            part_of_speech="noun phrase",
            grammatical_role="subject",
            topic="coordinated subjects agreement",
            note_text="A coordinated noun phrase formed with and is typically plural and triggers plural verb agreement.",
            origin_unit="coordinated subjects and agreement",
        ),
        _phrase_row(
            sentence="What Dostoevsky is is a murder witness.",
            phrase_text="What Dostoevsky is",
            part_of_speech="noun clause",
            grammatical_role="subject",
            topic="what cleft subject clause",
            note_text="The what-clause in a double be construction acts as the subject of the main clause and is itself a kind of embedded question.",
            origin_unit="double be construction",
        ),
        _phrase_row(
            sentence="This is the girl that Peter gave her some cakes.",
            phrase_text="that Peter gave her some cakes",
            part_of_speech="relative clause",
            grammatical_role="modifier",
            topic="shadow pronouns resumptive",
            note_text="The relative clause contains a resumptive pronoun her that co-refers with the head noun the girl, filling what would otherwise be an empty position inside the clause.",
            origin_unit="shadow pronouns and island rescue",
        ),
        _phrase_row(
            sentence="I've ordered some biscuits, but none have arrived yet.",
            phrase_text="none have arrived",
            part_of_speech="verb phrase",
            grammatical_role="predicate",
            topic="none agreement count",
            note_text="Plural agreement with none is common when the noun in the context is countable; it treats the set of individual items rather than the whole as a unit.",
            origin_unit="none agreement patterns",
        ),
        _phrase_row(
            sentence="Michael is always taking cigarette breaks.",
            phrase_text="is always taking",
            part_of_speech="verb phrase",
            grammatical_role="predicate",
            topic="progressive habitual disapproval",
            note_text="The combination of progressive aspect with always conveys habitual behaviour and typically implies the speaker finds it annoying or excessive.",
            origin_unit="always with progressive for disapproval",
        ),
        _phrase_row(
            sentence="The woman I spoke to's ideas were stimulating.",
            phrase_text="The woman I spoke to's",
            part_of_speech="noun phrase",
            grammatical_role="possessive",
            topic="group genitive",
            note_text="The group genitive 's is attached to the final word of the whole noun phrase rather than just the head noun, which can produce unusual-sounding results with long phrases.",
            origin_unit="group genitive",
        ),
    ])

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
    parser = argparse.ArgumentParser(
        description="Build curated book-note rows from Mysteries of English Grammar (Calude & Bauer, 2022)."
    )
    parser.add_argument(
        "--output-jsonl",
        default="data/processed_book_notes_mysteries_v1/mysteries_book_note_rows_v1.jsonl",
    )
    parser.add_argument(
        "--report-json",
        default="data/processed_book_notes_mysteries_v1/mysteries_book_note_rows_v1.report.json",
    )
    args = parser.parse_args()

    rows = build_rows()
    report = {
        "document_id": DOCUMENT_ID,
        "source_path": SOURCE_PATH,
        "rows_total": len(rows),
        "sentence_rows": sum(1 for r in rows if (r.get("context") or {}).get("node_type") == "Sentence"),
        "phrase_rows": sum(1 for r in rows if (r.get("context") or {}).get("node_type") == "Phrase"),
        "topics": sorted(
            {
                str((r.get("source") or {}).get("topic"))
                for r in rows
                if str((r.get("source") or {}).get("topic")).strip()
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
