import unittest

from ela_pipeline.classifier.rollout import (
    PHASE_ORDER,
    build_phase_time_summary,
    can_start_phase,
    get_phase,
)


class ClassifierRolloutTests(unittest.TestCase):
    def test_phase_specs_are_defined(self):
        self.assertEqual(PHASE_ORDER, ("phase1", "phase2", "phase3"))
        self.assertEqual(get_phase("phase1").levels, ("A1", "A2", "B1"))
        self.assertEqual(get_phase("phase2").levels, ("B2",))
        self.assertEqual(get_phase("phase3").levels, ("C1", "C2"))

    def test_gate_rule_requires_repeated_pass_runs_for_non_phase1(self):
        self.assertTrue(can_start_phase("phase1", repeated_pass_runs=0))
        self.assertFalse(can_start_phase("phase2", repeated_pass_runs=2, min_repeated_pass_runs=3))
        self.assertTrue(can_start_phase("phase2", repeated_pass_runs=3, min_repeated_pass_runs=3))
        self.assertTrue(can_start_phase("phase3", repeated_pass_runs=5, min_repeated_pass_runs=3))

    def test_time_summary_contains_expected_windows(self):
        summary = build_phase_time_summary()
        self.assertEqual(summary["phase1"]["mvp_weeks"], "1.5-2.5")
        self.assertEqual(summary["phase1"]["stable_weeks"], "3-4")
        self.assertEqual(summary["phase2"]["mvp_weeks"], "1-2.5")
        self.assertEqual(summary["phase3"]["mvp_weeks"], "2-4")
        self.assertEqual(summary["full_ladder_target_weeks"], "6-10")


if __name__ == "__main__":
    unittest.main()
