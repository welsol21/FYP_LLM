import tempfile
import unittest
import zipfile
from pathlib import Path

from ela_pipeline.classifier.oanc_inspect import (
    OANC_ADVANCED_GENRE_MARKERS,
    extract_oanc_text,
    find_oanc_candidate_files_by_patterns,
    list_oanc_candidate_files,
    summarize_oanc_zip,
)


class OANCInspectTests(unittest.TestCase):
    def test_summarize_oanc_zip_and_list_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "oanc.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr("OANC/data/written_1/journal/slate/1/doc1.txt", "Advanced journal text.")
                z.writestr("OANC/data/written_2/technical/manuals/doc2.txt", "Technical text.")
                z.writestr("OANC/data/spoken/telephone/doc3.txt", "Spoken text.")
                z.writestr("OANC/data/written_2/technical/manuals/doc2.anc", "<anc/>")

            summary = summarize_oanc_zip(str(zip_path))
            candidates = list_oanc_candidate_files(str(zip_path))

        self.assertGreaterEqual(summary["txt_files"], 3)
        self.assertIn("written_1/journal", summary["top_genre_buckets"])
        self.assertIn("written_2/technical", summary["top_genre_buckets"])
        self.assertEqual(len(candidates), 2)
        self.assertTrue(any("journal" in p for p in candidates))
        self.assertTrue(any("technical" in p for p in candidates))

    def test_extract_oanc_text_reads_txt_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "oanc.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr("OANC/data/written_1/journal/slate/1/doc1.txt", "Line one.\nLine two.")

            text = extract_oanc_text(str(zip_path), "OANC/data/written_1/journal/slate/1/doc1.txt")

        self.assertIn("Line one.", text)
        self.assertIn("Line two.", text)
        self.assertTrue(any(marker in "OANC/data/written_1/journal/slate/1/doc1.txt" for marker in OANC_ADVANCED_GENRE_MARKERS))

    def test_find_oanc_candidate_files_by_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "oanc.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr(
                    "OANC/data/written_2/technical/manuals/doc1.txt",
                    "The archive will have been migrated by the end of the quarter.",
                )
                z.writestr(
                    "OANC/data/written_2/technical/manuals/doc2.txt",
                    "The system had completed the calibration before the test started.",
                )
                z.writestr(
                    "OANC/data/written_1/journal/slate/1/doc3.txt",
                    "A neutral sentence without advanced pattern.",
                )

            result = find_oanc_candidate_files_by_patterns(
                str(zip_path),
                {
                    "future_perfect": r"\bwill\s+have\s+\w+",
                    "past_perfect": r"\bhad\s+\w+",
                },
                member_paths=["OANC/data/written_2/technical/manuals/doc1.txt"],
            )

        self.assertIn("future_perfect", result)
        self.assertIn("past_perfect", result)
        self.assertEqual(len(result["future_perfect"]), 1)
        self.assertEqual(len(result["past_perfect"]), 0)


if __name__ == "__main__":
    unittest.main()
