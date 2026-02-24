import json
import tempfile
import unittest

from ela_pipeline.classifier.build_kb import build_kb_artifacts


class ClassifierBuildKBTests(unittest.TestCase):
    def test_build_kb_artifacts_writes_raw_and_enriched_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = build_kb_artifacts(output_dir=tmp, spacy_model="en_core_web_sm")
            self.assertIn("kb_raw", artifacts)
            self.assertIn("kb_spacy_enriched", artifacts)

            with open(artifacts["kb_raw"], "r", encoding="utf-8") as f:
                raw_lines = [json.loads(line) for line in f if line.strip()]
            with open(artifacts["kb_spacy_enriched"], "r", encoding="utf-8") as f:
                enr_lines = [json.loads(line) for line in f if line.strip()]

            self.assertGreaterEqual(len(raw_lines), 6)
            self.assertEqual(len(raw_lines), len(enr_lines))
            self.assertIn("spacy", enr_lines[0])
            self.assertIn("tokens", enr_lines[0]["spacy"])


if __name__ == "__main__":
    unittest.main()
