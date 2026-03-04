import unittest

from ela_pipeline.classifier.tabular_cefr_predictor import TabularCefrPredictor


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


if __name__ == "__main__":
    unittest.main()
