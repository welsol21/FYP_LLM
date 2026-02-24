import unittest

from ela_pipeline.classifier.kb_enrichment import enrich_kb_example, enrich_kb_examples
from ela_pipeline.parse.spacy_parser import load_nlp


class ClassifierKBEnrichmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nlp = load_nlp("en_core_web_sm")

    def test_enrich_kb_example_includes_token_and_dependency_fields(self):
        out = enrich_kb_example("She should have trusted him.", nlp=self.nlp)
        self.assertIn("tokens", out)
        self.assertGreater(len(out["tokens"]), 0)
        first = out["tokens"][0]
        for key in ("text", "lemma", "pos", "tag", "dep", "head_text", "head_i", "i", "morph"):
            self.assertIn(key, first)

    def test_enrich_kb_example_derives_tam_signature(self):
        out = enrich_kb_example("She should have trusted him.", nlp=self.nlp)
        derived = out["derived_features"]
        self.assertIn("token_count", derived)
        self.assertIn("has_modal_auxiliary", derived)
        self.assertIn("has_perfect_auxiliary", derived)
        self.assertIn("tam_signature", derived)
        self.assertEqual(derived["tam_signature"], "modal_perfect_hint")

    def test_enrich_kb_examples_batch(self):
        rows = enrich_kb_examples(["I run.", "She should have trusted him."], nlp=self.nlp)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
