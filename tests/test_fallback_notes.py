import unittest

from ela_pipeline.annotate.fallback_notes import build_fallback_note
from ela_pipeline.validation.notes_quality import is_valid_note


class FallbackNotesTests(unittest.TestCase):
    def test_sentence_fallback_is_valid(self):
        node = {
            "type": "Sentence",
            "content": "She reads every day.",
            "tense": "present",
            "part_of_speech": "sentence",
        }
        note = build_fallback_note(node)
        self.assertTrue(is_valid_note(note))

    def test_phrase_fallback_mentions_content(self):
        node = {
            "type": "Phrase",
            "content": "the white coat",
            "tense": "null",
            "part_of_speech": "noun phrase",
        }
        note = build_fallback_note(node)
        self.assertIn("the white coat", note)
        self.assertTrue(is_valid_note(note))

    def test_word_fallback_article(self):
        node = {
            "type": "Word",
            "content": "the",
            "tense": "null",
            "part_of_speech": "article",
        }
        note = build_fallback_note(node)
        self.assertIn("definite article", note.lower())
        self.assertTrue(is_valid_note(note))

    def test_word_fallback_verb_tense(self):
        node = {
            "type": "Word",
            "content": "examined",
            "tense": "past",
            "part_of_speech": "verb",
        }
        note = build_fallback_note(node)
        self.assertIn("past-form", note.lower())
        self.assertTrue(is_valid_note(note))

    def test_word_fallback_preposition_semantics(self):
        node = {
            "type": "Word",
            "content": "on",
            "tense": "null",
            "part_of_speech": "preposition",
        }
        note = build_fallback_note(node)
        self.assertIn("surface", note.lower())
        self.assertTrue(is_valid_note(note))

    def test_word_fallback_auxiliary_verb_is_valid_and_non_empty(self):
        node = {
            "type": "Word",
            "content": "should",
            "tense": "null",
            "part_of_speech": "auxiliary verb",
        }
        note = build_fallback_note(node)
        self.assertNotEqual(note.strip(), "")
        self.assertIn("'should'", note.lower())
        self.assertTrue(is_valid_note(note))


if __name__ == "__main__":
    unittest.main()
