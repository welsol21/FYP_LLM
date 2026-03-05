import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.train_tabular_joint_profile import _load_jsonl, _primary_class


class TrainTabularJointProfileTests(unittest.TestCase):
    def test_primary_class_uses_canonicalized_grammar_classes(self) -> None:
        row = {
            "grammar_classes": ["prepositions_time", "unknown_x"],
        }
        self.assertEqual(_primary_class(row), "preposition_linker")

    def test_primary_class_falls_back_to_grammar_label(self) -> None:
        row = {
            "grammar_classes": [],
            "grammar_label": "modal_can_ability|unknown_x",
        }
        self.assertEqual(_primary_class(row), "modal_can_ability")

    def test_load_jsonl_applies_dataset_protocol_normalization(self) -> None:
        raw = {
            "source_text": "She can swim.",
            "cefr_level": "a2",
            "grammar_classes": ["modal_can_ability", "unknown_x"],
            "note_blueprints": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "sample.jsonl"
            src.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            rows = _load_jsonl(str(src))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["cefr_label"], "A2")
        self.assertEqual(row["grammar_classes"], ["modal_can_ability"])
        self.assertTrue(row["note_blueprints"]["elementary_text"])


if __name__ == "__main__":
    unittest.main()
