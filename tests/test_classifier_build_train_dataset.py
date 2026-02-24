import json
import tempfile
import unittest

from ela_pipeline.classifier.build_kb import build_kb_artifacts
from ela_pipeline.classifier.build_train_dataset import build_train_dev_from_enriched_kb


class ClassifierBuildTrainDatasetTests(unittest.TestCase):
    def test_build_train_dev_from_enriched_kb(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = build_kb_artifacts(output_dir=f"{tmp}/kb", spacy_model="en_core_web_sm")
            out = build_train_dev_from_enriched_kb(
                input_path=kb["kb_spacy_enriched"],
                output_dir=f"{tmp}/ds",
                dev_ratio=0.34,
                seed=123,
            )
            for key in ("train", "dev", "stats"):
                self.assertIn(key, out)

            with open(out["train"], "r", encoding="utf-8") as f:
                train_rows = [json.loads(line) for line in f if line.strip()]
            with open(out["dev"], "r", encoding="utf-8") as f:
                dev_rows = [json.loads(line) for line in f if line.strip()]
            with open(out["stats"], "r", encoding="utf-8") as f:
                stats = json.load(f)

            self.assertGreater(len(train_rows), 0)
            self.assertGreater(len(dev_rows), 0)
            self.assertEqual(stats["train"], len(train_rows))
            self.assertEqual(stats["dev"], len(dev_rows))
            self.assertTrue(all("task: classify_cefr_and_grammar" in row["input"] for row in train_rows))


if __name__ == "__main__":
    unittest.main()
