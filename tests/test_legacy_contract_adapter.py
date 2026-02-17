import unittest

from ela_pipeline.adapters import adapt_legacy_contract_doc


class LegacyContractAdapterTests(unittest.TestCase):
    def test_adapts_linguistic_notes_and_cefr_aliases(self):
        legacy = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "tense": "null",
                "linguistic_notes": ["Legacy sentence note."],
                "sentence_cefr": "B1",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "linguistic_notes": ["Legacy phrase note."],
                        "phrase_cefr": "B1",
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "content": "trusted",
                                "word_cefr": "B1",
                                "linguistic_elements": [],
                            }
                        ],
                    }
                ],
            }
        }
        adapted = adapt_legacy_contract_doc(legacy)
        sent = adapted["She trusted him."]
        phrase = sent["linguistic_elements"][0]
        word = phrase["linguistic_elements"][0]

        self.assertIsNone(sent["tense"])
        self.assertEqual(sent["cefr_level"], "B1")
        self.assertEqual(phrase["cefr_level"], "B1")
        self.assertEqual(word["cefr_level"], "B1")

        self.assertEqual(sent["schema_version"], "v2")
        self.assertEqual(phrase["schema_version"], "v2")
        self.assertEqual(word["schema_version"], "v2")

        self.assertIn("notes", sent)
        self.assertEqual(sent["notes"][0]["source"], "legacy")
        self.assertIn("notes", phrase)
        self.assertEqual(phrase["notes"][0]["source"], "legacy")

    def test_adapts_missing_linguistic_elements_to_empty_list(self):
        legacy = {
            "Hello.": {
                "type": "Sentence",
                "content": "Hello.",
            }
        }
        adapted = adapt_legacy_contract_doc(legacy)
        sent = adapted["Hello."]
        self.assertEqual(sent["linguistic_elements"], [])
        self.assertEqual(sent["schema_version"], "v2")


if __name__ == "__main__":
    unittest.main()
