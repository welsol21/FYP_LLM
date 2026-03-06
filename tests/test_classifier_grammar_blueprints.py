import unittest

from ela_pipeline.classifier.grammar_blueprints import build_note_blueprints


class GrammarBlueprintTests(unittest.TestCase):
    def test_build_note_blueprints_adds_context_for_intermediate_and_advanced(self):
        notes = build_note_blueprints(
            grammar_classes=["past_simple_affirmative"],
            cefr_level="A2",
            node_type="Phrase",
            content="came to him",
            grammatical_role="predicate",
            tam_construction="past_simple",
        )
        self.assertIn("came to him", notes["intermediate_text"])
        self.assertIn("predicate", notes["intermediate_text"])
        self.assertIn("came to him", notes["advanced_text"])


if __name__ == "__main__":
    unittest.main()

