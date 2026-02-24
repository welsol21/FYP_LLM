import unittest

from ela_pipeline.classifier.kb import band_for_cefr, build_seed_grammar_kb, group_kb_by_band


class ClassifierKBTests(unittest.TestCase):
    def test_band_for_cefr(self):
        self.assertEqual(band_for_cefr("A1"), "Elementary")
        self.assertEqual(band_for_cefr("A2"), "Elementary")
        self.assertEqual(band_for_cefr("B1"), "Intermediate")
        self.assertEqual(band_for_cefr("B2"), "Intermediate")
        self.assertEqual(band_for_cefr("C1"), "Advanced")
        self.assertEqual(band_for_cefr("C2"), "Advanced")

    def test_build_seed_kb_contains_all_three_bands(self):
        rows = build_seed_grammar_kb()
        self.assertGreaterEqual(len(rows), 6)
        grouped = group_kb_by_band(rows)
        self.assertGreater(len(grouped["Elementary"]), 0)
        self.assertGreater(len(grouped["Intermediate"]), 0)
        self.assertGreater(len(grouped["Advanced"]), 0)

    def test_seed_entries_have_all_blueprints(self):
        rows = build_seed_grammar_kb()
        for row in rows:
            self.assertTrue(row.class_id.startswith("tense_table::"))
            self.assertTrue(row.blueprint_elementary.strip())
            self.assertTrue(row.blueprint_intermediate.strip())
            self.assertTrue(row.blueprint_advanced.strip())


if __name__ == "__main__":
    unittest.main()
