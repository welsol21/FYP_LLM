import unittest
from unittest.mock import patch

from ela_pipeline.annotate.local_generator import LocalT5Annotator
from ela_pipeline.inference.run import (
    _attach_cefr,
    _attach_phonetic,
    _attach_synonyms,
    _attach_translation,
    _resolve_translation_model_name,
    run_pipeline,
)
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.tam.rules import apply_tam


class PipelineTests(unittest.TestCase):
    def test_translation_model_prefers_local_project_copy_for_default_hf_id(self):
        with patch("ela_pipeline.inference.run.os.path.isdir", return_value=True):
            resolved = _resolve_translation_model_name("facebook/m2m100_418M")
        self.assertEqual(resolved, "artifacts/models/m2m100_418M")

    def test_translation_model_keeps_explicit_custom_model_name(self):
        with patch("ela_pipeline.inference.run.os.path.isdir", return_value=True):
            resolved = _resolve_translation_model_name("custom-org/custom-model")
        self.assertEqual(resolved, "custom-org/custom-model")

    def test_attach_translation_enriches_sentence_and_nodes(self):
        doc = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "source_span": {"start": 0, "end": 15},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "source_span": {"start": 4, "end": 15},
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "trusted",
                                "source_span": {"start": 4, "end": 11},
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "trusted",
                                "source_span": {"start": 4, "end": 11},
                                "ref_node_id": "n_word_1",
                                "linguistic_elements": [],
                            }
                        ],
                    }
                ],
            }
        }
        doc["She trusted him."]["node_id"] = "n_sentence"
        phrase = doc["She trusted him."]["linguistic_elements"][0]
        phrase["node_id"] = "n_phrase_1"
        phrase["linguistic_elements"][0]["node_id"] = "n_word_1"
        phrase["linguistic_elements"][1]["node_id"] = "n_word_2"

        class FakeTranslator:
            model_name = "fake-model"
            calls = []

            @classmethod
            def translate_text(cls, text: str, source_lang: str, target_lang: str) -> str:
                cls.calls.append(text)
                return f"{target_lang}:{text}"

        _attach_translation(
            doc,
            translator=FakeTranslator(),
            source_lang="en",
            target_lang="ru",
            include_node_translations=True,
        )

        sentence = doc["She trusted him."]
        self.assertEqual(sentence["translation"]["text"], "ru:She trusted him.")
        phrase = sentence["linguistic_elements"][0]
        word = phrase["linguistic_elements"][0]
        dup_word = phrase["linguistic_elements"][1]
        self.assertEqual(phrase["translation"]["text"], "ru:trusted him")
        self.assertEqual(word["translation"]["text"], "ru:trusted")
        self.assertEqual(dup_word["translation"]["text"], "ru:trusted")

        self.assertEqual(
            FakeTranslator.calls.count("trusted"),
            1,
            msg=f"Expected one translation call for duplicate span/ref node, got {FakeTranslator.calls}",
        )

    def test_attach_translation_prefers_source_span_over_content(self):
        doc = {
            "He, however, left.": {
                "type": "Sentence",
                "node_id": "s1",
                "content": "He, however, left.",
                "source_span": {"start": 0, "end": 17},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "node_id": "p1",
                        "content": "however",
                        "source_span": {"start": 4, "end": 11},
                        "linguistic_elements": [],
                    }
                ],
            }
        }

        class CaptureTranslator:
            model_name = "fake-model"
            calls = []

            @classmethod
            def translate_text(cls, text: str, source_lang: str, target_lang: str) -> str:
                cls.calls.append(text)
                return text

        _attach_translation(doc, CaptureTranslator(), "en", "ru", include_node_translations=True)
        # sentence + phrase span
        self.assertIn("He, however, left.", CaptureTranslator.calls)
        self.assertIn("however", CaptureTranslator.calls)

    def test_attach_phonetic_enriches_sentence_and_nodes_with_dedup(self):
        doc = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "source_span": {"start": 0, "end": 15},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "source_span": {"start": 4, "end": 15},
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "trusted",
                                "source_span": {"start": 4, "end": 11},
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "trusted",
                                "source_span": {"start": 4, "end": 11},
                                "ref_node_id": "n_word_1",
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }
        doc["She trusted him."]["node_id"] = "n_sentence"
        phrase = doc["She trusted him."]["linguistic_elements"][0]
        phrase["node_id"] = "n_phrase_1"
        phrase["linguistic_elements"][0]["node_id"] = "n_word_1"
        phrase["linguistic_elements"][1]["node_id"] = "n_word_2"

        class FakePhonetic:
            calls = []

            @classmethod
            def transcribe_text(cls, text: str, accent: str) -> str:
                cls.calls.append((text, accent))
                return f"{accent}:{text}"

        _attach_phonetic(doc, transcriber=FakePhonetic(), include_node_phonetic=True)

        sentence = doc["She trusted him."]
        self.assertEqual(sentence["phonetic"]["uk"], "uk:She trusted him.")
        self.assertEqual(sentence["phonetic"]["us"], "us:She trusted him.")
        phrase = sentence["linguistic_elements"][0]
        word = phrase["linguistic_elements"][0]
        dup_word = phrase["linguistic_elements"][1]
        self.assertEqual(phrase["phonetic"]["uk"], "uk:trusted him")
        self.assertEqual(word["phonetic"]["uk"], "uk:trusted")
        self.assertEqual(dup_word["phonetic"]["uk"], "uk:trusted")
        trusted_uk_calls = [c for c in FakePhonetic.calls if c == ("trusted", "uk")]
        trusted_us_calls = [c for c in FakePhonetic.calls if c == ("trusted", "us")]
        self.assertEqual(len(trusted_uk_calls), 1)
        self.assertEqual(len(trusted_us_calls), 1)

    def test_attach_synonyms_enriches_sentence_and_nodes_with_dedup(self):
        doc = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "part_of_speech": "sentence",
                "source_span": {"start": 0, "end": 15},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "part_of_speech": "verb phrase",
                        "source_span": {"start": 4, "end": 15},
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "trusted",
                                "part_of_speech": "verb",
                                "features": {"verb_form": "part", "tense_feature": "past"},
                                "source_span": {"start": 4, "end": 11},
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "trusted",
                                "part_of_speech": "verb",
                                "features": {"verb_form": "part", "tense_feature": "past"},
                                "source_span": {"start": 4, "end": 11},
                                "ref_node_id": "n_word_1",
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }
        doc["She trusted him."]["node_id"] = "n_sentence"
        phrase = doc["She trusted him."]["linguistic_elements"][0]
        phrase["node_id"] = "n_phrase_1"
        phrase["linguistic_elements"][0]["node_id"] = "n_word_1"
        phrase["linguistic_elements"][1]["node_id"] = "n_word_2"

        class FakeSynonyms:
            calls = []

            @classmethod
            def get_synonyms(cls, text: str, pos: str | None, top_k: int) -> list[str]:
                cls.calls.append((text, pos, top_k))
                if text.strip().lower() == "trusted":
                    return ["trust", "swear", "rely", "bank", "believe"]
                return ["alt1", "alt2", "alt3"]

        _attach_synonyms(doc, provider=FakeSynonyms(), top_k=2, include_node_synonyms=True)

        sentence = doc["She trusted him."]
        self.assertEqual(sentence["synonyms"], ["alt1", "alt2"])
        phrase = sentence["linguistic_elements"][0]
        word = phrase["linguistic_elements"][0]
        dup_word = phrase["linguistic_elements"][1]
        self.assertEqual(word["synonyms"], ["sworn", "relied on"])
        self.assertEqual(dup_word["synonyms"], ["sworn", "relied on"])
        trusted_calls = [c for c in FakeSynonyms.calls if c[0] == "trusted"]
        self.assertEqual(len(trusted_calls), 1)

    def test_attach_cefr_enriches_sentence_and_nodes_with_dedup(self):
        doc = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "part_of_speech": "sentence",
                "source_span": {"start": 0, "end": 15},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "part_of_speech": "verb phrase",
                        "source_span": {"start": 4, "end": 15},
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "trusted",
                                "part_of_speech": "verb",
                                "source_span": {"start": 4, "end": 11},
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "trusted",
                                "part_of_speech": "verb",
                                "source_span": {"start": 4, "end": 11},
                                "ref_node_id": "n_word_1",
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }
        doc["She trusted him."]["node_id"] = "n_sentence"
        phrase = doc["She trusted him."]["linguistic_elements"][0]
        phrase["node_id"] = "n_phrase_1"
        phrase["linguistic_elements"][0]["node_id"] = "n_word_1"
        phrase["linguistic_elements"][1]["node_id"] = "n_word_2"

        class FakeCEFR:
            calls = []

            @classmethod
            def predict_level(cls, node: dict, source_text: str, sentence_text: str) -> str:
                cls.calls.append(source_text)
                if source_text == sentence_text:
                    return "B1"
                if source_text.strip().lower() == "trusted":
                    return "B2"
                return "A2"

        _attach_cefr(doc, predictor=FakeCEFR(), include_node_cefr=True)
        sentence = doc["She trusted him."]
        self.assertEqual(sentence["cefr_level"], "B1")
        phrase = sentence["linguistic_elements"][0]
        word = phrase["linguistic_elements"][0]
        dup_word = phrase["linguistic_elements"][1]
        self.assertEqual(phrase["cefr_level"], "A2")
        self.assertEqual(word["cefr_level"], "B1")
        self.assertEqual(dup_word["cefr_level"], "B1")
        self.assertEqual(FakeCEFR.calls.count("trusted"), 1)

    def test_attach_cefr_calibrates_service_and_content_words(self):
        doc = {
            "She should have trusted her instincts before making the decision.": {
                "type": "Sentence",
                "content": "She should have trusted her instincts before making the decision.",
                "part_of_speech": "sentence",
                "source_span": {"start": 0, "end": 65},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "before making the decision",
                        "part_of_speech": "prepositional phrase",
                        "source_span": {"start": 38, "end": 64},
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "the",
                                "part_of_speech": "article",
                                "source_span": {"start": 52, "end": 55},
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "decision",
                                "part_of_speech": "noun",
                                "source_span": {"start": 56, "end": 64},
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }

        class FakeCEFR:
            @staticmethod
            def predict_level(node: dict, source_text: str, sentence_text: str) -> str:
                if node.get("type") == "Sentence":
                    return "A2"
                if node.get("type") == "Phrase":
                    return "A2"
                if source_text.strip().lower() == "the":
                    return "C1"
                if source_text.strip().lower() == "decision":
                    return "C2"
                return "A2"

        _attach_cefr(doc, predictor=FakeCEFR(), include_node_cefr=True)
        sentence = doc["She should have trusted her instincts before making the decision."]
        phrase = sentence["linguistic_elements"][0]
        article = phrase["linguistic_elements"][0]
        noun = phrase["linguistic_elements"][1]

        self.assertEqual(article["cefr_level"], "A1")
        self.assertEqual(noun["cefr_level"], "B1")

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
        self.assertIsInstance(sentence.get("backoff_aggregate_nodes_count"), int)
        self.assertIsInstance(sentence.get("backoff_unique_spans_count"), int)
        self.assertIsInstance(sentence.get("backoff_in_subtree"), bool)
        self.assertTrue(sentence.get("backoff_in_subtree"))
        self.assertGreaterEqual(sentence.get("backoff_nodes_count"), 1)
        self.assertEqual(
            sentence.get("backoff_nodes_count"),
            sentence.get("backoff_leaf_nodes_count") + sentence.get("backoff_aggregate_nodes_count"),
        )
        self.assertLessEqual(sentence.get("backoff_leaf_nodes_count"), sentence.get("backoff_nodes_count"))
        self.assertLessEqual(sentence.get("backoff_unique_spans_count"), sentence.get("backoff_leaf_nodes_count"))
        summary = sentence.get("backoff_summary")
        self.assertIsInstance(summary, dict)
        self.assertIsInstance(summary.get("nodes"), list)
        self.assertIsInstance(summary.get("leaf_nodes"), list)
        self.assertIsInstance(summary.get("aggregate_nodes_count"), int)
        self.assertIsInstance(summary.get("unique_spans"), list)
        self.assertIsInstance(summary.get("reasons"), list)

        leaf_backoff_node = None
        for phrase in sentence.get("linguistic_elements", []):
            for word in phrase.get("linguistic_elements", []):
                if word.get("node_id") == "n9":
                    leaf_backoff_node = word
                    break
            if leaf_backoff_node:
                break
        self.assertIsNotNone(leaf_backoff_node)
        self.assertIn("backoff_used", leaf_backoff_node.get("quality_flags", []))
        self.assertIs(leaf_backoff_node.get("backoff_in_subtree"), False)

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

    def test_pipeline_keeps_linguistic_elements_as_last_field(self):
        out = run_pipeline(
            "She should have trusted her instincts before making the decision.",
            model_dir=None,
            validation_mode="v2_strict",
        )
        sentence = out[next(iter(out))]

        def walk(node: dict) -> None:
            if "linguistic_elements" in node:
                self.assertEqual(list(node.keys())[-1], "linguistic_elements")
            for child in node.get("linguistic_elements", []):
                walk(child)

        walk(sentence)

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
