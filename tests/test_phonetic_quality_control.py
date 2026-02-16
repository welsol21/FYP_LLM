import unittest

from ela_pipeline.inference.phonetic_quality_control import _extract_phonetic_probe_stats


class PhoneticQualityControlTests(unittest.TestCase):
    def test_extract_phonetic_probe_stats_counts_node_coverage(self):
        result = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "phonetic": {"uk": "ʃi", "us": "ʃi"},
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "phonetic": {"uk": "t", "us": "t"},
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "trusted",
                                "phonetic": {"uk": "t", "us": "t"},
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "him",
                                "phonetic": {"uk": "", "us": "h"},
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }
        stats = _extract_phonetic_probe_stats(result)
        self.assertEqual(stats["nodes"], 4)
        self.assertEqual(stats["valid_node_phonetics"], 2)
        self.assertEqual(stats["invalid_phonetic_nodes"], 1)
        self.assertEqual(stats["missing_phonetic_nodes"], 0)
        self.assertAlmostEqual(stats["node_phonetic_coverage"], 0.666667, places=6)

    def test_extract_phonetic_probe_stats_detects_missing_sentence_phonetic(self):
        result = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "linguistic_elements": [{"type": "Word", "content": "trusted", "linguistic_elements": []}],
                    }
                ],
            }
        }
        stats = _extract_phonetic_probe_stats(result)
        self.assertFalse(stats["sentence_phonetic_ok"])
        self.assertEqual(stats["missing_phonetic_nodes"], 2)


if __name__ == "__main__":
    unittest.main()
