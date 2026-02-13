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
        for field in ("aspect", "mood", "voice", "finiteness"):
            self.assertIn(field, sentence)
            self.assertIsInstance(sentence[field], str)
        self.assertIn("tam_construction", sentence)
        self.assertIsInstance(sentence["tam_construction"], str)
        self.assertEqual(sentence["source_span"]["start"], 0)
        self.assertEqual(sentence["source_span"]["end"], len(text))

        for phrase in sentence.get("linguistic_elements", []):
            self.assertEqual(phrase.get("parent_id"), sentence.get("node_id"))
            self.assertIn("source_span", phrase)
            self.assertIn("grammatical_role", phrase)
            self.assertIsInstance(phrase["grammatical_role"], str)
            for field in ("aspect", "mood", "voice", "finiteness"):
                self.assertIn(field, phrase)
                self.assertIsInstance(phrase[field], str)
            self.assertIn("tam_construction", phrase)
            self.assertIsInstance(phrase["tam_construction"], str)
            for word in phrase.get("linguistic_elements", []):
                self.assertEqual(word.get("parent_id"), phrase.get("node_id"))
                self.assertIn("source_span", word)
                self.assertIn("grammatical_role", word)
                self.assertIsInstance(word["grammatical_role"], str)
                for field in ("aspect", "mood", "voice", "finiteness"):
                    self.assertIn(field, word)
                    self.assertIsInstance(word[field], str)
                self.assertIn("dep_label", word)
                self.assertIsInstance(word["dep_label"], str)
                self.assertIn("head_id", word)
                self.assertTrue(word["head_id"] is None or isinstance(word["head_id"], str))
                self.assertIn("features", word)
                self.assertIsInstance(word["features"], dict)
                self.assertGreaterEqual(word["source_span"]["end"], word["source_span"]["start"])

    def test_pipeline_excludes_simple_determiner_noun_phrases(self):
        out = run_pipeline("She should have trusted her instincts before making the decision.", model_dir=None)
        key = next(iter(out))
        phrase_texts = [p.get("content") for p in out[key].get("linguistic_elements", [])]
        self.assertNotIn("the decision", phrase_texts)

    def test_pipeline_strict_mode_uses_real_null_for_tam_fields(self):
        out = run_pipeline(
            "She should have trusted her instincts before making the decision.",
            model_dir=None,
            validation_mode="v2_strict",
        )
        sentence = out[next(iter(out))]
        self.assertEqual(sentence.get("tam_construction"), "modal_perfect")

        def walk(node):
            for field in ("tense", "aspect", "mood", "voice", "finiteness"):
                self.assertNotEqual(node.get(field), "null")
            for child in node.get("linguistic_elements", []):
                walk(child)

        walk(sentence)

    def test_pipeline_v1_keeps_string_null_tam_values(self):
        out = run_pipeline(
            "She should have trusted her instincts before making the decision.",
            model_dir=None,
            validation_mode="v1",
        )
        sentence = out[next(iter(out))]
        has_string_null = False

        def walk(node):
            nonlocal has_string_null
            for field in ("tense", "aspect", "mood", "voice", "finiteness"):
                if node.get(field) == "null":
                    has_string_null = True
            for child in node.get("linguistic_elements", []):
                walk(child)

        walk(sentence)
        self.assertTrue(has_string_null)

    def test_pipeline_sets_modal_perfect_construction_label(self):
        out = run_pipeline(
            "She should have trusted her instincts before making the decision.",
            model_dir=None,
            validation_mode="v1",
        )
        sentence = out[next(iter(out))]
        self.assertEqual(sentence.get("tam_construction"), "modal_perfect")


if __name__ == "__main__":
    unittest.main()
