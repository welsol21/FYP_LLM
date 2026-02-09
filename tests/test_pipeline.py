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

    def test_pipeline_adds_node_metadata(self):
        text = "She should have trusted her instincts before making the decision."
        out = run_pipeline(text, model_dir=None)
        sentence = out[next(iter(out))]
        self.assertIn("node_id", sentence)
        self.assertIn("parent_id", sentence)
        self.assertIsNone(sentence["parent_id"])
        self.assertIn("source_span", sentence)
        self.assertIn("grammatical_role", sentence)
        self.assertIsInstance(sentence["grammatical_role"], str)
        self.assertEqual(sentence["source_span"]["start"], 0)
        self.assertEqual(sentence["source_span"]["end"], len(text))

        for phrase in sentence.get("linguistic_elements", []):
            self.assertEqual(phrase.get("parent_id"), sentence.get("node_id"))
            self.assertIn("source_span", phrase)
            self.assertIn("grammatical_role", phrase)
            self.assertIsInstance(phrase["grammatical_role"], str)
            for word in phrase.get("linguistic_elements", []):
                self.assertEqual(word.get("parent_id"), phrase.get("node_id"))
                self.assertIn("source_span", word)
                self.assertIn("grammatical_role", word)
                self.assertIsInstance(word["grammatical_role"], str)
                self.assertIn("dep_label", word)
                self.assertIsInstance(word["dep_label"], str)
                self.assertIn("head_id", word)
                self.assertTrue(word["head_id"] is None or isinstance(word["head_id"], str))
                self.assertGreaterEqual(word["source_span"]["end"], word["source_span"]["start"])


if __name__ == "__main__":
    unittest.main()
