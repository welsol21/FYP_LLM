import json
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
