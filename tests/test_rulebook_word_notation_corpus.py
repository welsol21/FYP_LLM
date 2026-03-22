import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.dataset.build_rulebook_word_notation_corpus import build_rulebook_word_notation_rows


class RulebookWordNotationCorpusTests(unittest.TestCase):
    def test_build_rulebook_word_notation_rows_emits_preposition_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "preposition",
                        "A preposition is a word used before a noun phrase to link it to another word in the clause.",
                        "For example: in the garden. with no name.",
                    ]
                ),
                encoding="utf-8",
            )
            rows_path = Path(tmp) / "rows.jsonl"
            with rows_path.open("w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "source_path": "/tmp/book.pdf",
                            "row_type": "dictionary_entry",
                            "heading": "preposition",
                            "entry_head": "preposition",
                            "text": "A preposition is a word used before a noun phrase to link it to another word in the clause. For example: in the garden. with no name.",
                            "line_start": 1,
                            "line_end": 3,
                        }
                    )
                    + "\n"
                )

            rows, report = build_rulebook_word_notation_rows(
                rulebook_jsonl=str(rows_path),
                payload_txt=str(payload_path),
            )

        self.assertGreaterEqual(report["stats"]["rows_emitted"], 1)
        self.assertTrue(any(row["template_id"] == "WORD_PREPOSITION" for row in rows))
        self.assertTrue(any("preposition is a word" in row["book_notation_text"].lower() for row in rows))

    def test_build_rulebook_word_notation_rows_rejects_meta_and_crossref_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.txt"
            payload_path.write_text(
                "\n".join(
                    [
                        "common noun",
                        "A common noun names a class of entities.",
                        "For example: See further under noun, section 2.",
                        "For example: The dog barked loudly.",
                    ]
                ),
                encoding="utf-8",
            )
            rows_path = Path(tmp) / "rows.jsonl"
            with rows_path.open("w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "source_path": "/tmp/book.pdf",
                            "row_type": "dictionary_entry",
                            "heading": "common noun",
                            "entry_head": "common noun",
                            "text": "A common noun names a class of entities. For example: See further under noun, section 2. For example: The dog barked loudly.",
                            "line_start": 1,
                            "line_end": 4,
                        }
                    )
                    + "\n"
                )

            rows, report = build_rulebook_word_notation_rows(
                rulebook_jsonl=str(rows_path),
                payload_txt=str(payload_path),
            )

        self.assertGreaterEqual(report["stats"]["rows_emitted"], 1)
        self.assertTrue(any(row["word_text"].lower() == "dog" for row in rows))
        self.assertFalse(any("see further under" in row["context_text"].lower() for row in rows))


if __name__ == "__main__":
    unittest.main()
