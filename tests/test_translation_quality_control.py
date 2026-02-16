import unittest

from ela_pipeline.inference.translation_quality_control import _extract_translation_probe_stats


class TranslationQualityControlTests(unittest.TestCase):
    def test_extract_translation_probe_stats_counts_node_coverage(self):
        result = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "translation": {"source_lang": "en", "target_lang": "ru", "model": "m2m100", "text": "Она ему доверяла."},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "translation": {"source_lang": "en", "target_lang": "ru", "text": "доверяла ему"},
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "trusted",
                                "translation": {"source_lang": "en", "target_lang": "ru", "text": "доверяла"},
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "him",
                                "translation": {"source_lang": "en", "target_lang": "ru", "text": ""},
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }

        stats = _extract_translation_probe_stats(result, source_lang="en", target_lang="ru")
        self.assertEqual(stats["nodes"], 4)
        self.assertEqual(stats["translated_nodes"], 2)
        self.assertEqual(stats["empty_translation_nodes"], 1)
        self.assertEqual(stats["missing_translation_nodes"], 0)
        self.assertEqual(stats["lang_mismatch_nodes"], 0)
        self.assertAlmostEqual(stats["node_translation_coverage"], 0.666667, places=6)

    def test_extract_translation_probe_stats_detects_lang_mismatch_and_missing(self):
        result = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "translation": {"source_lang": "en", "target_lang": "ru", "model": "m2m100", "text": "Она ему доверяла."},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "translation": {"source_lang": "en", "target_lang": "de", "text": "vertraute ihm"},
                        "linguistic_elements": [
                            {"type": "Word", "content": "trusted", "linguistic_elements": []}
                        ],
                    }
                ],
            }
        }
        stats = _extract_translation_probe_stats(result, source_lang="en", target_lang="ru")
        self.assertEqual(stats["nodes"], 3)
        self.assertEqual(stats["lang_mismatch_nodes"], 1)
        self.assertEqual(stats["missing_translation_nodes"], 1)
        self.assertEqual(stats["translated_nodes"], 1)


if __name__ == "__main__":
    unittest.main()
