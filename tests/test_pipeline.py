import unittest

from ela_pipeline.inference.run import run_pipeline


class PipelineTests(unittest.TestCase):
    def test_pipeline_without_generator(self):
        out = run_pipeline("She should have trusted her instincts before making the decision.", model_dir=None)
        self.assertIsInstance(out, dict)
        key = next(iter(out))
        self.assertEqual(out[key]["type"], "Sentence")

    def test_pipeline_disallows_one_word_phrases(self):
        out = run_pipeline("I run.", model_dir=None)
        key = next(iter(out))
        sentence = out[key]
        for phrase in sentence.get("linguistic_elements", []):
            self.assertGreaterEqual(len(phrase.get("linguistic_elements", [])), 2)


if __name__ == "__main__":
    unittest.main()
