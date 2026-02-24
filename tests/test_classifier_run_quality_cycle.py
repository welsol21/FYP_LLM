import json
import tempfile
import unittest

from ela_pipeline.classifier.run_quality_cycle import run_quality_cycle


class ClassifierRunQualityCycleTests(unittest.TestCase):
    def test_run_quality_cycle_writes_artifacts_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_quality_cycle(
                output_dir=tmp,
                run_id="r-qc-1",
                required_consecutive_passes=2,
                max_attempts_per_gate=3,
            )
            self.assertIn("artifacts", summary)
            artifacts = summary["artifacts"]
            for key in ("quality_events", "repair_actions", "quality_summary"):
                self.assertIn(key, artifacts)
            with open(artifacts["quality_summary"], "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk["run_id"], "r-qc-1")
            self.assertIn("gates", on_disk)
            self.assertIn("iterative_loop", on_disk)

    def test_run_quality_cycle_can_fail_with_bad_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = {
                "classifier": [
                    {"macro_f1": 0.4, "min_class_recall": 0.2, "ece_max": 0.3},
                    {"macro_f1": 0.5, "min_class_recall": 0.3, "ece_max": 0.25},
                ]
            }
            summary = run_quality_cycle(
                output_dir=tmp,
                run_id="r-qc-2",
                gate_metrics=bad,
                max_attempts_per_gate=2,
                required_consecutive_passes=2,
            )
            classifier_row = next(item for item in summary["gates"] if item["gate"] == "classifier")
            self.assertFalse(classifier_row["passed"])
            self.assertFalse(summary["all_gates_passed"])


if __name__ == "__main__":
    unittest.main()
