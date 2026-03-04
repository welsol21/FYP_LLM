import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ela_pipeline.classifier.build_oanc_advanced_dataset import build_oanc_advanced_dataset


class BuildOANCAdvancedDatasetTests(unittest.TestCase):
    def test_build_oanc_advanced_dataset_creates_train_ready_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "oanc.zip"
            output_dir = Path(tmp) / "out"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr(
                    "OANC/data/written_2/technical/manuals/doc1.txt",
                    (
                        "Title\n"
                        "By the time the process started, the system had completed the prior calibration.\n"
                        "The valve should have been replaced before the final pressure test.\n"
                        "The archive will have been migrated by the end of the quarter.\n"
                    ),
                )
                z.writestr(
                    "OANC/data/written_2/technical/manuals/doc1-s.xml",
                    (
                        "<?xml version='1.0' encoding='UTF-8'?>"
                        "<cesAna xmlns='http://www.xces.org/schema/2003' version='1.0.4'>"
                        "<struct type='s' from='6' to='85'><feat name='id' value='s1'/></struct>"
                        "<struct type='s' from='86' to='153'><feat name='id' value='s2'/></struct>"
                        "<struct type='s' from='154' to='221'><feat name='id' value='s3'/></struct>"
                        "</cesAna>"
                    ),
                )

            summary = build_oanc_advanced_dataset(
                zip_path=str(zip_path),
                output_dir=str(output_dir),
                member_paths=["OANC/data/written_2/technical/manuals/doc1.txt"],
                per_bucket_limit=5,
                total_limit=5,
                min_examples_per_class=1,
            )

            dataset_path = Path(summary["dataset_path"])
            rows = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertTrue(summary["gate_report"]["passed"])
        self.assertEqual(summary["accepted_rows"], 3)
        self.assertEqual({row["cefr_label"] for row in rows}, {"B2", "C1", "C2"})
        self.assertTrue(any("past_perfect" in row["grammar_classes"] for row in rows))
        self.assertTrue(any("modal_perfect" in row["grammar_classes"] for row in rows))
        self.assertTrue(any("future_perfect" in row["grammar_classes"] for row in rows))


if __name__ == "__main__":
    unittest.main()
