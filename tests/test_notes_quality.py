import unittest

from ela_pipeline.validation.notes_quality import is_generic_template, is_valid_note, sanitize_note


class NotesQualityTests(unittest.TestCase):
    def test_rejects_node_artifact(self):
        self.assertFalse(is_valid_note("Node_speech phrase functioning as subject."))

    def test_rejects_boolean_literal(self):
        self.assertFalse(is_valid_note("True"))

    def test_accepts_normal_note(self):
        self.assertTrue(is_valid_note("A noun phrase functioning as the subject of the clause."))

    def test_accepts_note_with_tense_word(self):
        self.assertTrue(
            is_valid_note(
                "This auxiliary verb supports tense and aspect interpretation in the verbal group."
            )
        )

    def test_rejects_generic_template(self):
        text = "Subordinate clause of concession introduced by a subordinating conjunction."
        self.assertTrue(is_generic_template(text))
        self.assertFalse(is_valid_note(text))

    def test_rejects_gibberish_template(self):
        text = "Sensibilisation: a simple note with an educational linguistic tone."
        self.assertTrue(is_generic_template(text))
        self.assertFalse(is_valid_note(text))

    def test_sanitize_whitespace(self):
        self.assertEqual(sanitize_note("  A   short\nnote   "), "A short note")


if __name__ == "__main__":
    unittest.main()
