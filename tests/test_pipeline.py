import unittest

from ela_pipeline.annotate.local_generator import LocalT5Annotator
from ela_pipeline.inference.run import run_pipeline
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.tam.rules import apply_tam


class PipelineTests(unittest.TestCase):
    def test_backoff_flag_added_for_non_l1_levels(self):
        flags = LocalT5Annotator._with_backoff_flag(
            ["template_selected", "rule_used"],
            {"level": "L2_DROP_TAM"},
        )
        self.assertIn("backoff_used", flags)

        flags_l1 = LocalT5Annotator._with_backoff_flag(
            ["template_selected", "rule_used"],
            {"level": "L1_EXACT"},
        )
        self.assertNotIn("backoff_used", flags_l1)

    def test_sentence_backoff_summary_fields(self):
        text = "She should have trusted her instincts before making the decision."
        nlp = load_nlp("en_core_web_sm")
        doc = build_skeleton(text, nlp)
        apply_tam(doc, nlp)

        annotator = LocalT5Annotator(model_dir=".", note_mode="template_only", backoff_debug_summary=True)
        annotator.annotate(doc)

        sentence = doc[next(iter(doc))]
        self.assertIsInstance(sentence.get("backoff_nodes_count"), int)
        self.assertIsInstance(sentence.get("backoff_leaf_nodes_count"), int)
        self.assertGreaterEqual(sentence.get("backoff_nodes_count"), 1)
        self.assertLessEqual(sentence.get("backoff_leaf_nodes_count"), sentence.get("backoff_nodes_count"))
        summary = sentence.get("backoff_summary")
        self.assertIsInstance(summary, dict)
        self.assertIsInstance(summary.get("nodes"), list)
        self.assertIsInstance(summary.get("leaf_nodes"), list)
        self.assertIsInstance(summary.get("reasons"), list)

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
                    self.assertTrue(word[field] is None or isinstance(word[field], str))
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

    def test_pipeline_marks_duplicate_spans_with_ref_node_id(self):
        out = run_pipeline(
            "She should have trusted her instincts before making the decision.",
            model_dir=None,
            validation_mode="v2_strict",
        )
        sentence = out[next(iter(out))]

        words_by_id = {}
        for phrase in sentence.get("linguistic_elements", []):
            for word in phrase.get("linguistic_elements", []):
                words_by_id[word.get("node_id")] = word

        ref_words = [w for w in words_by_id.values() if isinstance(w.get("ref_node_id"), str)]
        self.assertTrue(ref_words)
        for word in ref_words:
            ref_id = word["ref_node_id"]
            self.assertIn(ref_id, words_by_id)
            canonical = words_by_id[ref_id]
            self.assertEqual(word.get("content"), canonical.get("content"))
            self.assertEqual(word.get("source_span"), canonical.get("source_span"))

    def test_regression_had_vbn_vs_should_have_vbn(self):
        modal_out = run_pipeline(
            "She should have trusted her instincts.",
            model_dir=None,
            validation_mode="v2_strict",
        )
        modal_sentence = modal_out[next(iter(modal_out))]
        self.assertEqual(modal_sentence.get("tam_construction"), "modal_perfect")
        self.assertEqual(modal_sentence.get("tense"), None)
        self.assertEqual(modal_sentence.get("aspect"), "perfect")
        self.assertEqual(modal_sentence.get("mood"), "modal")

        modal_phrase = next(
            (p for p in modal_sentence.get("linguistic_elements", []) if p.get("tam_construction") == "modal_perfect"),
            None,
        )
        self.assertIsNotNone(modal_phrase)
        should_word = next(
            (w for w in modal_phrase.get("linguistic_elements", []) if w.get("content", "").lower() == "should"),
            None,
        )
        self.assertIsNotNone(should_word)
        self.assertEqual(should_word.get("mood"), "modal")

        past_out = run_pipeline(
            "She had trusted her instincts.",
            model_dir=None,
            validation_mode="v2_strict",
        )
        past_sentence = past_out[next(iter(past_out))]
        self.assertEqual(past_sentence.get("tam_construction"), "past_perfect")
        self.assertEqual(past_sentence.get("tense"), "past perfect")
        self.assertEqual(past_sentence.get("aspect"), "perfect")
        self.assertEqual(past_sentence.get("mood"), "indicative")


if __name__ == "__main__":
    unittest.main()
