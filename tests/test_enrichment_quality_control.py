import unittest

from ela_pipeline.inference.enrichment_quality_control import _extract_enrichment_probe_stats


class EnrichmentQualityControlTests(unittest.TestCase):
    def test_extract_enrichment_probe_stats_reports_field_coverage(self):
        result = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "translation": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."},
                "phonetic": {"uk": "ʃi", "us": "ʃi"},
                "synonyms": ["depend", "rely on"],
                "cefr_level": "A2",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "translation": {"source_lang": "en", "target_lang": "ru", "text": "доверяла ему"},
                        "phonetic": {"uk": "t", "us": "t"},
                        "synonyms": ["trust"],
                        "cefr_level": "A2",
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "trusted",
                                "translation": {"source_lang": "en", "target_lang": "ru", "text": "доверяла"},
                                "phonetic": {"uk": "t", "us": "t"},
                                "synonyms": ["rely on", "bank on"],
                                "cefr_level": "B1",
                                "linguistic_elements": [],
                            },
                            {
                                "type": "Word",
                                "content": "him",
                                "translation": {"source_lang": "en", "target_lang": "ru", "text": ""},
                                "phonetic": {"uk": "h", "us": ""},
                                "synonyms": ["", "same", "same"],
                                "cefr_level": "B3",
                                "linguistic_elements": [],
                            },
                        ],
                    }
                ],
            }
        }
        stats = _extract_enrichment_probe_stats(result)

        self.assertEqual(stats["nodes"], 4)
        self.assertEqual(stats["non_sentence_nodes"], 3)
        self.assertTrue(stats["sentence"]["translation_ok"])
        self.assertTrue(stats["sentence"]["phonetic_ok"])
        self.assertTrue(stats["sentence"]["synonyms_ok"])
        self.assertTrue(stats["sentence"]["cefr_ok"])

        self.assertEqual(stats["node_fields"]["translation"]["valid"], 2)
        self.assertEqual(stats["node_fields"]["translation"]["invalid"], 1)
        self.assertEqual(stats["node_fields"]["phonetic"]["valid"], 2)
        self.assertEqual(stats["node_fields"]["phonetic"]["invalid"], 1)
        self.assertEqual(stats["node_fields"]["synonyms"]["valid"], 2)
        self.assertEqual(stats["node_fields"]["synonyms"]["invalid"], 1)
        self.assertEqual(stats["node_fields"]["cefr_level"]["valid"], 2)
        self.assertEqual(stats["node_fields"]["cefr_level"]["invalid"], 1)

    def test_synonyms_allows_empty_for_function_words_only(self):
        result = {
            "S.": {
                "type": "Sentence",
                "content": "S.",
                "translation": {"source_lang": "en", "target_lang": "ru", "text": "S"},
                "phonetic": {"uk": "s", "us": "s"},
                "synonyms": [],
                "cefr_level": "A1",
                "linguistic_elements": [
                    {
                        "type": "Word",
                        "content": "the",
                        "part_of_speech": "article",
                        "translation": {"source_lang": "en", "target_lang": "ru", "text": "the"},
                        "phonetic": {"uk": "ðə", "us": "ðə"},
                        "synonyms": [],
                        "cefr_level": "A1",
                        "linguistic_elements": [],
                    },
                    {
                        "type": "Word",
                        "content": "decision",
                        "part_of_speech": "noun",
                        "translation": {"source_lang": "en", "target_lang": "ru", "text": "decision"},
                        "phonetic": {"uk": "d", "us": "d"},
                        "synonyms": [],
                        "cefr_level": "B1",
                        "linguistic_elements": [],
                    },
                ],
            }
        }
        stats = _extract_enrichment_probe_stats(result)
        self.assertTrue(stats["sentence"]["synonyms_ok"])
        self.assertEqual(stats["node_fields"]["synonyms"]["valid"], 1)
        self.assertEqual(stats["node_fields"]["synonyms"]["invalid"], 1)
