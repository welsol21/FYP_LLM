import unittest

from ela_pipeline.runtime.sentence_notes import build_sentence_notes


class RuntimeSentenceNotesTests(unittest.TestCase):
    def test_build_sentence_notes_focuses_on_subject_and_predicate(self):
        sentence = "She entered very carefully, moving silently, floating through the chamber like a phantom."
        notes = build_sentence_notes(sentence)

        self.assertIsInstance(notes, dict)
        self.assertTrue(notes.get("elementary"))
        self.assertTrue(notes.get("intermediate"))
        self.assertTrue(notes.get("advanced"))
        merged = " ".join(
            [
                str(notes.get("elementary") or ""),
                str(notes.get("intermediate") or ""),
                str(notes.get("advanced") or ""),
            ]
        ).casefold()
        self.assertIn("subject", merged)
        self.assertIn("predicate", merged)
        self.assertNotIn(sentence.casefold(), merged)

    def test_build_sentence_notes_for_phrasal_verbs(self):
        sentence = "She looked after him and turned down the offer."
        notes = build_sentence_notes(sentence)

        self.assertIsInstance(notes, dict)
        self.assertIn("subject", str(notes.get("intermediate") or "").casefold())
        self.assertIn("predicate", str(notes.get("intermediate") or "").casefold())


if __name__ == "__main__":
    unittest.main()
