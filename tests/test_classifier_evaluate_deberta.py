import unittest

from ela_pipeline.classifier.evaluate_deberta_classifier import evaluate_rows


class EvaluateDebertaTests(unittest.TestCase):
    def test_evaluate_rows_computes_accuracy_and_macro_f1(self):
        rows = [
            {"input": "x1", "cefr_label": "A1"},
            {"input": "x2", "cefr_label": "A2"},
            {"input": "x3", "cefr_label": "B1"},
            {"input": "x4", "cefr_label": "B1"},
        ]
        mapping = {"x1": "A1", "x2": "A2", "x3": "A2", "x4": "B1"}
        metrics = evaluate_rows(rows, lambda text: mapping[text])
        self.assertEqual(metrics["samples"], 4)
        self.assertAlmostEqual(metrics["accuracy"], 0.75, places=6)
        self.assertGreater(metrics["macro_f1"], 0.7)
        self.assertEqual(metrics["confusion"]["B1"]["A2"], 1)


if __name__ == "__main__":
    unittest.main()
