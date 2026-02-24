import json
import tempfile
import unittest
from unittest.mock import patch

from ela_pipeline.classifier.run_full_orchestrator import run_full_orchestrator


class ClassifierRunFullOrchestratorTests(unittest.TestCase):
    @patch("ela_pipeline.classifier.run_full_orchestrator.run_quality_cycle")
    @patch("ela_pipeline.classifier.run_full_orchestrator.train_deberta_classifier")
    @patch("ela_pipeline.classifier.run_full_orchestrator.build_train_dev_from_enriched_kb")
    @patch("ela_pipeline.classifier.run_full_orchestrator.build_kb_artifacts")
    def test_orchestrator_runs_all_stages_and_writes_summary(
        self,
        kb_mock,
        ds_mock,
        train_mock,
        qc_mock,
    ):
        kb_mock.return_value = {"kb_raw": "a", "kb_spacy_enriched": "b"}
        ds_mock.return_value = {"train": "train.jsonl", "dev": "dev.jsonl", "stats": "stats.json"}
        train_mock.return_value = {"output_dir": "model", "metrics": {"eval_loss": 0.2}}
        qc_mock.return_value = {"all_gates_passed": True, "artifacts": {"quality_summary": "q.json"}}

        with tempfile.TemporaryDirectory() as tmp:
            summary = run_full_orchestrator(run_id="r-orch-1", output_dir=tmp)
            self.assertEqual(summary["status"], "completed")
            self.assertIn("summary_path", summary)
            self.assertEqual(len(summary["stages"]), 4)
            self.assertEqual(summary["stages"][0]["stage"], "build_kb")
            self.assertEqual(summary["stages"][3]["stage"], "run_quality_cycle")
            self.assertIn("build_kb", summary["artifacts"])
            self.assertIn("run_quality_cycle", summary["artifacts"])

            with open(summary["summary_path"], "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk["run_id"], "r-orch-1")
            self.assertEqual(on_disk["status"], "completed")
            self.assertEqual(len(on_disk["stages"]), 4)

    @patch("ela_pipeline.classifier.run_full_orchestrator.build_kb_artifacts")
    def test_orchestrator_stops_on_failed_stage(self, kb_mock):
        kb_mock.side_effect = RuntimeError("kb failed")
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_full_orchestrator(run_id="r-orch-2", output_dir=tmp)
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["failed_stage"], "build_kb")
            self.assertIn("kb failed", str(summary["error_message"]))
            self.assertGreaterEqual(len(summary["stages"]), 1)


if __name__ == "__main__":
    unittest.main()
