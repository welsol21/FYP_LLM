import unittest

from ela_pipeline.classifier.iterative_loop import run_iterative_improvement_loop
from ela_pipeline.classifier.quality_loop import GateResult


class ClassifierIterativeLoopTests(unittest.TestCase):
    def test_stops_after_required_consecutive_passes(self):
        # fail, pass, pass => stop when required_consecutive_passes=2
        states = {
            1: [GateResult(gate="classifier", passed=False, details={})],
            2: [GateResult(gate="classifier", passed=True, details={})],
            3: [GateResult(gate="classifier", passed=True, details={})],
        }
        records, ok = run_iterative_improvement_loop(
            evaluate_full_run=lambda idx: states[idx],
            required_consecutive_passes=2,
            max_iterations=10,
        )
        self.assertTrue(ok)
        self.assertEqual(len(records), 3)
        self.assertFalse(records[0].all_passed)
        self.assertTrue(records[1].all_passed)
        self.assertTrue(records[2].all_passed)

    def test_returns_false_when_max_iterations_reached(self):
        records, ok = run_iterative_improvement_loop(
            evaluate_full_run=lambda _idx: [GateResult(gate="contract", passed=False, details={})],
            required_consecutive_passes=2,
            max_iterations=4,
        )
        self.assertFalse(ok)
        self.assertEqual(len(records), 4)
        self.assertTrue(all(not r.all_passed for r in records))


if __name__ == "__main__":
    unittest.main()
