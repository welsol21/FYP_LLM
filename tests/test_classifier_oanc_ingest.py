import tempfile
import unittest
import zipfile
from pathlib import Path

from ela_pipeline.classifier.oanc_ingest import (
    build_oanc_candidate_manifest,
    build_oanc_sentence_candidates,
    extract_oanc_annotated_sentences,
    split_oanc_text_to_sentences,
)


class OANCIngestTests(unittest.TestCase):
    def test_split_oanc_text_to_sentences_filters_short_noise(self):
        text = (
            "This is a valid advanced sentence. "
            "Too short. "
            "Another sentence with enough structure to pass filtering. "
            "Dr. Smith wrote the report."
        )

        parts = split_oanc_text_to_sentences(text, min_chars=20)

        self.assertIn("This is a valid advanced sentence.", parts)
        self.assertIn("Another sentence with enough structure to pass filtering.", parts)
        self.assertIn("Dr. Smith wrote the report.", parts)
        self.assertNotIn("Too short.", parts)

    def test_split_oanc_text_to_sentences_drops_short_title_paragraph(self):
        text = "Harmonic Convergences\nYou're right, Maxim's strong point is that it's totally unsentimental and ungenteel."

        parts = split_oanc_text_to_sentences(text, min_chars=20)

        self.assertEqual(
            parts,
            ["You're right, Maxim's strong point is that it's totally unsentimental and ungenteel."],
        )

    def test_build_oanc_sentence_candidates_reads_zip_and_attaches_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "oanc.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr(
                    "OANC/data/written_1/journal/slate/1/doc1.txt",
                    "This is a valid advanced sentence. Another advanced sentence appears here.",
                )
                z.writestr(
                    "OANC/data/written_2/technical/manuals/doc2.txt",
                    "The system shall remain operational during maintenance windows.",
                )
                z.writestr(
                    "OANC/data/spoken/telephone/doc3.txt",
                    "Hello there.",
                )

            rows = build_oanc_sentence_candidates(str(zip_path), limit_files=10, min_chars=20)

        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(all("text" in row for row in rows))
        self.assertTrue(all("provenance" in row for row in rows))
        self.assertTrue(all(row["provenance"]["source"] == "OANC" for row in rows))
        self.assertTrue(any(row["provenance"]["genre_bucket"] == "written_1/journal" for row in rows))
        self.assertTrue(any(row["provenance"]["genre_bucket"] == "written_2/technical" for row in rows))
        self.assertTrue(all("spoken/telephone" not in row["provenance"]["member_path"] for row in rows))
        journal_rows = [row for row in rows if row["provenance"]["genre_bucket"] == "written_1/journal"]
        technical_rows = [row for row in rows if row["provenance"]["genre_bucket"] == "written_2/technical"]
        self.assertTrue(all(row["provenance"]["sentence_boundary_source"] == "spacy_parser" for row in journal_rows + technical_rows))
        self.assertTrue(all(row["provenance"]["sentence_splitter_model"] == "en_core_web_sm" for row in journal_rows + technical_rows))

    def test_build_oanc_candidate_manifest_limits_per_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "oanc.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                for idx in range(3):
                    z.writestr(f"OANC/data/written_1/journal/slate/1/doc{idx}.txt", f"Journal {idx}.")
                for idx in range(3):
                    z.writestr(f"OANC/data/written_2/technical/manuals/tech{idx}.txt", f"Tech {idx}.")

            manifest = build_oanc_candidate_manifest(str(zip_path), per_bucket_limit=2)

        self.assertEqual(manifest["selected_files"], 4)
        self.assertEqual(manifest["bucket_counts"]["written_1/journal"], 2)
        self.assertEqual(manifest["bucket_counts"]["written_2/technical"], 2)

    def test_extract_oanc_annotated_sentences_prefers_s_xml_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "oanc.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                txt = "Title\nThis is the first proper sentence. This is the second proper sentence."
                z.writestr("OANC/data/written_2/technical/manuals/doc1.txt", txt)
                z.writestr(
                    "OANC/data/written_2/technical/manuals/doc1-s.xml",
                    (
                        "<?xml version='1.0' encoding='UTF-8'?>"
                        "<cesAna xmlns='http://www.xces.org/schema/2003' version='1.0.4'>"
                        "<struct type='s' from='6' to='40'><feat name='id' value='s1'/></struct>"
                        "<struct type='s' from='41' to='76'><feat name='id' value='s2'/></struct>"
                        "</cesAna>"
                    ),
                )

            rows = extract_oanc_annotated_sentences(
                str(zip_path),
                "OANC/data/written_2/technical/manuals/doc1.txt",
                min_chars=10,
            )

        self.assertEqual(
            rows,
            [
                {
                    "text": "This is the first proper sentence.",
                    "annotation_id": "s1",
                },
                {
                    "text": "This is the second proper sentence.",
                    "annotation_id": "s2",
                },
            ],
        )

    def test_build_oanc_sentence_candidates_uses_oanc_sentence_annotations_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "oanc.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                txt = "Title\nThis is the first proper sentence. This is the second proper sentence."
                z.writestr("OANC/data/written_2/technical/manuals/doc1.txt", txt)
                z.writestr(
                    "OANC/data/written_2/technical/manuals/doc1-s.xml",
                    (
                        "<?xml version='1.0' encoding='UTF-8'?>"
                        "<cesAna xmlns='http://www.xces.org/schema/2003' version='1.0.4'>"
                        "<struct type='s' from='6' to='40'><feat name='id' value='s1'/></struct>"
                        "<struct type='s' from='41' to='76'><feat name='id' value='s2'/></struct>"
                        "</cesAna>"
                    ),
                )

            rows = build_oanc_sentence_candidates(str(zip_path), limit_files=10, min_chars=10)

        self.assertEqual(rows[0]["provenance"]["sentence_boundary_source"], "oanc_s_xml")
        self.assertEqual(rows[0]["provenance"]["sentence_annotation_id"], "s1")


if __name__ == "__main__":
    unittest.main()
