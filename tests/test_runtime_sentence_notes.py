import unittest

from ela_pipeline.runtime.sentence_notes import build_sentence_notes


class RuntimeSentenceNotesTests(unittest.TestCase):
    def test_build_sentence_notes_focuses_on_subject_and_predicate(self):
        sentence = "She entered very carefully, moving silently, floating through the chamber like a phantom."
        notes = build_sentence_notes(sentence)

        self.assertGreaterEqual(len(notes), 3)
        merged = " ".join(notes).casefold()
        self.assertIn("subject", merged)
        self.assertIn("predicate", merged)
        self.assertNotIn(sentence.casefold(), merged)

    def test_build_sentence_notes_for_phrasal_verbs(self):
        sentence = "She looked after him and turned down the offer."
        notes = build_sentence_notes(sentence)

        self.assertGreaterEqual(len(notes), 3)
        self.assertIn("subject", notes[1].casefold())
        self.assertIn("predicate", notes[1].casefold())


if __name__ == "__main__":
    unittest.main()
