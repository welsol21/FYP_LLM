import unittest

from ela_pipeline.classifier.dataset_protocol import (
    canonicalize_grammar_classes,
    ensure_note_blueprints,
    normalize_classifier_row,
)


class ClassifierDatasetProtocolTests(unittest.TestCase):
    def test_canonicalize_grammar_classes_maps_aliases_and_drops_unknown(self):
        classes = canonicalize_grammar_classes(
            ["prepositions_time", "modal_can_ability", "unknown_x", "prepositions_time"]
        )
        self.assertEqual(classes, ["preposition_linker", "modal_can_ability"])

    def test_ensure_note_blueprints_fills_missing_from_class_specs(self):
        out = ensure_note_blueprints(
            note_blueprints={"elementary_text": "", "intermediate_text": "", "advanced_text": ""},
            cefr_label="A2",
            grammar_classes=["modal_can_ability"],
        )
        self.assertTrue(out["elementary_text"])
        self.assertTrue(out["intermediate_text"])
        self.assertTrue(out["advanced_text"])

    def test_normalize_classifier_row_builds_grammar_label_and_cefr(self):
        row = normalize_classifier_row(
            {
                "source_text": "She can swim.",
                "cefr_level": "a2",
                "grammar_classes": ["prepositions_time", "modal_can_ability"],
                "note_blueprints": {},
            }
        )
        self.assertEqual(row["cefr_label"], "A2")
        self.assertEqual(row["grammar_classes"], ["preposition_linker", "modal_can_ability"])
        self.assertEqual(row["grammar_label"], "modal_can_ability|preposition_linker")
        self.assertIn("note_blueprints", row)
        self.assertTrue(row["note_blueprints"]["intermediate_text"])


if __name__ == "__main__":
    unittest.main()

