import tempfile
import textwrap
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_gutenberg_advanced_dataset import build_gutenberg_advanced_dataset


class BuildGutenbergAdvancedDatasetTests(unittest.TestCase):
    def test_build_gutenberg_advanced_dataset_creates_c1_c2_rows(self):
        sample = textwrap.dedent(
            """
            *** START OF THE PROJECT GUTENBERG EBOOK SAMPLE ***
            She should have left earlier. They will have finished by dawn. The results had improved already.
            *** END OF THE PROJECT GUTENBERG EBOOK SAMPLE ***
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_text(sample, encoding="utf-8")
            summary = build_gutenberg_advanced_dataset(
                text_paths=[str(path)],
                output_dir=str(Path(tmp) / "out"),
                metadata_by_path={str(path): {"gutenberg_id": "123", "title": "Sample"}},
                text_patterns=[r"\bshould have\b", r"\bwill have\b", r"\bhad\b"],
                min_examples_per_class=1,
            )

        self.assertGreaterEqual(summary["mapped_rows_before_gates"], 2)
        self.assertTrue(any(level in summary["mapped_cefr_counts"] for level in ("B2", "C1", "C2")))


if __name__ == "__main__":
    unittest.main()
