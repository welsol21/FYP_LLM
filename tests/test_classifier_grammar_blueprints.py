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

    def test_build_note_blueprints_does_not_emit_other_role_hint(self):
        notes = build_note_blueprints(
            grammar_classes=["past_simple_affirmative"],
            cefr_level="A2",
            node_type="Word",
            content="came",
            grammatical_role="other",
            part_of_speech="verb",
            tense="past",
        )
        self.assertNotIn("functions as other", notes["intermediate_text"].lower())
        self.assertNotIn("fills the other role", notes["advanced_text"].lower())

    def test_build_note_blueprints_overrides_finite_clause_note_for_past_participle_word(self):
        notes = build_note_blueprints(
            grammar_classes=["present_simple_affirmative"],
            cefr_level="A1",
            node_type="Word",
            content="written",
            grammatical_role="other",
            part_of_speech="verb",
            tense="past participle",
        )
        combined = " ".join(notes.values()).lower()
        self.assertIn("past participle", combined)
        self.assertNotIn("present simple", combined)
        self.assertNotIn("subject-verb agreement", combined)
        self.assertNotIn("routine meaning", combined)


if __name__ == "__main__":
    unittest.main()
