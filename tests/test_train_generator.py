import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.training.train_generator import load_jsonl, mix_with_feedback_rows, save_json


class TrainGeneratorTests(unittest.TestCase):
    def test_load_jsonl_reads_non_empty_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.jsonl"
            path.write_text(
                '{"input":"a","target":"b"}\n\n{"input":"c","target":"d"}\n',
                encoding="utf-8",
            )
            rows = load_jsonl(str(path))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["input"], "a")
            self.assertEqual(rows[1]["target"], "d")

    def test_save_json_writes_sorted_pretty_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.json"
            save_json(str(path), {"b": 2, "a": 1})
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, {"a": 1, "b": 2})

    def test_mix_with_feedback_rows_applies_weight(self):
        base = [{"input": "a", "target": "x"}]
        feedback = [{"input": "b", "target": "y"}]
        mixed = mix_with_feedback_rows(base, feedback, feedback_weight=2)
        self.assertEqual(len(mixed), 3)
        self.assertEqual(mixed[0]["input"], "a")
        self.assertEqual(mixed[1]["input"], "b")
        self.assertEqual(mixed[2]["input"], "b")


if __name__ == "__main__":
    unittest.main()
