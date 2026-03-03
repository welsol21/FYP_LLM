import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.metadata import (
    build_classifier_metadata_from_dataset,
    build_classifier_metadata_from_kb,
)


class ClassifierMetadataTests(unittest.TestCase):
    def test_build_classifier_metadata_from_kb(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb_path = Path(tmp) / "kb_raw.jsonl"
            rows = [
                {
                    "class_id": "tense_table::present_simple_active",
                    "cefr_level": "A1",
                    "blueprint_elementary": "A1 E",
                    "blueprint_intermediate": "A1 I",
                    "blueprint_advanced": "A1 A",
                },
                {
                    "class_id": "tense_table::past_simple_active",
                    "cefr_level": "A2",
                    "blueprint_elementary": "A2 E",
                    "blueprint_intermediate": "A2 I",
                    "blueprint_advanced": "A2 A",
                },
            ]
            kb_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

            summary = build_classifier_metadata_from_kb(kb_raw_path=str(kb_path), output_dir=tmp)
            self.assertEqual(summary["class_count"], 2)
            self.assertIn("metadata_path", summary)

            metadata = json.loads(Path(summary["metadata_path"]).read_text(encoding="utf-8"))
            self.assertIn("per_class_cefr_ladder", metadata)
            self.assertIn("grammar_classes_by_cefr", metadata)
            self.assertIn("note_blueprints_by_cefr", metadata)
            self.assertIn("tense_table::present_simple_active", metadata["grammar_classes_by_cefr"]["A1"])
            self.assertEqual(
                metadata["note_blueprints_by_cefr"]["A2"]["intermediate_text"],
                "A2 I",
            )

    def test_build_classifier_metadata_from_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds_path = Path(tmp) / "train_classifier.jsonl"
            rows = [
                {
                    "input": "task: classify text: She walks.",
                    "cefr_label": "A1",
                    "grammar_classes": ["tense_table::present_simple_active"],
                    "note_blueprints": {
                        "elementary_text": "A1 E",
                        "intermediate_text": "A1 I",
                        "advanced_text": "A1 A",
                    },
                },
                {
                    "input": "task: classify text: She walked.",
                    "cefr_label": "A2",
                    "grammar_classes": ["tense_table::past_simple_active"],
                    "note_blueprints": {
                        "elementary_text": "A2 E",
                        "intermediate_text": "A2 I",
                        "advanced_text": "A2 A",
                    },
                },
            ]
            ds_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

            summary = build_classifier_metadata_from_dataset(classifier_jsonl_path=str(ds_path), output_dir=tmp)
            self.assertEqual(summary["class_count"], 2)

            metadata = json.loads(Path(summary["metadata_path"]).read_text(encoding="utf-8"))
            self.assertIn("tense_table::present_simple_active", metadata["grammar_classes_by_cefr"]["A1"])
            self.assertEqual(
                metadata["note_blueprints_by_cefr"]["A2"]["intermediate_text"],
                "A2 I",
            )


if __name__ == "__main__":
    unittest.main()
