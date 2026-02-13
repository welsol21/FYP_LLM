import unittest

from ela_pipeline.dataset.build_dataset import balance_rows_by_level_tam, iter_examples


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

    def test_iter_examples_ignores_legacy_linguistic_notes_without_source(self):
        item = {
            "input": "Legacy sentence",
            "features": {"pos": [], "dep": []},
            "targets": {"linguistic_notes": "Legacy note"},
            "linguistic_elements": [],
        }

        rows = list(iter_examples(item))
        self.assertEqual(rows, [])

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


if __name__ == "__main__":
    unittest.main()
