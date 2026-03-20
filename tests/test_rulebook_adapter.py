import unittest

from ela_pipeline.dataset.book_extraction.engine import BookTextPayload
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


if __name__ == "__main__":
    unittest.main()
