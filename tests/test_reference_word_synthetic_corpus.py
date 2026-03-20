import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.dataset.book_extraction.engine import BookSnippet
from ela_pipeline.dataset.build_reference_word_synthetic_corpus import build_reference_word_rows


class ReferenceWordSyntheticCorpusTests(unittest.TestCase):
    @patch("ela_pipeline.dataset.build_reference_word_synthetic_corpus.UniversalBookExtractionEngine.extract_from_path")
    def test_build_reference_word_rows_emits_preposition_word_rows(self, mock_extract):
        mock_extract.return_value = [
            BookSnippet(
                source_path="/tmp/Dictionary of Grammar.pdf",
                parser_name="pdf",
                format="pdf",
                topic_key="word_preposition",
                anchor="preposition",
                heading="Preposition",
                snippet_text='A preposition links a following complement to another element. For example: "Tom went through the tunnel."',
                start_line=1,
                end_line=3,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ref_dir = Path(tmp) / "refs"
            ref_dir.mkdir()
            (ref_dir / "Dictionary of Grammar.pdf").write_text("fake", encoding="utf-8")
            rows, report = build_reference_word_rows(
                input_path=str(ref_dir),
                cache_dir=str(Path(tmp) / "cache"),
            )

        self.assertGreaterEqual(report["rows_emitted"], 1)
        self.assertTrue(any(row["template_id"] == "WORD_PREPOSITION" for row in rows))
        self.assertTrue(any(row["word_text"].lower() == "through" for row in rows))

    @patch("ela_pipeline.dataset.build_reference_word_synthetic_corpus.UniversalBookExtractionEngine.extract_from_path")
    def test_build_reference_word_rows_keeps_common_noun_not_determiner(self, mock_extract):
        mock_extract.return_value = [
            BookSnippet(
                source_path="/tmp/Dictionary of Grammar.pdf",
                parser_name="pdf",
                format="pdf",
                topic_key="word_common_noun",
                anchor="common noun",
                heading="Common noun",
                snippet_text='A common noun names a class of entities. For example: "The dog barked loudly."',
                start_line=1,
                end_line=3,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ref_dir = Path(tmp) / "refs"
            ref_dir.mkdir()
            (ref_dir / "Dictionary of Grammar.pdf").write_text("fake", encoding="utf-8")
            rows, report = build_reference_word_rows(
                input_path=str(ref_dir),
                cache_dir=str(Path(tmp) / "cache"),
            )

        self.assertGreaterEqual(report["rows_emitted"], 1)
        self.assertTrue(any(row["word_text"].lower() == "dog" for row in rows))
        self.assertFalse(any(row["word_text"].lower() == "the" for row in rows))

    @patch("ela_pipeline.dataset.build_reference_word_synthetic_corpus.UniversalBookExtractionEngine.extract_from_path")
    def test_build_reference_word_rows_rejects_meta_reference_fragment(self, mock_extract):
        mock_extract.return_value = [
            BookSnippet(
                source_path="/tmp/Dictionary of Grammar.pdf",
                parser_name="pdf",
                format="pdf",
                topic_key="word_participle",
                anchor="participle",
                heading="Participle",
                snippet_text="A participle is a verb form. For example: See also absolute (4).",
                start_line=1,
                end_line=3,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ref_dir = Path(tmp) / "refs"
            ref_dir.mkdir()
            (ref_dir / "Dictionary of Grammar.pdf").write_text("fake", encoding="utf-8")
            rows, report = build_reference_word_rows(
                input_path=str(ref_dir),
                cache_dir=str(Path(tmp) / "cache"),
            )

        self.assertEqual(rows, [])
        self.assertEqual(report["rows_emitted"], 0)


if __name__ == "__main__":
    unittest.main()
