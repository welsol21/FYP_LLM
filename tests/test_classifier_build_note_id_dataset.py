import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.build_note_id_classifier_dataset import build_note_id_classifier_dataset


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class BuildNoteIdClassifierDatasetTests(unittest.TestCase):
    def test_build_note_id_dataset_merges_template_and_raw_splits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            template_dir = tmp / "template"
            raw_dir = tmp / "raw"
            out_dir = tmp / "out"

            _write_jsonl(template_dir / "train.jsonl", [{"input": "i1", "target": "Use {{MODAL}} to indicate possibility."}])
            _write_jsonl(template_dir / "dev.jsonl", [{"input": "i2", "target": "Use {{MODAL}} to indicate possibility."}])
            _write_jsonl(template_dir / "test.jsonl", [{"input": "i3", "target": "A {{SUBJECT}} template note."}])

            _write_jsonl(raw_dir / "train.jsonl", [{"input": "i4", "target": "Don't have to indicates lack of necessity."}])
            _write_jsonl(raw_dir / "dev.jsonl", [{"input": "i5", "target": "Impersonal passive avoids naming the agent."}])
            _write_jsonl(raw_dir / "test.jsonl", [{"input": "i6", "target": "Impersonal passive avoids naming the agent."}])

            summary = build_note_id_classifier_dataset(
                template_dataset_dir=str(template_dir),
                raw_dataset_dir=str(raw_dir),
                output_dir=str(out_dir),
            )

            self.assertEqual(summary["unique_note_ids"], 4)
            self.assertEqual(summary["all_samples"], 6)
            self.assertGreaterEqual(summary["train_samples"], 2)
            self.assertLessEqual(summary["dev_samples"], 2)
            self.assertLessEqual(summary["test_samples"], 2)
            self.assertEqual(
                summary["train_samples"] + summary["dev_samples"] + summary["test_samples"],
                6,
            )
            inventory = json.loads((out_dir / "note_id_inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(len(inventory), 4)
            train_rows = [json.loads(line) for line in (out_dir / "train.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(train_rows[0]["source_text"], train_rows[0]["input"])
            self.assertIn(train_rows[0]["note_type"], {"template", "raw"})


if __name__ == "__main__":
    unittest.main()
