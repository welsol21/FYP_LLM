import unittest

from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.tam.rules import detect_tam


class TamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nlp = load_nlp()

    def test_past_passive(self):
        doc = self.nlp("The car was repaired yesterday.")
        sent = next(doc.sents)
        result = detect_tam(sent)
        self.assertEqual(result.tense, "past")
        self.assertEqual(result.voice, "passive")
        self.assertEqual(result.finiteness, "finite")

    def test_future_modal(self):
        doc = self.nlp("The report will be submitted tomorrow.")
        sent = next(doc.sents)
        result = detect_tam(sent)
        self.assertEqual(result.tense, "future")
        self.assertEqual(result.mood, "modal")

    def test_modal_perfect_not_labeled_as_past_perfect(self):
        doc = self.nlp("She should have trusted her instincts.")
        sent = next(doc.sents)
        result = detect_tam(sent)
        self.assertEqual(result.mood, "modal")
        self.assertEqual(result.aspect, "perfect")
        self.assertEqual(result.tense, "none")
        self.assertEqual(result.finiteness, "finite")


if __name__ == "__main__":
    unittest.main()
