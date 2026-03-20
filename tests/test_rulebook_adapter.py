import unittest

from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
from ela_pipeline.dataset.book_extraction.cambridge_dictionary_adapter import extract_cambridge_dictionary_rows
from ela_pipeline.dataset.book_extraction.leech_glossary_adapter import extract_leech_glossary_rows
from ela_pipeline.dataset.book_extraction.oxford_dictionary_adapter import extract_oxford_dictionary_rows


class RulebookAdapterTests(unittest.TestCase):
    def test_extract_oxford_dictionary_rows_reads_front_matter_and_entries(self):
        payload = BookTextPayload(
            source_path="/tmp/The Oxford Dictionary of English Grammar.pdf",
            parser_name="pdf",
            format="pdf",
            text="""
Organization
1. Entries are alphabetical.
2. Cross-references are marked with an asterisk, e.g. aspect.

Notational Conventions
* indicates an impossible structure. Example: *They likes to read.

Abbreviations
P/PP preposition/prepositional phrase
S sentence

A
A *Adverbial as an element of clause structure.
Compare c; s; o; v.
See also adjunct.

abbreviated
Shortened or contracted so that a part stands for the whole.
For example, labels often omit the subject.
""",
        )

        rows = extract_oxford_dictionary_rows(payload)
        row_types = [row.row_type for row in rows]

        self.assertIn("organization_rule", row_types)
        self.assertIn("notational_rule", row_types)
        self.assertIn("abbreviation_rule", row_types)
        self.assertIn("dictionary_entry", row_types)
        self.assertTrue(any(row.entry_head == "abbreviated" for row in rows if row.row_type == "dictionary_entry"))
        self.assertTrue(any(row.example_marker_count > 0 for row in rows))

    def test_extract_oxford_dictionary_rows_skips_letter_headers_and_keeps_real_headwords(self):
        payload = BookTextPayload(
            source_path="/tmp/The Oxford Dictionary of English Grammar.pdf",
            parser_name="pdf",
            format="pdf",
            text="""
Organization
Entries are alphabetical.

Notational Conventions
* marks impossible structure.

Abbreviations
PP prepositional phrase

A
abbreviation

a

2

abbreviation A shortened form of a word or phrase.
BBC
UK

principal parts Chieﬂy used in the description of Latin.
blow, blew, blown
""",
        )

        rows = [row for row in extract_oxford_dictionary_rows(payload) if row.row_type == "dictionary_entry"]
        heads = [row.entry_head for row in rows]

        self.assertIn("abbreviation", heads)
        self.assertIn("principal parts", heads)
        self.assertNotIn("a", heads)
        self.assertFalse(any(row.entry_head == "abbreviation" and row.text.startswith("a ") for row in rows))

    def test_extract_leech_glossary_rows_reads_symbols_intro_and_entries(self):
        payload = BookTextPayload(
            source_path="/tmp/A Glossary of English Grammar.pdf",
            parser_name="pdf",
            format="pdf",
            text="""
Use of special symbols
* indicates an unacceptable example.
[ ] marks the boundary of a clause.

Introduction
This glossary focuses on descriptive grammar and relies on illustrations.

A
abstract noun A noun which refers to an abstraction rather than a concrete thing.
Hope is an abstract noun.

active, active voice The term applied to a verb phrase which is not passive.
See passive; voice.
""",
        )

        rows = extract_leech_glossary_rows(payload)
        row_types = [row.row_type for row in rows]

        self.assertIn("notational_rule", row_types)
        self.assertIn("introduction_rule", row_types)
        self.assertIn("dictionary_entry", row_types)
        self.assertTrue(any(row.entry_head == "abstract noun" for row in rows if row.row_type == "dictionary_entry"))
        self.assertTrue(any(row.entry_head == "active, active voice" for row in rows if row.row_type == "dictionary_entry"))

    def test_extract_cambridge_dictionary_rows_reads_usage_intro_and_entries(self):
        payload = BookTextPayload(
            source_path="/tmp/The Cambridge Dictionary of English Grammar.pdf",
            parser_name="pdf",
            format="pdf",
            text="""
How to use this book
Lookup terms alphabetically and follow cross-references.

Introduction
This dictionary explains current grammatical terms and concepts.

A
A/AN The indefinite article in traditional grammar and a determiner in modern grammar.

abbreviated clause A reduced clause with omitted material.
When in doubt, ask.
""",
        )

        rows = extract_cambridge_dictionary_rows(payload)
        row_types = [row.row_type for row in rows]

        self.assertIn("usage_rule", row_types)
        self.assertIn("introduction_rule", row_types)
        self.assertIn("dictionary_entry", row_types)
        self.assertTrue(any(row.entry_head == "A/AN" for row in rows if row.row_type == "dictionary_entry"))
        self.assertTrue(any(row.entry_head == "abbreviated clause" for row in rows if row.row_type == "dictionary_entry"))


if __name__ == "__main__":
    unittest.main()
