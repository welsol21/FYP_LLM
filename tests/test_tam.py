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

    def test_future_modal(self):
        doc = self.nlp("The report will be submitted tomorrow.")
        sent = next(doc.sents)
        result = detect_tam(sent)
        self.assertEqual(result.tense, "future")


if __name__ == "__main__":
    unittest.main()
