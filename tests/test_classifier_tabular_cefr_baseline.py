import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.train_tabular_cefr_baseline import (
    build_feature_rows,
    evaluate_predictions,
    extract_tabular_features,
    train_tabular_cefr_baseline,
)


class TabularCefrBaselineTests(unittest.TestCase):
    def test_extract_tabular_features_uses_existing_signatures(self):
        row = {
            "source_text": "She had finished the work.",
            "tam_profile": "past_perfect",
            "grammar_label": "past_perfect",
            "grammar_classes": ["past_perfect"],
            "grammar_evidence": {
                "dep_signature": ["nsubj", "aux", "root", "det", "obj", "punct"],
                "pos_signature": ["PRON", "AUX", "VERB", "DET", "NOUN", "PUNCT"],
                "token_count": 6,
            },
            "provenance": {"dataset_source": "ud_gum", "treebank": "UD_English-GUM"},
        }
        features = extract_tabular_features(row)
        self.assertEqual(features["token_count"], 6)
        self.assertEqual(features["dataset_source"], "ud_gum")
        self.assertIn("nsubj|aux|root", features["dep_signature_join"])
        self.assertNotIn("grammar_label", features)

    def test_build_feature_rows_filters_invalid_labels(self):
        rows = [
            {"source_text": "A.", "cefr_label": "A1", "grammar_evidence": {}},
            {"source_text": "B.", "cefr_label": "", "grammar_evidence": {}},
        ]
        features, labels = build_feature_rows(rows)
        self.assertEqual(len(features), 1)
        self.assertEqual(labels, ["A1"])

    def test_build_feature_rows_supports_grammar_label(self):
        rows = [
            {"source_text": "A.", "grammar_label": "past_perfect", "grammar_evidence": {}},
            {"source_text": "B.", "grammar_label": "", "grammar_evidence": {}},
        ]
        features, labels = build_feature_rows(rows, label_field="grammar_label")
        self.assertEqual(len(features), 1)
        self.assertEqual(labels, ["past_perfect"])

    def test_evaluate_predictions_returns_macro_metrics(self):
        y_true = ["A1", "A2", "B1", "B1"]
        y_pred = ["A1", "A2", "A2", "B1"]
        metrics = evaluate_predictions(y_true, y_pred)
        self.assertAlmostEqual(metrics["accuracy"], 0.75, places=6)
        self.assertGreater(metrics["macro_f1"], 0.7)
        self.assertEqual(metrics["confusion"]["B1"]["A2"], 1)

    def test_train_tabular_cefr_baseline_writes_classifier_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            train_path = Path(tmpdir) / "train.jsonl"
            dev_path = Path(tmpdir) / "dev.jsonl"
            test_path = Path(tmpdir) / "test.jsonl"
            out_dir = Path(tmpdir) / "model"
            rows = [
                {
                    "source_text": "She smiles.",
                    "cefr_label": "A1",
                    "tam_profile": "present_simple",
                    "grammar_classes": ["present_simple_affirmative"],
                    "grammar_evidence": {"token_count": 2, "dep_signature": ["nsubj", "root"], "pos_signature": ["PRON", "VERB"]},
                    "note_blueprints": {"elementary_text": "A1 e", "intermediate_text": "A1 i", "advanced_text": "A1 a"},
                },
                {
                    "source_text": "She had finished.",
                    "cefr_label": "B2",
                    "tam_profile": "past_perfect",
                    "grammar_classes": ["past_perfect"],
                    "grammar_evidence": {"token_count": 3, "dep_signature": ["nsubj", "aux", "root"], "pos_signature": ["PRON", "AUX", "VERB"]},
                    "note_blueprints": {"elementary_text": "B2 e", "intermediate_text": "B2 i", "advanced_text": "B2 a"},
                },
            ]
            for path in (train_path, dev_path, test_path):
                with path.open("w", encoding="utf-8") as f:
                    for row in rows:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
            summary = train_tabular_cefr_baseline(
                train_path=str(train_path),
                dev_path=str(dev_path),
                test_path=str(test_path),
                output_dir=str(out_dir),
                model_names=["logreg"],
            )
            metadata_path = Path(summary["classifier_metadata_path"])
            self.assertTrue(metadata_path.is_file())
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertIn("grammar_classes_by_cefr", payload)
            self.assertIn("note_blueprints_by_cefr", payload)


if __name__ == "__main__":
    unittest.main()
