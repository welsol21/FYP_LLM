import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ela_pipeline.classifier.deberta import DebertaProfileClassifier


class DebertaClassifierTests(unittest.TestCase):
    def test_gpu_only_policy_rejects_non_cuda_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(f"{tmp}/classifier_metadata.json", "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "per_class_cefr_ladder": {
                            "tam::past": ["A1", "A2", "B1", "B2", "C1", "C2"],
                        },
                        "grammar_classes_by_cefr": {"B1": ["tam::past"]},
                        "note_blueprints_by_cefr": {
                            "B1": {
                                "elementary_text": "E",
                                "intermediate_text": "I",
                                "advanced_text": "A",
                            }
                        },
                    },
                    f,
                    ensure_ascii=False,
                )

            with self.assertRaises(RuntimeError):
                DebertaProfileClassifier(model_path=tmp, device="cpu")

    @patch("ela_pipeline.classifier.deberta.os.path.isdir", return_value=True)
    @patch("ela_pipeline.classifier.deberta.os.path.isfile", return_value=True)
    @patch("ela_pipeline.classifier.deberta.validate_per_class_cefr_ladder", return_value=[])
    def test_classifier_returns_cefr_only_payload(self, _mock_validate, _mock_isfile, _mock_isdir):
        with tempfile.TemporaryDirectory() as tmp:
            with open(f"{tmp}/classifier_metadata.json", "w", encoding="utf-8") as f:
                json.dump({"per_class_cefr_ladder": {"x": ["A1", "A2", "B1", "B2", "C1", "C2"]}}, f)

            fake_pipe = lambda prompt: [{"label": "B1"}]
            fake_transformers = SimpleNamespace(pipeline=lambda *args, **kwargs: fake_pipe)
            fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
            with patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}):
                    clf = DebertaProfileClassifier(model_path=tmp, device="cuda")
                    payload = clf.classify_node(node={"type": "Sentence"}, source_text="alpha", sentence_text="alpha")
            self.assertEqual(payload, {"cefr_level": "B1"})


if __name__ == "__main__":
    unittest.main()
