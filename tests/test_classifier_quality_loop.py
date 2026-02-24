import json
import tempfile
import unittest

from ela_pipeline.classifier.quality_loop import (
    evaluate_quality_gate,
    persist_quality_telemetry,
    run_stage_with_retry,
)


class ClassifierQualityLoopTests(unittest.TestCase):
    def test_each_gate_passes_with_good_metrics(self):
        cases = {
            "kb_generation": {
                "class_coverage": 0.99,
                "level_balance": 0.9,
                "duplicate_ratio_max": 0.05,
                "invalid_blueprint_ratio_max": 0.01,
            },
            "spacy_enrichment": {
                "parse_success_rate": 0.99,
                "required_feature_coverage": 0.96,
                "structural_anomaly_rate_max": 0.01,
            },
            "classifier": {
                "macro_f1": 0.9,
                "min_class_recall": 0.8,
                "ece_max": 0.05,
            },
            "contract": {
                "schema_pass_rate": 1.0,
                "consistency_pass_rate": 0.99,
                "blueprint_completeness": 1.0,
            },
            "nlg": {
                "note_relevance": 0.95,
                "level_style_fit": 0.9,
                "hallucination_rate_max": 0.01,
            },
        }
        for gate, metrics in cases.items():
            result = evaluate_quality_gate(gate, metrics)
            self.assertTrue(result.passed, msg=f"{gate}: {result.details}")

    def test_retry_loop_generates_events_and_repairs_until_pass(self):
        # attempt1 fail, attempt2 fail, attempt3 pass
        attempts = {
            1: {"macro_f1": 0.70, "min_class_recall": 0.5, "ece_max": 0.2},
            2: {"macro_f1": 0.80, "min_class_recall": 0.69, "ece_max": 0.11},
            3: {"macro_f1": 0.83, "min_class_recall": 0.71, "ece_max": 0.10},
        }

        result, events, repairs = run_stage_with_retry(
            run_id="r1",
            stage="train_classifier",
            gate="classifier",
            measure_metrics=lambda attempt: attempts[attempt],
            max_attempts=3,
        )
        self.assertTrue(result.passed)
        self.assertEqual(len(events), 3)
        self.assertEqual(len(repairs), 2)
        self.assertEqual(events[-1].attempt, 3)
        self.assertTrue(events[-1].passed)

    def test_retry_loop_stops_on_fail_after_max_attempts(self):
        result, events, repairs = run_stage_with_retry(
            run_id="r2",
            stage="enrich_spacy",
            gate="spacy_enrichment",
            measure_metrics=lambda _attempt: {
                "parse_success_rate": 0.80,
                "required_feature_coverage": 0.70,
                "structural_anomaly_rate_max": 0.10,
            },
            max_attempts=2,
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(events), 2)
        self.assertEqual(len(repairs), 1)

    def test_persist_quality_telemetry_writes_expected_files(self):
        result, events, repairs = run_stage_with_retry(
            run_id="r3",
            stage="gate_contract",
            gate="contract",
            measure_metrics=lambda attempt: {
                "schema_pass_rate": 1.0 if attempt > 1 else 0.9,
                "consistency_pass_rate": 0.99,
                "blueprint_completeness": 1.0,
            },
            max_attempts=2,
        )
        self.assertTrue(result.passed)
        with tempfile.TemporaryDirectory() as tmp:
            paths = persist_quality_telemetry(
                output_dir=tmp,
                quality_events=events,
                repair_actions=repairs,
            )
            with open(paths["quality_events"], "r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            with open(paths["repair_actions"], "r", encoding="utf-8") as f:
                repairs_lines = [json.loads(line) for line in f if line.strip()]

            self.assertEqual(len(lines), 2)
            self.assertGreaterEqual(len(repairs_lines), 1)
            self.assertEqual(lines[0]["gate"], "contract")


if __name__ == "__main__":
    unittest.main()
