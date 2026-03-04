import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ela_pipeline.classifier.train_tabular_cefr_baseline import (
    build_feature_rows,
    evaluate_predictions,
    extract_tabular_features,
    project_feature_profile,
    train_tabular_cefr_baseline,
)


class _FakeXGBClassifier:
    def __init__(self, **kwargs):
        self._kwargs = kwargs

    def fit(self, x, y):
        self._labels = list(sorted(set(y)))
        return self

    def predict(self, x):
        # deterministic single-class prediction is enough for IO/metadata test
        label = self._labels[0] if self._labels else 0
        return [label for _ in x]

    def get_params(self, deep=True):
        return dict(self._kwargs)

    def set_params(self, **params):
        self._kwargs.update(params)
        return self


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

    def test_project_feature_profile_drops_source_fields_for_runtime_stable(self):
        features = {
            "word_count": 4,
            "char_count": 20,
            "token_count": 4,
            "dep_count": 4,
            "dep_unique_count": 3,
            "pos_count": 4,
            "pos_unique_count": 3,
            "grammar_class_count": 1,
            "tam_profile": "present_simple",
            "dataset_source": "ud_ewt",
            "treebank": "UD_English-EWT",
            "dep_signature_join": "nsubj|root",
            "pos_signature_join": "PRON|VERB",
            "has_relative_clause_marker": 0,
            "has_clause_embedding": 0,
            "has_passive_signal": 0,
        }
        projected = project_feature_profile(features, profile="runtime_stable")
        self.assertNotIn("dataset_source", projected)
        self.assertNotIn("treebank", projected)
        self.assertIn("tam_profile", projected)
        self.assertIn("dep_signature_join", projected)

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
            fake_xgb = SimpleNamespace(XGBClassifier=_FakeXGBClassifier)
            with patch.dict(sys.modules, {"xgboost": fake_xgb}):
                with patch(
                    "ela_pipeline.classifier.train_tabular_cefr_baseline._assert_gpu_training_available",
                    return_value=None,
                ):
                    summary = train_tabular_cefr_baseline(
                        train_path=str(train_path),
                        dev_path=str(dev_path),
                        test_path=str(test_path),
                        output_dir=str(out_dir),
                        model_names=["xgboost_gpu"],
                    )
            metadata_path = Path(summary["classifier_metadata_path"])
            self.assertTrue(metadata_path.is_file())
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertIn("grammar_classes_by_cefr", payload)
            self.assertIn("note_blueprints_by_cefr", payload)


if __name__ == "__main__":
    unittest.main()
