import unittest

from ela_pipeline.dataset.build_dataset import (
    balance_rows_by_level_tam,
    dedup_and_cap_rows,
    detect_dataset_schema,
    evaluate_quality_gates,
    iter_examples,
)


class BuildDatasetTests(unittest.TestCase):
    def test_iter_examples_uses_only_model_notes(self):
        item = {
            "input": "She should have trusted her instincts.",
            "features": {"pos": ["PRON", "AUX", "AUX", "VERB"], "dep": ["nsubj", "aux", "aux", "ROOT"]},
            "targets": {
                "notes": [
                    {"text": "Fallback sentence note", "source": "fallback"},
                    {"text": "Model sentence note", "source": "model"},
                ],
                "tam_construction": "modal_perfect",
            },
            "linguistic_elements": [
                {
                    "type": "Phrase",
                    "input": "should have trusted",
                    "features": {"pos": ["AUX", "AUX", "VERB"], "dep": ["aux", "aux", "ROOT"]},
                    "targets": {
                        "notes": [
                            {"text": "Rule phrase note", "source": "rule"},
                            {"text": "Model phrase note", "source": "model"},
                        ],
                        "tam_construction": "modal_perfect",
                    },
                    "linguistic_elements": [
                        {
                            "type": "Word",
                            "input": "should",
                            "features": {
                                "pos": ["AUX"],
                                "tag": ["MD"],
                                "dep": ["aux"],
                                "morph": ["VerbForm=Fin"],
                            },
                            "targets": {
                                "notes": [{"text": "Model word note", "source": "model"}],
                                "tam_construction": "modal",
                            },
                        },
                        {
                            "type": "Word",
                            "input": "trusted",
                            "features": {
                                "pos": ["VERB"],
                                "tag": ["VBN"],
                                "dep": ["ROOT"],
                                "morph": ["VerbForm=Part|Tense=Past"],
                            },
                            "targets": {"notes": [{"text": "Fallback word note", "source": "fallback"}]},
                        },
                    ],
                }
            ],
        }

        rows = list(iter_examples(item))
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertIn("prompt_template_version", row)
            self.assertEqual(row["prompt_template_version"], "v1")
            self.assertIn("template_version: v1", row["input"])
        targets = {row["target"] for row in rows}
        self.assertIn("Model sentence note", targets)
        self.assertIn("Model phrase note", targets)
        self.assertIn("Model word note", targets)
        self.assertNotIn("Fallback sentence note", targets)
        self.assertNotIn("Fallback word note", targets)
        tam_by_target = {row["target"]: row["tam_bucket"] for row in rows}
        self.assertEqual(tam_by_target["Model sentence note"], "modal_perfect")
        self.assertEqual(tam_by_target["Model phrase note"], "modal_perfect")
        self.assertEqual(tam_by_target["Model word note"], "modal")

    def test_iter_examples_supports_legacy_linguistic_notes_schema(self):
        item = {
            "input": "Legacy sentence",
            "features": {"pos": [], "dep": []},
            "targets": {"linguistic_notes": "Legacy note"},
            "linguistic_elements": [],
        }

        rows = list(iter_examples(item))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], "Legacy note")
        self.assertEqual(rows[0]["level"], "Sentence")

    def test_iter_examples_excludes_telemetry_like_note_text(self):
        item = {
            "input": "Telemetry sentence",
            "features": {"pos": [], "dep": []},
            "targets": {
                "notes": [
                    {
                        "text": "quality_flags=['fallback_used']; reason_codes=['MODEL_OUTPUT_LOW_QUALITY']",
                        "source": "model",
                    }
                ]
            },
            "linguistic_elements": [],
        }

        rows = list(iter_examples(item))
        self.assertEqual(rows, [])

    def test_iter_examples_excludes_low_quality_template_style(self):
        item = {
            "input": "Template sentence",
            "features": {"pos": [], "dep": []},
            "targets": {
                "notes": [
                    {
                        "text": "Node content. Part of speech.",
                        "source": "model",
                    }
                ]
            },
            "linguistic_elements": [],
        }

        rows = list(iter_examples(item))
        self.assertEqual(rows, [])

    def test_iter_examples_excludes_targets_longer_than_two_sentences(self):
        item = {
            "input": "Long sentence",
            "features": {"pos": [], "dep": []},
            "targets": {
                "notes": [
                    {
                        "text": "This note has one sentence. Here is second. And a third.",
                        "source": "model",
                    }
                ]
            },
            "linguistic_elements": [],
        }

        rows = list(iter_examples(item))
        self.assertEqual(rows, [])

    def test_balance_rows_by_level_tam_balances_each_level(self):
        rows = [
            {"input": "a", "target": "t1", "level": "Word", "tam_bucket": "none"},
            {"input": "b", "target": "t2", "level": "Word", "tam_bucket": "none"},
            {"input": "c", "target": "t3", "level": "Word", "tam_bucket": "none"},
            {"input": "d", "target": "t4", "level": "Word", "tam_bucket": "modal_perfect"},
            {"input": "e", "target": "t5", "level": "Phrase", "tam_bucket": "none"},
            {"input": "f", "target": "t6", "level": "Phrase", "tam_bucket": "past_perfect"},
            {"input": "g", "target": "t7", "level": "Sentence", "tam_bucket": "none"},
        ]

        balanced = balance_rows_by_level_tam(rows, seed=42)
        word_none = [r for r in balanced if r["level"] == "Word" and r["tam_bucket"] == "none"]
        word_modal = [r for r in balanced if r["level"] == "Word" and r["tam_bucket"] == "modal_perfect"]
        phrase_none = [r for r in balanced if r["level"] == "Phrase" and r["tam_bucket"] == "none"]
        phrase_past = [r for r in balanced if r["level"] == "Phrase" and r["tam_bucket"] == "past_perfect"]
        sentence_none = [r for r in balanced if r["level"] == "Sentence" and r["tam_bucket"] == "none"]

        self.assertEqual(len(word_none), 1)
        self.assertEqual(len(word_modal), 1)
        self.assertEqual(len(phrase_none), 1)
        self.assertEqual(len(phrase_past), 1)
        self.assertEqual(len(sentence_none), 1)

    def test_dedup_and_cap_rows_limits_repeated_targets(self):
        rows = [
            {"input": "i1", "target": "A target", "level": "Word", "tam_bucket": "none"},
            {"input": "i2", "target": "A target", "level": "Word", "tam_bucket": "none"},
            {"input": "i3", "target": "A target", "level": "Word", "tam_bucket": "none"},
            {"input": "i4", "target": "B target", "level": "Word", "tam_bucket": "none"},
        ]
        out, report = dedup_and_cap_rows(rows, max_per_target=2, dedup_exact_input_target=False)
        self.assertEqual(len(out), 3)
        self.assertEqual(report["skipped_by_target_cap"], 1)

    def test_detect_dataset_schema_legacy(self):
        raw = [
            {
                "input": "Legacy sentence",
                "targets": {"linguistic_notes": "Legacy note"},
                "linguistic_elements": [],
            }
        ]
        report = detect_dataset_schema(raw)
        self.assertEqual(report["detected_schema"], "legacy_linguistic_notes")

    def test_iter_examples_reference_templates_mode(self):
        item = {
            "type": "Sentence",
            "input": "The team works in the office.",
            "features": {"pos": ["DET", "NOUN", "VERB", "ADP", "DET", "NOUN"], "dep": ["det", "nsubj", "ROOT"]},
            "targets": {},
            "linguistic_elements": [
                {
                    "type": "Phrase",
                    "input": "in the office",
                    "features": {"pos": ["ADP", "DET", "NOUN"], "dep": ["prep"]},
                    "targets": {},
                    "linguistic_elements": [
                        {
                            "type": "Word",
                            "input": "office",
                            "features": {"pos": ["NOUN"], "dep": ["pobj"], "tag": ["NN"], "morph": ["Number=Sing"]},
                            "targets": {},
                        }
                    ],
                }
            ],
        }
        rows = list(iter_examples(item, use_reference_templates=True))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["target"] for row in rows))
        self.assertTrue(any("prepositional phrase" in row["target"] for row in rows if row["level"] == "Phrase"))

    def test_iter_examples_template_id_mode(self):
        item = {
            "type": "Sentence",
            "input": "She should have trusted her instincts before making the decision.",
            "features": {"pos": ["PRON", "AUX", "AUX", "VERB"], "dep": ["nsubj", "aux", "aux", "ROOT"]},
            "targets": {
                "notes": [{"text": "Model sentence note", "source": "model"}],
                "tam_construction": "modal_perfect",
            },
            "linguistic_elements": [
                {
                    "type": "Phrase",
                    "input": "before making the decision",
                    "features": {
                        "pos": ["ADP", "VERB", "DET", "NOUN"],
                        "dep": ["prep", "pcomp", "det", "dobj"],
                        "tag": ["IN", "VBG", "DT", "NN"],
                    },
                    "targets": {"notes": [{"text": "Model phrase note", "source": "model"}]},
                    "linguistic_elements": [
                        {
                            "type": "Word",
                            "input": "before",
                            "features": {"pos": ["ADP"], "dep": ["prep"], "tag": ["IN"], "morph": []},
                            "targets": {"notes": [{"text": "Model word note", "source": "model"}]},
                        }
                    ],
                }
            ],
        }
        rows = list(iter_examples(item, use_template_id_targets=True))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all("|" in row["target"] for row in rows))
        self.assertTrue(any(row["target"].startswith("SENTENCE_FINITE_CLAUSE|") for row in rows))
        self.assertTrue(any(row["target"].startswith("PP_TIME_BEFORE_ING|") for row in rows))
        self.assertTrue(any(row["target"].startswith("WORD_PREPOSITION|") for row in rows))

    def test_template_id_mode_has_priority_over_reference_templates(self):
        item = {
            "type": "Sentence",
            "input": "The team works in the office.",
            "features": {"pos": ["DET", "NOUN", "VERB"], "dep": ["det", "nsubj", "ROOT"]},
            "targets": {
                "notes": [{"text": "Model sentence note", "source": "model"}],
            },
            "linguistic_elements": [],
        }
        rows = list(iter_examples(item, use_reference_templates=True, use_template_id_targets=True))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["target"].startswith("SENTENCE_FINITE_CLAUSE|"))

    def test_quality_gates_pass_for_good_distribution(self):
        failures = evaluate_quality_gates(
            target_stats_after_balance={
                "total": 100,
                "unique_targets": 40,
                "top_repeated_targets": [{"target": "a", "count": 20}],
            },
            template_id_distribution_after_balance={"SENTENCE_FINITE_CLAUSE": 20, "WORD_NOUN_COMMON": 30, "none": 0},
            min_unique_targets=30,
            max_top1_share=0.25,
            min_active_template_ids=2,
        )
        self.assertEqual(failures, [])

    def test_quality_gates_fail_for_collapsed_distribution(self):
        failures = evaluate_quality_gates(
            target_stats_after_balance={
                "total": 100,
                "unique_targets": 5,
                "top_repeated_targets": [{"target": "a", "count": 80}],
            },
            template_id_distribution_after_balance={"SENTENCE_FINITE_CLAUSE": 1, "none": 99},
            min_unique_targets=30,
            max_top1_share=0.5,
            min_active_template_ids=2,
        )
        self.assertEqual(len(failures), 3)
        self.assertTrue(any("min_unique_targets violated" in f for f in failures))
        self.assertTrue(any("max_top1_share violated" in f for f in failures))
        self.assertTrue(any("min_active_template_ids violated" in f for f in failures))


if __name__ == "__main__":
    unittest.main()
