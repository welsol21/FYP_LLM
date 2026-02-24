import unittest

from ela_pipeline.classifier.curriculum import validate_per_class_cefr_ladder


class ClassifierCurriculumTests(unittest.TestCase):
    def test_accepts_full_ordered_ladder(self):
        issues = validate_per_class_cefr_ladder(
            {
                "tam::modal_perfect": ["A1", "A2", "B1", "B2", "C1", "C2"],
            }
        )
        self.assertEqual(issues, [])

    def test_rejects_missing_levels(self):
        issues = validate_per_class_cefr_ladder(
            {
                "tam::modal_perfect": ["A2", "B1", "B2"],
            }
        )
        self.assertTrue(any("missing required levels" in issue.message for issue in issues))

    def test_rejects_wrong_order(self):
        issues = validate_per_class_cefr_ladder(
            {
                "tam::modal_perfect": ["A1", "B1", "A2", "B2", "C1", "C2"],
            }
        )
        self.assertTrue(any("non-decreasing CEFR order" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
