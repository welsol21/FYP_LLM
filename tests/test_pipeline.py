import unittest
from unittest.mock import MagicMock, patch

from ela_pipeline.annotate.local_generator import LocalT5Annotator
from ela_pipeline.inference.run import (
    _attach_cefr,
    _attach_phonetic,
    _resolve_translation_cache_ttl_seconds,
    _attach_synonyms,
    _attach_translation,
    _resolve_translation_model_name,
    run_pipeline,
)
from ela_pipeline.translate import InMemoryTranslationCache
from ela_pipeline.parse.spacy_parser import load_nlp
from ela_pipeline.skeleton.builder import build_skeleton
from ela_pipeline.tam.rules import apply_tam


class PipelineTests(unittest.TestCase):
    @staticmethod
    def _iter_descendants(node):
        for child in node.get("linguistic_elements", []):
            if not isinstance(child, dict):
                continue
            yield child
            yield from PipelineTests._iter_descendants(child)

    @staticmethod
    def _iter_by_type(node, expected_type: str):
        for item in PipelineTests._iter_descendants(node):
            if item.get("type") == expected_type:
                yield item

    @staticmethod
    def _iter_parent_child_pairs(node):
        for child in node.get("linguistic_elements", []):
            if not isinstance(child, dict):
                continue
            yield node, child
            yield from PipelineTests._iter_parent_child_pairs(child)

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
        self.assertEqual(sentence["translations"]["backend_m2m100"]["text"], "ru:She trusted him.")
        phrase = sentence["linguistic_elements"][0]
        word = phrase["linguistic_elements"][0]
        dup_word = phrase["linguistic_elements"][1]
        self.assertEqual(phrase["translations"]["backend_m2m100"]["text"], "ru:trusted him")
        self.assertEqual(word["translations"]["backend_m2m100"]["text"], "ru:trusted")
        self.assertEqual(dup_word["translations"]["backend_m2m100"]["text"], "ru:trusted")

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

    def test_attach_translation_uses_cache_across_runs(self):
        doc = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
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
                return f"{target_lang}:{text}"

        cache = InMemoryTranslationCache()
        _attach_translation(
            doc,
            translator=CaptureTranslator(),
            source_lang="en",
            target_lang="ru",
            include_node_translations=True,
            translation_cache=cache,
            translation_cache_ttl_seconds=60,
        )
        first_calls = len(CaptureTranslator.calls)
        _attach_translation(
            doc,
            translator=CaptureTranslator(),
            source_lang="en",
            target_lang="ru",
            include_node_translations=True,
            translation_cache=cache,
            translation_cache_ttl_seconds=60,
        )
        second_calls = len(CaptureTranslator.calls)
        self.assertEqual(first_calls, second_calls)

    def test_resolve_translation_cache_ttl_seconds_default_and_env(self):
        with patch("ela_pipeline.inference.run.os.getenv", return_value=""):
            self.assertEqual(_resolve_translation_cache_ttl_seconds(), 86400)
        with patch("ela_pipeline.inference.run.os.getenv", return_value="120"):
            self.assertEqual(_resolve_translation_cache_ttl_seconds(), 120)

    def test_resolve_translation_cache_ttl_seconds_rejects_non_positive(self):
        with patch("ela_pipeline.inference.run.os.getenv", return_value="0"):
            with self.assertRaises(ValueError):
                _resolve_translation_cache_ttl_seconds()

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

    def test_attach_phonetic_falls_back_to_source_text_when_transcriber_returns_empty(self):
        doc = {
            "Or, maybe.": {
                "type": "Sentence",
                "content": "Or, maybe.",
                "node_id": "n_sentence",
                "linguistic_elements": [
                    {
                        "type": "Word",
                        "content": ",",
                        "node_id": "n_comma",
                        "linguistic_elements": [],
                    }
                ],
            }
        }

        class EmptyPhonetic:
            @staticmethod
            def transcribe_text(text: str, accent: str) -> str:  # noqa: ARG004
                return ""

        _attach_phonetic(doc, transcriber=EmptyPhonetic(), include_node_phonetic=True)
        sentence = doc["Or, maybe."]
        comma = sentence["linguistic_elements"][0]
        self.assertEqual(sentence["phonetic"]["uk"], "Or, maybe.")
        self.assertEqual(sentence["phonetic"]["us"], "Or, maybe.")
        self.assertEqual(comma["phonetic"]["uk"], ",")
        self.assertEqual(comma["phonetic"]["us"], ",")

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

        leaf_backoff_node = next(
            (
                word
                for word in self._iter_by_type(sentence, "Word")
                if "backoff_used" in (word.get("quality_flags") or [])
            ),
            None,
        )
        self.assertIsNotNone(leaf_backoff_node)
        self.assertIn("backoff_used", leaf_backoff_node.get("quality_flags", []))
        self.assertIs(leaf_backoff_node.get("backoff_in_subtree"), False)

    def test_pipeline_without_generator(self):
        out = run_pipeline("She should have trusted her instincts before making the decision.", model_dir=None)
        self.assertIsInstance(out, dict)
        key = next(iter(out))
        self.assertEqual(out[key]["type"], "Sentence")

    @patch("ela_pipeline.annotate.local_generator.LocalT5Annotator.annotate")
    @patch("ela_pipeline.annotate.local_generator.LocalT5Annotator.__init__", return_value=None)
    def test_pipeline_sets_note_generator_version_when_annotator_enabled(self, _mock_init, mock_annotate):
        mock_annotate.return_value = None
        out = run_pipeline(
            "She trusted him.",
            model_dir="artifacts/models/fake_notes_model",
            note_mode="template_only",
        )
        sentence = out[next(iter(out))]
        self.assertEqual(sentence.get("note_generator_version"), "local_t5::template_only")
        for phrase in self._iter_by_type(sentence, "Phrase"):
            self.assertEqual(phrase.get("note_generator_version"), "local_t5::template_only")
        for word in self._iter_by_type(sentence, "Word"):
            self.assertEqual(word.get("note_generator_version"), "local_t5::template_only")

    def test_pipeline_attaches_grammar_classes(self):
        out = run_pipeline("She trusted him.", model_dir=None)
        sentence = out[next(iter(out))]
        sentence_classes = sentence.get("grammar_classes")
        self.assertIsInstance(sentence_classes, list)
        self.assertGreater(len(sentence_classes), 0)
        for cls in sentence_classes:
            self.assertIn("class_id", cls)
            self.assertIn("confidence", cls)
            self.assertFalse(str(cls["class_id"]).startswith(("type::", "pos::", "role::", "tense_table::", "tam::")))

    def test_skeleton_nests_inner_phrase_in_prepositional_phrase_instead_of_duplicate_siblings(self):
        out = run_pipeline("written by Andrei Sapkowski", model_dir=None)
        sentence = out[next(iter(out))]

        top_level_contents = [str(node.get("content") or "") for node in sentence.get("linguistic_elements", [])]
        self.assertIn("by Andrei Sapkowski", top_level_contents)
        self.assertNotIn("Andrei Sapkowski", top_level_contents)

        pp = next(
            node
            for node in sentence.get("linguistic_elements", [])
            if str(node.get("content") or "") == "by Andrei Sapkowski"
        )
        class_ids = {str(item.get("class_id")) for item in pp.get("grammar_classes", []) if isinstance(item, dict)}
        self.assertIn("prepositional_relation_phrase", class_ids)
        child_phrase_contents = [str(node.get("content") or "") for node in pp.get("linguistic_elements", []) if node.get("type") == "Phrase"]
        self.assertIn("Andrei Sapkowski", child_phrase_contents)

    def test_pipeline_attaches_pedagogical_modal_perfect_grammar_class(self):
        out = run_pipeline(
            "She should have trusted her instincts before making the decision.",
            model_dir=None,
            validation_mode="v2_strict",
        )
        sentence = out[next(iter(out))]
        classes = sentence.get("grammar_classes") or []
        class_ids = {str(item.get("class_id")) for item in classes if isinstance(item, dict)}
        self.assertIn("modal_perfect", class_ids)
        self.assertEqual(
            sentence.get("generated_notes", {}).get("intermediate_text"),
            "Explain how modal + have + past participle evaluates a past event.",
        )

    def test_pipeline_attaches_generated_notes_and_populates_linguistic_notes(self):
        out = run_pipeline("She trusted him.", model_dir=None)
        sentence = out[next(iter(out))]
        generated = sentence.get("generated_notes")
        blueprints = sentence.get("note_blueprints")
        self.assertIsInstance(generated, dict)
        self.assertIsInstance(blueprints, dict)
        self.assertTrue(generated.get("elementary_text"))
        self.assertTrue(generated.get("intermediate_text"))
        self.assertTrue(generated.get("advanced_text"))
        self.assertNotIn("pos::", str(generated.get("intermediate_text")))
        self.assertNotIn("type::", str(generated.get("intermediate_text")))
        self.assertNotIn("tam::", str(generated.get("intermediate_text")))
        self.assertNotIn("tense_table::", str(generated.get("intermediate_text")))
        self.assertEqual(blueprints, generated)
        notes = sentence.get("linguistic_notes")
        self.assertIsInstance(notes, list)
        self.assertGreater(len(notes), 0)

    def test_pipeline_controlled_mode_uses_classifier_blueprints_for_notes(self):
        out = run_pipeline(
            "She trusted him.",
            model_dir=None,
            note_mode="controlled",
        )
        sentence = out[next(iter(out))]
        generated = sentence.get("generated_notes")
        blueprints = sentence.get("note_blueprints")
        self.assertIsInstance(generated, dict)
        self.assertIsInstance(blueprints, dict)
        self.assertEqual(
            sentence.get("linguistic_notes"),
            [generated.get("intermediate_text")],
        )
        self.assertEqual(sentence.get("note_generator_version"), "controlled::classifier_blueprints")

    def test_pipeline_default_note_mode_is_controlled(self):
        out = run_pipeline("She trusted him.", model_dir=None)
        sentence = out[next(iter(out))]
        generated = sentence.get("generated_notes")
        self.assertIsInstance(generated, dict)
        self.assertEqual(
            sentence.get("linguistic_notes"),
            [generated.get("intermediate_text")],
        )

    def test_pipeline_skips_weak_phrase_candidates_and_generic_phrase_notes(self):
        out = run_pipeline("She came to him towards morning.", model_dir=None)
        sentence = out[next(iter(out))]
        top_level_phrases = [node for node in sentence.get("linguistic_elements", []) if node.get("type") == "Phrase"]
        self.assertEqual(len(top_level_phrases), 1)
        phrase_text = str(top_level_phrases[0].get("content") or "")
        self.assertTrue(phrase_text.startswith("came to him towards"))
        top_level_contents = [str(node.get("content") or "") for node in sentence.get("linguistic_elements", [])]
        self.assertNotIn("She", top_level_contents)
        self.assertNotIn("came", top_level_contents)
        self.assertNotIn("to him", top_level_contents)
        self.assertNotIn("towards morning", top_level_contents)

    def test_pipeline_leaves_unknown_phrase_without_generic_notes(self):
        out = run_pipeline("She entered through the chamber like a phantom.", model_dir=None)
        sentence = out[next(iter(out))]
        phrases = [
            node
            for node in sentence.get("linguistic_elements", [])
            if node.get("type") == "Phrase" and str(node.get("content") or "") in {"through the chamber", "like a phantom"}
        ]
        self.assertGreaterEqual(len(phrases), 1)
        for phrase in phrases:
            class_ids = {str(item.get("class_id")) for item in phrase.get("grammar_classes", []) if isinstance(item, dict)}
            self.assertIn("prepositional_relation_phrase", class_ids)
            notes = " ".join(phrase.get("linguistic_notes") or [])
            self.assertNotIn("Main grammar focus: phrase structure", notes)
            self.assertNotIn("This phrase is used as modifier", notes)

    @patch("ela_pipeline.annotate.controlled_renderer.ControlledT5NoteRenderer")
    @patch("ela_pipeline.annotate.local_generator.LocalT5Annotator.__init__", side_effect=AssertionError("must not be called"))
    def test_pipeline_controlled_mode_skips_legacy_t5_annotator(self, _mock_init, mock_renderer_cls):
        mock_renderer = MagicMock()
        mock_renderer.render_note.side_effect = lambda **kwargs: kwargs["blueprint_text"]
        mock_renderer_cls.return_value = mock_renderer
        out = run_pipeline(
            "She trusted him.",
            model_dir="artifacts/models/fake_notes_model",
            note_mode="controlled",
        )
        sentence = out[next(iter(out))]
        self.assertEqual(sentence.get("note_generator_version"), "controlled_t5::blueprint_rewrite")

    @patch("ela_pipeline.annotate.controlled_renderer.ControlledT5NoteRenderer")
    def test_pipeline_controlled_mode_rewrites_blueprints_with_t5(self, mock_renderer_cls):
        mock_renderer = MagicMock()

        def _render(**kwargs):
            return f"rendered::{kwargs['level']}::{kwargs['blueprint_text']}"

        mock_renderer.render_note.side_effect = _render
        mock_renderer_cls.return_value = mock_renderer

        out = run_pipeline(
            "She trusted him.",
            model_dir="artifacts/models/fake_notes_model",
            note_mode="controlled",
        )
        sentence = out[next(iter(out))]
        generated = sentence.get("generated_notes", {})
        blueprints = sentence.get("note_blueprints", {})
        self.assertTrue(str(generated.get("elementary_text")).startswith("rendered::elementary::"))
        self.assertTrue(str(generated.get("intermediate_text")).startswith("rendered::intermediate::"))
        self.assertTrue(str(generated.get("advanced_text")).startswith("rendered::advanced::"))
        self.assertFalse(str(blueprints.get("intermediate_text")).startswith("rendered::"))
        self.assertEqual(sentence.get("linguistic_notes"), [generated.get("intermediate_text")])

    @patch("ela_pipeline.classifier.deberta.DebertaProfileClassifier")
    def test_pipeline_uses_deberta_classifier_provider(self, mock_classifier_cls):
        fake_classifier = MagicMock()
        fake_classifier.classify_node.return_value = {
            "cefr_level": "B2",
        }
        mock_classifier_cls.return_value = fake_classifier

        out = run_pipeline(
            "She trusted him.",
            model_dir=None,
            note_mode="controlled",
            classifier_provider="deberta",
            classifier_model_path="/tmp/fake-deberta",
            classifier_device="cuda",
        )
        sentence = out[next(iter(out))]
        self.assertEqual(sentence.get("cefr_level"), "B2")
        self.assertIsInstance(sentence.get("grammar_classes"), list)
        self.assertGreater(len(sentence.get("grammar_classes")), 0)
        self.assertTrue(sentence.get("generated_notes", {}).get("intermediate_text"))
        self.assertEqual(sentence.get("linguistic_notes"), [sentence.get("generated_notes", {}).get("intermediate_text")])
        self.assertGreaterEqual(fake_classifier.classify_node.call_count, 1)

    @patch("ela_pipeline.classifier.tabular_cefr_predictor.TabularProfileClassifier")
    def test_pipeline_uses_tabular_classifier_provider(self, mock_classifier_cls):
        fake_classifier = MagicMock()
        fake_classifier.classify_node.return_value = {
            "cefr_level": "B1",
        }
        mock_classifier_cls.return_value = fake_classifier

        out = run_pipeline(
            "She trusted him.",
            model_dir=None,
            note_mode="controlled",
            classifier_provider="tabular",
            classifier_model_path="/tmp/fake-tabular",
        )
        sentence = out[next(iter(out))]
        self.assertEqual(sentence.get("cefr_level"), "B1")
        self.assertIsInstance(sentence.get("grammar_classes"), list)
        self.assertGreater(len(sentence.get("grammar_classes")), 0)
        self.assertTrue(sentence.get("generated_notes", {}).get("intermediate_text"))
        self.assertEqual(sentence.get("linguistic_notes"), [sentence.get("generated_notes", {}).get("intermediate_text")])
        self.assertGreaterEqual(fake_classifier.classify_node.call_count, 1)

    @patch("ela_pipeline.annotate.local_generator.LocalT5Annotator.annotate")
    @patch("ela_pipeline.annotate.local_generator.LocalT5Annotator.__init__", return_value=None)
    def test_t5_annotation_cannot_override_classifier_truth_fields(self, _mock_init, mock_annotate):
        def _tamper(doc):
            sentence = doc[next(iter(doc))]
            sentence["cefr_level"] = "C2"
            sentence["grammar_classes"] = [{"class_id": "tampered::from_t5", "confidence": 1.0}]
            sentence["generated_notes"] = {
                "elementary_text": "tampered",
                "intermediate_text": "tampered",
                "advanced_text": "tampered",
            }

        mock_annotate.side_effect = _tamper
        out = run_pipeline(
            "She trusted him.",
            model_dir="artifacts/models/fake_notes_model",
            note_mode="template_only",
            classifier_provider="rule",
            enable_cefr=True,
            cefr_provider="rule",
        )
        sentence = out[next(iter(out))]
        class_ids = {row["class_id"] for row in sentence.get("grammar_classes", []) if isinstance(row, dict)}
        self.assertNotIn("tampered::from_t5", class_ids)
        self.assertNotEqual(sentence.get("generated_notes", {}).get("intermediate_text"), "tampered")

    def test_pipeline_replaces_weak_one_word_phrases_with_sentence_words_fallback(self):
        out = run_pipeline("I run.", model_dir=None)
        key = next(iter(out))
        sentence = out[key]
        phrases = list(self._iter_by_type(sentence, "Phrase"))
        words = list(self._iter_by_type(sentence, "Word"))
        self.assertEqual(len(phrases), 0)
        self.assertGreaterEqual(len(words), 2)
        self.assertTrue(any(str(w.get("content") or "") == "I" for w in words))
        self.assertTrue(any(str(w.get("content") or "") == "run" for w in words))

    def test_pipeline_keeps_only_phrase_nodes_with_pedagogical_grammar_class(self):
        out = run_pipeline("She came to him towards morning.", model_dir=None)
        sentence = out[next(iter(out))]
        for phrase in self._iter_by_type(sentence, "Phrase"):
            self.assertGreater(len(phrase.get("grammar_classes") or []), 0)
            self.assertGreater(len(phrase.get("linguistic_notes") or []), 0)

    def test_pipeline_attaches_word_level_notes_for_pronouns(self):
        out = run_pipeline("She trusted him.", model_dir=None)
        sentence = out[next(iter(out))]
        pronoun = next(
            word
            for word in self._iter_by_type(sentence, "Word")
            if str(word.get("content") or "") == "him"
        )
        class_ids = {str(item.get("class_id")) for item in pronoun.get("grammar_classes", []) if isinstance(item, dict)}
        self.assertIn("pronoun_reference", class_ids)
        self.assertGreater(len(pronoun.get("linguistic_notes") or []), 0)

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

        for parent, child in self._iter_parent_child_pairs(sentence):
            self.assertEqual(child.get("parent_id"), parent.get("node_id"))
            self.assertIn("source_span", child)
            self.assertIn("grammatical_role", child)
            self.assertIsInstance(child["grammatical_role"], str)
            for field in ("aspect", "mood", "voice", "finiteness"):
                self.assertIn(field, child)
                self.assertTrue(child[field] is None or isinstance(child[field], str))
            self.assertGreaterEqual(child["source_span"]["end"], child["source_span"]["start"])
            if child.get("type") == "Phrase":
                self.assertIn("tam_construction", child)
                self.assertIsInstance(child["tam_construction"], str)
            if child.get("type") == "Word":
                self.assertIn("dep_label", child)
                self.assertIsInstance(child["dep_label"], str)
                self.assertIn("head_id", child)
                self.assertTrue(child["head_id"] is None or isinstance(child["head_id"], str))
                self.assertIn("features", child)
                self.assertIsInstance(child["features"], dict)

    def test_pipeline_excludes_simple_determiner_noun_phrases(self):
        out = run_pipeline("She should have trusted her instincts before making the decision.", model_dir=None)
        key = next(iter(out))
        phrase_texts = [p.get("content") for p in self._iter_by_type(out[key], "Phrase")]
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

        words_by_id = {word.get("node_id"): word for word in self._iter_by_type(sentence, "Word")}

        ref_words = [w for w in words_by_id.values() if isinstance(w.get("ref_node_id"), str)]
        for word in ref_words:
            ref_id = word["ref_node_id"]
            self.assertIn(ref_id, words_by_id)
            canonical = words_by_id[ref_id]
            self.assertEqual(word.get("content"), canonical.get("content"))
            self.assertEqual(word.get("source_span"), canonical.get("source_span"))

        sentence_children = [child for child in sentence.get("linguistic_elements", []) if isinstance(child, dict)]
        sibling_spans = [
            (
                int((child.get("source_span") or {}).get("start", -1)),
                int((child.get("source_span") or {}).get("end", -1)),
                str(child.get("content") or ""),
            )
            for child in sentence_children
        ]
        self.assertEqual(len(sibling_spans), len(set(sibling_spans)))

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

        modal_phrase = next((p for p in self._iter_by_type(modal_sentence, "Phrase") if p.get("tam_construction") == "modal_perfect"), None)
        self.assertIsNotNone(modal_phrase)
        should_word = next((w for w in self._iter_by_type(modal_phrase, "Word") if w.get("content", "").lower() == "should"), None)
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
