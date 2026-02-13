import unittest

from ela_pipeline.dataset.build_dataset import iter_examples


class BuildDatasetTests(unittest.TestCase):
    def test_iter_examples_uses_only_model_notes(self):
        item = {
            "input": "She should have trusted her instincts.",
            "features": {"pos": ["PRON", "AUX", "AUX", "VERB"], "dep": ["nsubj", "aux", "aux", "ROOT"]},
            "targets": {
                "notes": [
                    {"text": "Fallback sentence note", "source": "fallback"},
                    {"text": "Model sentence note", "source": "model"},
                ]
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
                        ]
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
                            "targets": {"notes": [{"text": "Model word note", "source": "model"}]},
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
        targets = {row["target"] for row in rows}
        self.assertIn("Model sentence note", targets)
        self.assertIn("Model phrase note", targets)
        self.assertIn("Model word note", targets)
        self.assertNotIn("Fallback sentence note", targets)
        self.assertNotIn("Fallback word note", targets)

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


if __name__ == "__main__":
    unittest.main()
