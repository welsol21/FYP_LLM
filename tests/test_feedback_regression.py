import unittest

from ela_pipeline.training.feedback_regression import RegressionThresholds, evaluate_feedback_regression


class TestFeedbackRegression(unittest.TestCase):
    def test_regression_passes_when_candidate_improves_and_contract_is_present(self):
        baseline_train = {"eval_metrics": {"eval_exact_match": 0.30, "eval_loss": 0.20}}
        candidate_train = {"eval_metrics": {"eval_exact_match": 0.34, "eval_loss": 0.19}}
        baseline_qc = {
            "probe_count": 5,
            "aggregate": {
                "total_nodes": 100,
                "accepted_note_rate": 0.40,
                "fallback_rate": 0.50,
                "rejected_nodes_total": 10,
                "semantic_mismatch_rate": 0.03,
            },
        }
        candidate_qc = {
            "probe_count": 5,
            "aggregate": {
                "total_nodes": 100,
                "accepted_note_rate": 0.45,
                "fallback_rate": 0.46,
                "rejected_nodes_total": 7,
                "semantic_mismatch_rate": 0.02,
            },
        }
        report = evaluate_feedback_regression(
            baseline_train_report=baseline_train,
            candidate_train_report=candidate_train,
            baseline_qc_report=baseline_qc,
            candidate_qc_report=candidate_qc,
            thresholds=RegressionThresholds(),
        )
        self.assertTrue(report["overall_passed"])

    def test_regression_fails_when_candidate_degrades(self):
        baseline_train = {"eval_metrics": {"eval_exact_match": 0.30, "eval_loss": 0.20}}
        candidate_train = {"eval_metrics": {"eval_exact_match": 0.29, "eval_loss": 0.23}}
        baseline_qc = {
            "probe_count": 5,
            "aggregate": {
                "total_nodes": 100,
                "accepted_note_rate": 0.40,
                "fallback_rate": 0.50,
                "rejected_nodes_total": 10,
                "semantic_mismatch_rate": 0.03,
            },
        }
        candidate_qc = {
            "probe_count": 5,
            "aggregate": {
                "total_nodes": 100,
                "accepted_note_rate": 0.35,
                "fallback_rate": 0.55,
                "rejected_nodes_total": 14,
                "semantic_mismatch_rate": 0.05,
            },
        }
        report = evaluate_feedback_regression(
            baseline_train_report=baseline_train,
            candidate_train_report=candidate_train,
            baseline_qc_report=baseline_qc,
            candidate_qc_report=candidate_qc,
            thresholds=RegressionThresholds(),
        )
        self.assertFalse(report["overall_passed"])
        failed_names = {item["name"] for item in report["checks"] if not item["passed"]}
        self.assertIn("train_eval_exact_match_non_regression", failed_names)
        self.assertIn("train_eval_loss_non_increase", failed_names)
        self.assertIn("qc_fallback_rate_non_increase", failed_names)


if __name__ == "__main__":
    unittest.main()
