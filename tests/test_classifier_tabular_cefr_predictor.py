import json
import tempfile
import unittest
from pathlib import Path

import joblib

from ela_pipeline.classifier.tabular_cefr_predictor import TabularCefrPredictor, TabularProfileClassifier, _normalize_cefr


class _FakeModel:
    def __init__(self):
        self.last_rows = None

    def predict(self, rows):
        self.last_rows = rows
        out = []
        for row in rows:
            if int(row.get("token_count", 0)) <= 6:
                out.append("A1")
            else:
                out.append("B2")
        return out


class _FakeJointModel:
    def predict(self, rows):
        out = []
        for row in rows:
            if int(row.get("token_count", 0)) <= 4:
                out.append(("A1", "pronoun_reference"))
            else:
                out.append(("B2", "past_perfect"))
        return out


class _FakeJointModelScalar:
    def predict(self, rows):
        return ["A1|prepositions_time" for _ in rows]


class _FakeJointModelIncompatibleClass:
    def predict(self, rows):
        return ["A2|modal_can_ability" for _ in rows]


class TabularCefrPredictorTests(unittest.TestCase):
    def test_normalize_cefr_accepts_numeric_legacy_labels(self):
        self.assertEqual(_normalize_cefr("0"), "A1")
        self.assertEqual(_normalize_cefr("4"), "C1")
        self.assertEqual(_normalize_cefr("6"), "C2")
        self.assertEqual(_normalize_cefr("4.0"), "C1")

    def test_predict_row_uses_extracted_features(self):
        model = _FakeModel()
        predictor = TabularCefrPredictor(model)
        row = {
            "source_text": "She smiled.",
            "grammar_evidence": {"token_count": 2, "dep_signature": ["nsubj", "root"], "pos_signature": ["PRON", "VERB"]},
        }
        self.assertEqual(predictor.predict_row(row), "A1")
        self.assertNotIn("dataset_source", model.last_rows[0])
        self.assertNotIn("treebank", model.last_rows[0])

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
            (model_dir / "tabular_cefr_baseline_summary.json").write_text(
                json.dumps({"feature_profile": "runtime_stable"}, ensure_ascii=False),
                encoding="utf-8",
            )
            classifier = TabularProfileClassifier(str(model_dir))
            profile = classifier.classify_node(
                node={"tam_construction": "present_simple", "grammar_evidence": {"token_count": 2}},
                source_text="She smiles.",
                sentence_text="She smiles.",
            )
            self.assertEqual(profile["cefr_level"], "A1")
            self.assertNotIn("grammar_classes", profile)
            self.assertNotIn("generated_notes", profile)
            self.assertEqual(classifier.feature_profile, "runtime_stable")

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
            (model_dir / "tabular_cefr_baseline_summary.json").write_text(
                json.dumps({"feature_profile": "runtime_stable"}, ensure_ascii=False),
                encoding="utf-8",
            )
            classifier = TabularProfileClassifier(str(model_dir))
            profile = classifier.classify_node(
                node={"features": {"dep": ["nsubj", "aux", "root", "obj", "punct", "punct", "punct"], "pos": ["PRON", "AUX", "VERB"]}},
                source_text="Although he had already finished the work, he stayed.",
                sentence_text="Although he had already finished the work, he stayed.",
            )
            self.assertEqual(profile["cefr_level"], "B2")

    def test_tabular_profile_classifier_joint_model_returns_cefr_grammar_and_blueprints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            joblib.dump(_FakeJointModel(), model_dir / "best_tabular_joint_profile.joblib")
            metadata = {
                "per_class_cefr_ladder": {"pronoun_reference": ["A1", "A2", "B1", "B2", "C1", "C2"]},
                "grammar_classes_by_cefr": {"A1": ["pronoun_reference"], "A2": [], "B1": [], "B2": [], "C1": [], "C2": []},
                "note_blueprints_by_cefr": {level: {"elementary_text": f"{level} e", "intermediate_text": f"{level} i", "advanced_text": f"{level} a"} for level in ["A1","A2","B1","B2","C1","C2"]},
            }
            (model_dir / "classifier_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            (model_dir / "tabular_cefr_baseline_summary.json").write_text(
                json.dumps({"feature_profile": "runtime_stable"}, ensure_ascii=False),
                encoding="utf-8",
            )
            classifier = TabularProfileClassifier(str(model_dir))
            profile = classifier.classify_node(
                node={"features": {"dep": ["nsubj", "root"], "pos": ["PRON", "VERB"]}},
                source_text="She smiled.",
                sentence_text="She smiled.",
            )
            self.assertTrue(classifier.supports_joint_profiles)
            self.assertEqual(profile["cefr_level"], "A1")
            self.assertIsInstance(profile.get("grammar_classes"), list)
            self.assertEqual(profile["grammar_classes"][0]["class_id"], "pronoun_reference")
            self.assertIsInstance(profile.get("generated_notes"), dict)
            self.assertTrue(profile["generated_notes"].get("intermediate_text"))

    def test_tabular_profile_classifier_joint_model_parses_scalar_joint_label(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            joblib.dump(_FakeJointModelScalar(), model_dir / "best_tabular_joint_profile.joblib")
            metadata = {
                "per_class_cefr_ladder": {"prepositions_time": ["A1", "A2", "B1", "B2", "C1", "C2"]},
                "grammar_classes_by_cefr": {"A1": [], "A2": ["prepositions_time"], "B1": [], "B2": [], "C1": [], "C2": []},
                "note_blueprints_by_cefr": {level: {"elementary_text": f"{level} e", "intermediate_text": f"{level} i", "advanced_text": f"{level} a"} for level in ["A1","A2","B1","B2","C1","C2"]},
            }
            (model_dir / "classifier_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            (model_dir / "tabular_cefr_baseline_summary.json").write_text(
                json.dumps({"feature_profile": "runtime_stable"}, ensure_ascii=False),
                encoding="utf-8",
            )
            classifier = TabularProfileClassifier(str(model_dir))
            profile = classifier.classify_node(
                node={"features": {"dep": ["prep", "pobj"], "pos": ["ADP", "NOUN"]}},
                source_text="towards morning",
                sentence_text="She came to him towards morning.",
            )
            self.assertEqual(profile["cefr_level"], "A1")
            self.assertEqual(profile["grammar_classes"][0]["class_id"], "preposition_linker")
            self.assertIsInstance(profile.get("generated_notes"), dict)
            self.assertTrue(str(profile["generated_notes"].get("elementary_text") or "").strip())
            self.assertTrue(str(profile["generated_notes"].get("intermediate_text") or "").strip())
            self.assertTrue(str(profile["generated_notes"].get("advanced_text") or "").strip())

    def test_tabular_profile_classifier_joint_model_applies_rule_sanity_on_class(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            joblib.dump(_FakeJointModelIncompatibleClass(), model_dir / "best_tabular_joint_profile.joblib")
            metadata = {
                "per_class_cefr_ladder": {
                    "pronoun_reference": ["A1", "A2", "B1", "B2", "C1", "C2"],
                    "modal_can_ability": ["A1", "A2", "B1", "B2", "C1", "C2"],
                },
                "grammar_classes_by_cefr": {"A1": ["pronoun_reference"], "A2": ["modal_can_ability"], "B1": [], "B2": [], "C1": [], "C2": []},
                "note_blueprints_by_cefr": {level: {"elementary_text": f"{level} e", "intermediate_text": f"{level} i", "advanced_text": f"{level} a"} for level in ["A1","A2","B1","B2","C1","C2"]},
            }
            (model_dir / "classifier_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            (model_dir / "tabular_cefr_baseline_summary.json").write_text(
                json.dumps({"feature_profile": "runtime_stable"}, ensure_ascii=False),
                encoding="utf-8",
            )
            classifier = TabularProfileClassifier(str(model_dir))
            profile = classifier.classify_node(
                node={"type": "Word", "part_of_speech": "pronoun", "features": {"dep": ["nsubj"], "pos": ["PRON"]}},
                source_text="She",
                sentence_text="She came.",
            )
            self.assertEqual(profile["cefr_level"], "A2")
            self.assertEqual(profile["grammar_classes"][0]["class_id"], "pronoun_reference")


if __name__ == "__main__":
    unittest.main()
