import unittest

from ela_pipeline.classifier.train_tabular_cefr_baseline import (
    build_feature_rows,
    evaluate_predictions,
    extract_tabular_features,
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

    def test_evaluate_predictions_returns_macro_metrics(self):
        y_true = ["A1", "A2", "B1", "B1"]
        y_pred = ["A1", "A2", "A2", "B1"]
        metrics = evaluate_predictions(y_true, y_pred)
        self.assertAlmostEqual(metrics["accuracy"], 0.75, places=6)
        self.assertGreater(metrics["macro_f1"], 0.7)
        self.assertEqual(metrics["confusion"]["B1"]["A2"], 1)


if __name__ == "__main__":
    unittest.main()
