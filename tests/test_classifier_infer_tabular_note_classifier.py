import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.infer_tabular_note_classifier import load_label_order, load_note_inventory


class InferTabularNoteClassifierTests(unittest.TestCase):
    def test_load_helpers_parse_summary_and_inventory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            summary_path = tmp / "summary.json"
            inventory_path = tmp / "inventory.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "train_label_counts": {
                            "note_a": 4,
                            "note_b": 2,
                        }
                    }
                ),
                encoding="utf-8",
            )
            inventory_path.write_text(
                json.dumps(
                    [
                        {"note_id": "note_a", "note_text": "Template A", "note_type": "template"},
                        {"note_id": "note_b", "note_text": "Raw B", "note_type": "raw"},
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_label_order(str(summary_path)), ["note_a", "note_b"])
            self.assertEqual(
                load_note_inventory(str(inventory_path)),
                {
                    "note_a": {"note_text": "Template A", "note_type": "template"},
                    "note_b": {"note_text": "Raw B", "note_type": "raw"},
                },
            )


if __name__ == "__main__":
    unittest.main()
