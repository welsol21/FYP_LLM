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


if __name__ == "__main__":
    unittest.main()
