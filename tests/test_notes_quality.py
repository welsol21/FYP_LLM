import json
import os
import tempfile
import unittest

from ela_pipeline.validation import notes_quality as nq


class NotesQualityTests(unittest.TestCase):
    def test_rejects_node_artifact(self):
        self.assertFalse(nq.is_valid_note("Node_speech phrase functioning as subject."))

    def test_rejects_boolean_literal(self):
        self.assertFalse(nq.is_valid_note("True"))

    def test_accepts_normal_note(self):
        self.assertTrue(nq.is_valid_note("A noun phrase functioning as the subject of the clause."))

    def test_accepts_note_with_tense_word(self):
        self.assertTrue(
            nq.is_valid_note(
                "This auxiliary verb supports tense and aspect interpretation in the verbal group."
            )
        )

    def test_rejects_generic_template(self):
        text = "Subordinate clause of concession introduced by a subordinating conjunction."
        self.assertTrue(nq.is_generic_template(text))
        self.assertFalse(nq.is_valid_note(text))

    def test_rejects_gibberish_template(self):
        text = "Sensibilisation: a simple note with an educational linguistic tone."
        self.assertTrue(nq.is_generic_template(text))
        self.assertFalse(nq.is_valid_note(text))

    def test_sanitize_whitespace(self):
        self.assertEqual(nq.sanitize_note("  A   short\nnote   "), "A short note")

    def test_external_hard_negative_patterns_are_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            patterns_path = os.path.join(tmpdir, "hard_negative_patterns.json")
            with open(patterns_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": "v1",
                        "phrases": [
                            {"text": "Sentence is a nod to the subject of the clause.", "count": 4}
                        ],
                    },
                    f,
                )

            old_path = os.environ.get("ELA_HARD_NEGATIVE_PATTERNS")
            os.environ["ELA_HARD_NEGATIVE_PATTERNS"] = patterns_path
            nq._load_external_patterns.cache_clear()
            try:
                text = "Sentence is a nod to the subject of the clause."
                self.assertTrue(nq.is_generic_template(text))
                self.assertFalse(nq.is_valid_note(text))
            finally:
                if old_path is None:
                    os.environ.pop("ELA_HARD_NEGATIVE_PATTERNS", None)
                else:
                    os.environ["ELA_HARD_NEGATIVE_PATTERNS"] = old_path
                nq._load_external_patterns.cache_clear()


if __name__ == "__main__":
    unittest.main()
