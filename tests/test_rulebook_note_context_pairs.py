import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.dataset.build_rulebook_note_context_pairs import build_rulebook_note_context_pairs


class RulebookNoteContextPairTests(unittest.TestCase):
    def test_build_rulebook_note_context_pairs_extracts_explicit_and_line_block_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "Abbreviated sentences of a more predictable kind are a frequent feature of informal writing.",
                        "Here the subject and part of the verb are often omitted.",
                        "Having a wonderful time here",
                        "See you soon",
                        "",
                        "This symbol indicates an impossible structure.",
                        "Example: *They likes to read.",
                    ]
                ),
                encoding="utf-8",
            )
            rows_path = Path(tmp) / "rows.jsonl"
            rows = [
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "dictionary_entry",
                    "heading": "abbreviated",
                    "entry_head": "abbreviated",
                    "line_start": 1,
                    "line_end": 4,
                },
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "notational_rule",
                    "heading": "Notational Conventions",
                    "entry_head": "",
                    "line_start": 6,
                    "line_end": 7,
                },
            ]
            with rows_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            pairs, report = build_rulebook_note_context_pairs(
                rulebook_jsonl=str(rows_path),
                payload_txt=str(payload_path),
            )

        self.assertGreaterEqual(report["pairs_total"], 1)
        self.assertTrue(any("Having a wonderful time here" in row["context_text"] for row in pairs))
        self.assertTrue(any(row["pair_method"] == "line_block" for row in pairs))

    def test_build_rulebook_note_context_pairs_strips_entry_head_and_ignores_meta_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "Organization",
                        "Entries are alphabetical.",
                        "",
                        "prepositional phrase A prepositional phrase can indicate location.",
                        "in the garden",
                        "with no name",
                    ]
                ),
                encoding="utf-8",
            )
            rows_path = Path(tmp) / "rows.jsonl"
            rows = [
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "organization_rule",
                    "heading": "Organization",
                    "entry_head": "",
                    "line_start": 1,
                    "line_end": 2,
                },
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "dictionary_entry",
                    "heading": "prepositional phrase",
                    "entry_head": "prepositional phrase",
                    "line_start": 4,
                    "line_end": 6,
                },
            ]
            with rows_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            pairs, report = build_rulebook_note_context_pairs(
                rulebook_jsonl=str(rows_path),
                payload_txt=str(payload_path),
            )

        self.assertGreaterEqual(report["pairs_total"], 1)
        self.assertTrue(all(row["entry_head"] == "prepositional phrase" for row in pairs))
        self.assertTrue(any(row["notation_text"].startswith("A prepositional phrase") for row in pairs))

    def test_build_rulebook_note_context_pairs_source_first_handles_front_matter_and_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "Organization",
                        "Entries are strictly alphabetical. Cross-references are signalled by an asterisk.",
                        "See agreement.",
                        "",
                        "ability",
                        "One of the semantic categories used in the classification of modal verbs.",
                        "They can swim.",
                    ]
                ),
                encoding="utf-8",
            )
            rows_path = Path(tmp) / "rows.jsonl"
            rows = [
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "organization_rule",
                    "heading": "Organization",
                    "entry_head": "",
                    "line_start": 1,
                    "line_end": 3,
                },
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "dictionary_entry",
                    "heading": "ability",
                    "entry_head": "ability",
                    "line_start": 5,
                    "line_end": 7,
                },
            ]
            with rows_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            pairs, report = build_rulebook_note_context_pairs(
                rulebook_jsonl=str(rows_path),
                payload_txt=str(payload_path),
                source_first=True,
            )

        self.assertGreaterEqual(report["pairs_total"], 1)
        self.assertTrue(any(row["pair_method"] == "rulebook_source_first" for row in pairs))
        self.assertTrue(any("modal verbs" in row["notation_text"] for row in pairs))

    def test_build_rulebook_note_context_pairs_source_first_drops_crossref_and_fragment_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "prepositional phrase",
                        "A prepositional phrase can indicate location in a clause.",
                        "sometimes deviates from standard rules.",
                        "See gradable.",
                        "with no name",
                        "in the garden",
                    ]
                ),
                encoding="utf-8",
            )
            rows_path = Path(tmp) / "rows.jsonl"
            rows = [
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "dictionary_entry",
                    "heading": "prepositional phrase",
                    "entry_head": "prepositional phrase",
                    "line_start": 1,
                    "line_end": 6,
                }
            ]
            with rows_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            pairs, report = build_rulebook_note_context_pairs(
                rulebook_jsonl=str(rows_path),
                payload_txt=str(payload_path),
                source_first=True,
            )

        self.assertGreaterEqual(report["pairs_total"], 1)
        contexts = {row["context_text"] for row in pairs}
        self.assertIn("with no name", contexts)
        self.assertIn("in the garden", contexts)
        self.assertNotIn("sometimes deviates from standard rules.", contexts)
        self.assertNotIn("See gradable.", contexts)

    def test_build_rulebook_note_context_pairs_source_first_prefers_explicit_example_zone(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "A/AN",
                        "These are the two forms of the indefinite article, as underlined in: We saw a man riding a unicycle through the forest. Let’s make it an evening at the opera in Sydney. As in those examples, the indefinite article does not undertake to define the referent for the context.",
                    ]
                ),
                encoding="utf-8",
            )
            rows_path = Path(tmp) / "rows.jsonl"
            rows = [
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "dictionary_entry",
                    "heading": "A/AN",
                    "entry_head": "A/AN",
                    "line_start": 1,
                    "line_end": 2,
                    "text": "These are the two forms of the indefinite article, as underlined in: We saw a man riding a unicycle through the forest. Let’s make it an evening at the opera in Sydney. As in those examples, the indefinite article does not undertake to define the referent for the context.",
                }
            ]
            with rows_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            pairs, report = build_rulebook_note_context_pairs(
                rulebook_jsonl=str(rows_path),
                payload_txt=str(payload_path),
                source_first=True,
            )

        self.assertGreaterEqual(report["pairs_total"], 2)
        contexts = {row["context_text"] for row in pairs}
        self.assertIn("We saw a man riding a unicycle through the forest.", contexts)
        self.assertIn("Let’s make it an evening at the opera in Sydney.", contexts)
        self.assertFalse(any("referent for the context" in item for item in contexts))

    def test_build_rulebook_note_context_pairs_source_first_strips_meta_labels_and_trailing_explanations(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "acceptability",
                        "The quality of being judged by native speakers as normal or possible.",
                        "Examples: QUIRK Characters in Dickens can use an’t or ain’t for ‘isn’t’ without any hint that such forms are other than fully acceptable. e.g. I refusing to go, Nicholas went alone), so absolute clauses are sometimes called nominative absolutes.",
                    ]
                ),
                encoding="utf-8",
            )
            rows_path = Path(tmp) / "rows.jsonl"
            rows = [
                {
                    "source_path": "/tmp/book.pdf",
                    "row_type": "dictionary_entry",
                    "heading": "acceptability",
                    "entry_head": "acceptability",
                    "line_start": 1,
                    "line_end": 3,
                    "text": "The quality of being judged by native speakers as normal or possible. Examples: QUIRK Characters in Dickens can use an’t or ain’t for ‘isn’t’ without any hint that such forms are other than fully acceptable. e.g. I refusing to go, Nicholas went alone), so absolute clauses are sometimes called nominative absolutes.",
                }
            ]
            with rows_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            pairs, _report = build_rulebook_note_context_pairs(
                rulebook_jsonl=str(rows_path),
                payload_txt=str(payload_path),
                source_first=True,
            )

        contexts = {row["context_text"] for row in pairs}
        self.assertIn("I refusing to go, Nicholas went alone", contexts)
        self.assertFalse(any("Characters in Dickens" in item for item in contexts))
        self.assertFalse(any("any hint that" in item for item in contexts))
        self.assertFalse(any(item == "I refusing to go, Nicholas went" for item in contexts))


if __name__ == "__main__":
    unittest.main()
