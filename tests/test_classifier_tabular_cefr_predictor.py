import json
import tempfile
import unittest
from pathlib import Path

import joblib

from ela_pipeline.classifier.tabular_cefr_predictor import TabularCefrPredictor, TabularProfileClassifier


class _FakeModel:
    def predict(self, rows):
        out = []
        for row in rows:
            if int(row.get("token_count", 0)) <= 6:
                out.append("A1")
            else:
                out.append("B2")
        return out


class TabularCefrPredictorTests(unittest.TestCase):
    def test_predict_row_uses_extracted_features(self):
        predictor = TabularCefrPredictor(_FakeModel())
        row = {
            "source_text": "She smiled.",
            "grammar_evidence": {"token_count": 2, "dep_signature": ["nsubj", "root"], "pos_signature": ["PRON", "VERB"]},
        }
        self.assertEqual(predictor.predict_row(row), "A1")

    def test_predict_rows_handles_multiple_rows(self):
        predictor = TabularCefrPredictor(_FakeModel())
        rows = [
            {"source_text": "She smiled.", "grammar_evidence": {"token_count": 2}},
            {"source_text": "Although he had already finished the work, he stayed.", "grammar_evidence": {"token_count": 10}},
        ]
        self.assertEqual(predictor.predict_rows(rows), ["A1", "B2"])

    def test_tabular_profile_classifier_loads_model_dir_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            joblib.dump(_FakeModel(), model_dir / "best_tabular_cefr_baseline.joblib")
            metadata = {
                "per_class_cefr_ladder": {"present_simple_affirmative": ["A1", "A2", "B1", "B2", "C1", "C2"]},
                "grammar_classes_by_cefr": {"A1": ["present_simple_affirmative"], "A2": [], "B1": [], "B2": [], "C1": [], "C2": []},
                "note_blueprints_by_cefr": {
                    "A1": {"elementary_text": "A1 e", "intermediate_text": "A1 i", "advanced_text": "A1 a"},
                    "A2": {"elementary_text": "A2 e", "intermediate_text": "A2 i", "advanced_text": "A2 a"},
                    "B1": {"elementary_text": "B1 e", "intermediate_text": "B1 i", "advanced_text": "B1 a"},
                    "B2": {"elementary_text": "B2 e", "intermediate_text": "B2 i", "advanced_text": "B2 a"},
                    "C1": {"elementary_text": "C1 e", "intermediate_text": "C1 i", "advanced_text": "C1 a"},
                    "C2": {"elementary_text": "C2 e", "intermediate_text": "C2 i", "advanced_text": "C2 a"},
                },
            }
            (model_dir / "classifier_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            classifier = TabularProfileClassifier(str(model_dir))
            profile = classifier.classify_node(
                node={"tam_construction": "present_simple", "grammar_evidence": {"token_count": 2}},
                source_text="She smiles.",
                sentence_text="She smiles.",
            )
            self.assertEqual(profile["cefr_level"], "A1")
            self.assertEqual(profile["grammar_classes"][0]["class_id"], "present_simple_affirmative")
            self.assertEqual(profile["generated_notes"]["intermediate_text"], "A1 i")

    def test_tabular_profile_classifier_uses_node_features_when_runtime_evidence_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            joblib.dump(_FakeModel(), model_dir / "best_tabular_cefr_baseline.joblib")
            metadata = {
                "per_class_cefr_ladder": {"past_perfect": ["A1", "A2", "B1", "B2", "C1", "C2"]},
                "grammar_classes_by_cefr": {"A1": [], "A2": [], "B1": [], "B2": ["past_perfect"], "C1": [], "C2": []},
                "note_blueprints_by_cefr": {level: {"elementary_text": f"{level} e", "intermediate_text": f"{level} i", "advanced_text": f"{level} a"} for level in ["A1","A2","B1","B2","C1","C2"]},
            }
            (model_dir / "classifier_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            classifier = TabularProfileClassifier(str(model_dir))
            profile = classifier.classify_node(
                node={"features": {"dep": ["nsubj", "aux", "root", "obj", "punct", "punct", "punct"], "pos": ["PRON", "AUX", "VERB"]}},
                source_text="Although he had already finished the work, he stayed.",
                sentence_text="Although he had already finished the work, he stayed.",
            )
            self.assertEqual(profile["cefr_level"], "B2")
            self.assertEqual(profile["grammar_classes"][0]["class_id"], "past_perfect")


if __name__ == "__main__":
    unittest.main()
