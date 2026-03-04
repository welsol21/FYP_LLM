import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.gutenberg_ingest import build_gutenberg_sentence_candidates, extract_gutenberg_body


class GutenbergIngestTests(unittest.TestCase):
    def test_extract_gutenberg_body_removes_header_and_footer(self):
        sample = textwrap.dedent(
            """
            Header line
            *** START OF THE PROJECT GUTENBERG EBOOK SAMPLE ***
            This is the first sentence.
            This is the second sentence.
            *** END OF THE PROJECT GUTENBERG EBOOK SAMPLE ***
            Footer line
            """
        )
        body = extract_gutenberg_body(sample)
        self.assertIn("This is the first sentence.", body)
        self.assertNotIn("Header line", body)
        self.assertNotIn("Footer line", body)

    def test_build_gutenberg_sentence_candidates_filters_by_pattern(self):
        sample = textwrap.dedent(
            """
            *** START OF THE PROJECT GUTENBERG EBOOK SAMPLE ***
            She should have left earlier. The room was silent. They will have finished by dawn.
            *** END OF THE PROJECT GUTENBERG EBOOK SAMPLE ***
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_text(sample, encoding="utf-8")
            rows = build_gutenberg_sentence_candidates(
                text_path=str(path),
                metadata={"gutenberg_id": "123", "title": "Sample"},
                text_patterns=[r"\bshould have\b", r"\bwill have\b"],
            )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["provenance"]["source"], "ProjectGutenberg")
        self.assertEqual(rows[0]["provenance"]["gutenberg_id"], "123")


if __name__ == "__main__":
    unittest.main()
