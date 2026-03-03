import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ela_pipeline.classifier.import_phase1_datasets import import_phase1_datasets


def _row(sample_id: str, text: str, cefr: str, cls: str) -> dict:
    return {
        "id": sample_id,
        "text": text,
        "cefr_level": cefr,
        "grammar_classes": [cls],
        "note_blueprints": {
            "elementary_text": f"{cefr} elem",
            "intermediate_text": f"{cefr} inter",
            "advanced_text": f"{cefr} adv",
        },
    }


class ClassifierImportPhase1DatasetsTests(unittest.TestCase):
    def test_imports_training_and_validation_zips_into_classifier_working_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            train_zip = tmp_path / "train.zip"
            val_zip = tmp_path / "val.zip"

            label_inventory = [{"class_id": "present_simple_affirmative"}, {"class_id": "modal_can_ability"}]
            train_payloads = {
                "label_inventory.json": json.dumps(label_inventory),
                "train.jsonl": "\n".join(
                    [
                        json.dumps(_row("tr-1", "I work every day.", "A1", "present_simple_affirmative")),
                        json.dumps(_row("tr-2", "She can swim.", "A2", "modal_can_ability")),
                    ]
                )
                + "\n",
                "dev.jsonl": json.dumps(_row("dv-1", "He works at school.", "A1", "present_simple_affirmative")) + "\n",
                "test.jsonl": json.dumps(_row("te-1", "They can cook.", "A2", "modal_can_ability")) + "\n",
            }
            val_payloads = {
                "label_inventory.json": json.dumps(label_inventory),
                "validation_core.jsonl": json.dumps(
                    _row("vc-1", "I can read this book.", "A2", "modal_can_ability")
                )
                + "\n",
                "validation_challenge.jsonl": json.dumps(
                    _row("vh-1", "She works and he studies.", "B1", "present_simple_affirmative")
                )
                + "\n",
            }

            with zipfile.ZipFile(train_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for name, content in train_payloads.items():
                    zf.writestr(name, content)
            with zipfile.ZipFile(val_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for name, content in val_payloads.items():
                    zf.writestr(name, content)

            summary = import_phase1_datasets(
                training_zip_path=str(train_zip),
                validation_zip_path=str(val_zip),
                archive_dir=str(tmp_path / "archive"),
                extracted_dir=str(tmp_path / "unpacked"),
                output_dir=str(tmp_path / "processed"),
            )

            self.assertEqual(summary["label_count"], 2)
            self.assertEqual(summary["counts"]["train"], 2)
            self.assertEqual(summary["counts"]["dev"], 1)
            self.assertEqual(summary["counts"]["test"], 1)
            self.assertEqual(summary["counts"]["validation_core"], 1)
            self.assertEqual(summary["counts"]["validation_challenge"], 1)

            train_out = Path(summary["output_files"]["train"])
            self.assertTrue(train_out.is_file())
            first = json.loads(train_out.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("task: classify_cefr_and_grammar text:", first["input"])
            self.assertEqual(first["cefr_label"], "A1")
            self.assertIn("note_blueprints", first)
            self.assertIn("grammar_classes", first)

            manifest_path = Path(summary["manifest_path"])
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["validation_challenge"], 1)


if __name__ == "__main__":
    unittest.main()
