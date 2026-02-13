import unittest
from collections import Counter

from ela_pipeline.validation.build_hard_negatives import (
    _collect_rejected_candidates,
    build_hard_negative_payload,
)


class HardNegativeBuilderTests(unittest.TestCase):
    def test_collect_rejected_candidates_counts_across_nodes(self):
        payload = {
            "Sentence text.": {
                "type": "Sentence",
                "rejected_candidates": ["Bad template output", "Bad template output"],
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "rejected_candidates": ["Another bad output"],
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "rejected_candidates": ["Bad template output"],
                                "linguistic_elements": [],
                            }
                        ],
                    }
                ],
            }
        }
        counts = _collect_rejected_candidates(payload)
        self.assertEqual(counts["Bad template output"], 3)
        self.assertEqual(counts["Another bad output"], 1)

    def test_build_hard_negative_payload_filters_by_min_count(self):
        counts = Counter({"x": 1, "y": 4, "z": 2})
        payload = build_hard_negative_payload(counts=counts, min_count=2, max_items=10)
        texts = [item["text"] for item in payload["phrases"]]
        self.assertIn("y", texts)
        self.assertIn("z", texts)
        self.assertNotIn("x", texts)


if __name__ == "__main__":
    unittest.main()
