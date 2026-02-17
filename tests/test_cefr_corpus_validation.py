import unittest

from ela_pipeline.corpus import validate_cefr_corpus


class CEFRCorpusValidationTests(unittest.TestCase):
    def test_accepts_valid_sentence_phrase_word_tree(self):
        payload = [
            {
                "type": "Sentence",
                "input": "She trusted her instincts.",
                "cefr_level": "B1",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "input": "trusted her instincts",
                        "cefr_level": "B1",
                        "linguistic_elements": [
                            {"type": "Word", "input": "trusted", "cefr_level": "A2", "linguistic_elements": []},
                        ],
                    }
                ],
            }
        ]
        issues = validate_cefr_corpus(payload)
        self.assertEqual(issues, [])

    def test_rejects_missing_and_invalid_cefr_levels(self):
        payload = [
            {
                "type": "Sentence",
                "input": "Sample.",
                "cefr_level": "B3",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "input": "Sample phrase",
                        "linguistic_elements": [
                            {"type": "Word", "input": "Sample", "cefr_level": "A1"},
                        ],
                    }
                ],
            }
        ]
        issues = validate_cefr_corpus(payload)
        self.assertGreaterEqual(len(issues), 2)
        self.assertTrue(any("invalid cefr_level" in issue.message for issue in issues))
        self.assertTrue(any("missing cefr_level" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
