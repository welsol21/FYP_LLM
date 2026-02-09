import unittest

from ela_pipeline.validation.notes_quality import is_valid_note, sanitize_note


class NotesQualityTests(unittest.TestCase):
    def test_rejects_node_artifact(self):
        self.assertFalse(is_valid_note("Node_speech phrase functioning as subject."))

    def test_rejects_boolean_literal(self):
        self.assertFalse(is_valid_note("True"))

    def test_accepts_normal_note(self):
        self.assertTrue(is_valid_note("A noun phrase functioning as the subject of the clause."))

    def test_sanitize_whitespace(self):
        self.assertEqual(sanitize_note("  A   short\nnote   "), "A short note")


if __name__ == "__main__":
    unittest.main()
