import unittest

from ela_pipeline.classifier.grammar_blueprints import (
    PEDAGOGICAL_CLASS_SPECS,
    build_note_blueprints,
    class_cefr_level,
    humanize_grammar_class_id,
)


class GrammarBlueprintTests(unittest.TestCase):
    def test_humanize_grammar_class_id(self):
        self.assertEqual(humanize_grammar_class_id("modal_perfect"), "modal perfect")

    def test_class_cefr_level(self):
        self.assertEqual(class_cefr_level("future_perfect"), "C2")
        self.assertIsNone(class_cefr_level("missing"))

    def test_build_note_blueprints_uses_shared_spec_for_known_class(self):
        blueprints = build_note_blueprints(
            grammar_classes=["modal_perfect"],
            cefr_level="C1",
            node_type="sentence",
            content="She should have left earlier.",
            grammatical_role="clause",
            tam_construction="modal_perfect",
        )
        self.assertEqual(blueprints["intermediate_text"], PEDAGOGICAL_CLASS_SPECS["modal_perfect"]["intermediate_text"])

    def test_build_note_blueprints_falls_back_to_generic_text(self):
        blueprints = build_note_blueprints(
            grammar_classes=["unknown_pattern"],
            cefr_level="B1",
            node_type="phrase",
            content="left early",
            grammatical_role="modifier",
            tam_construction="none",
        )
        self.assertIn("Main grammar focus: unknown pattern.", blueprints["intermediate_text"])


if __name__ == "__main__":
    unittest.main()
