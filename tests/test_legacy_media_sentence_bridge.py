import unittest

from ela_pipeline.client_storage import build_sentence_hash
from ela_pipeline.legacy_bridge import build_contract_rows_from_media_sentences


class LegacyMediaSentenceBridgeTests(unittest.TestCase):
    def test_build_contract_rows_from_media_sentences(self):
        media_rows = [
            {"sentence_idx": 0, "text_eng": "She trusted him."},
            {"sentence_idx": 1, "sentence_text": "Before making the decision."},
        ]

        def provider(sentence_text: str, sentence_idx: int):
            return {
                "sentence_text": sentence_text,
                "sentence_hash": build_sentence_hash(sentence_text, sentence_idx),
                "sentence_node": {
                    "type": "Sentence",
                    "node_id": f"s{sentence_idx}",
                    "content": sentence_text,
                    "linguistic_elements": [],
                },
            }

        rows = build_contract_rows_from_media_sentences(
            media_rows,
            sentence_contract_provider=provider,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["sentence_idx"], 0)
        self.assertEqual(rows[0]["sentence_node"]["node_id"], "s0")
        self.assertEqual(rows[1]["sentence_idx"], 1)
        self.assertEqual(rows[1]["sentence_node"]["content"], "Before making the decision.")


if __name__ == "__main__":
    unittest.main()

