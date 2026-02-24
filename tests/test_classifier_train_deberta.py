import json
import tempfile
import unittest

from ela_pipeline.classifier.train_deberta_classifier import _load_jsonl, train_deberta_classifier


class ClassifierTrainDebertaTests(unittest.TestCase):
    def test_load_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/rows.jsonl"
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps({"a": 1}) + "\n")
                f.write(json.dumps({"b": 2}) + "\n")
            rows = _load_jsonl(path)
            self.assertEqual(len(rows), 2)

    def test_gpu_only_policy_rejects_non_cuda(self):
        with tempfile.TemporaryDirectory() as tmp:
            train = f"{tmp}/train.jsonl"
            dev = f"{tmp}/dev.jsonl"
            row = {"input": "task: classify", "cefr_label": "B1", "class_id": "x", "band": "Intermediate"}
            with open(train, "w", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            with open(dev, "w", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            with self.assertRaises(RuntimeError):
                train_deberta_classifier(
                    train_path=train,
                    dev_path=dev,
                    output_dir=f"{tmp}/out",
                    device="cpu",
                )


if __name__ == "__main__":
    unittest.main()
