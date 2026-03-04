import unittest

from ela_pipeline.classifier.oanc_parse import enrich_oanc_sentence_candidates


class OANCParseTests(unittest.TestCase):
    def test_enrich_oanc_sentence_candidates_adds_dependency_tokens_and_parser_provenance(self):
        rows = [
            {
                "text": "She should have trusted her instincts.",
                "provenance": {
                    "source": "OANC",
                    "member_path": "dummy.txt",
                    "genre_bucket": "written_1/journal",
                    "sentence_boundary_source": "oanc_s_xml",
                },
            }
        ]

        enriched = enrich_oanc_sentence_candidates(rows)

        self.assertEqual(len(enriched), 1)
        row = enriched[0]
        self.assertIn("tokens", row)
        self.assertTrue(len(row["tokens"]) > 0)
        self.assertTrue(any(tok["dep"] == "root" for tok in row["tokens"]))
        self.assertEqual(row["provenance"]["parser_engine"], "spacy")
        self.assertEqual(row["provenance"]["parser_model"], "en_core_web_sm")


if __name__ == "__main__":
    unittest.main()
