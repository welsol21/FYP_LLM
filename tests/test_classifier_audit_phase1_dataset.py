import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.classifier.audit_phase1_dataset import audit_classifier_dataset


class AuditPhase1DatasetTests(unittest.TestCase):
    def test_reports_ambiguous_grammar_combos(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            rows = [
                {"text": "A", "cefr_level": "A1", "grammar_classes": ["present_simple_affirmative"]},
                {"text": "B", "cefr_level": "A2", "grammar_classes": ["present_simple_affirmative"]},
                {"text": "C", "cefr_level": "B1", "grammar_classes": ["relative_clauses"]},
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            report = audit_classifier_dataset(dataset_path=str(path))
            self.assertEqual(report["samples"], 3)
            self.assertEqual(report["unique_grammar_combos"], 2)
            self.assertEqual(report["ambiguous_grammar_combo_count"], 1)
            self.assertGreater(report["ambiguous_grammar_combo_ratio"], 0.4)
            self.assertEqual(report["exact_text_cross_level_count"], 0)


if __name__ == "__main__":
    unittest.main()
