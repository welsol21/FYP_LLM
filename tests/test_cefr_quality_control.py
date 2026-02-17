import unittest

from ela_pipeline.inference.cefr_quality_control import _extract_cefr_probe_stats


class CEFRQualityControlTests(unittest.TestCase):
    def test_extract_cefr_probe_stats_detects_anomalies(self):
        result = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "cefr_level": "A2",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "cefr_level": "A2",
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "the",
                                "part_of_speech": "article",
                                "cefr_level": "C1",
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "decision",
                                "part_of_speech": "noun",
                                "cefr_level": "C2",
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }
        stats = _extract_cefr_probe_stats(result)
        self.assertEqual(stats["nodes"], 4)
        self.assertEqual(stats["valid_levels"], 4)
        self.assertEqual(stats["invalid_levels"], 0)
        self.assertEqual(stats["function_word_over_b1"], 1)
        self.assertEqual(stats["over_sentence_plus_2"], 2)
        self.assertEqual(stats["over_parent_plus_1"], 2)
        self.assertGreater(stats["anomaly_rate"], 0.0)

    def test_extract_cefr_probe_stats_accepts_well_calibrated_tree(self):
        result = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "cefr_level": "A2",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "cefr_level": "A2",
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "the",
                                "part_of_speech": "article",
                                "cefr_level": "A1",
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "decision",
                                "part_of_speech": "noun",
                                "cefr_level": "B1",
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }
        stats = _extract_cefr_probe_stats(result)
        self.assertEqual(stats["function_word_over_b1"], 0)
        self.assertEqual(stats["over_sentence_plus_2"], 0)
        self.assertEqual(stats["over_parent_plus_1"], 0)
        self.assertEqual(stats["distribution"]["A1"], 1)
        self.assertEqual(stats["distribution"]["B1"], 1)
