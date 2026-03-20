import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.dataset.build_oxford_dictionary_dataset import build_oxford_dictionary_dataset, infer_topic_key


class OxfordDictionaryDatasetTests(unittest.TestCase):
    def test_infer_topic_key_maps_known_entry_terms(self):
        self.assertEqual(infer_topic_key("prepositional phrase", "A prepositional phrase modifies a clause."), "prepositional_phrases")
        self.assertEqual(infer_topic_key("question tag", "A question tag is added at the end."), "question_tags")

    def test_build_oxford_dictionary_dataset_emits_phrase_row_for_pp_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            pairs_path = Path(tmp) / "pairs.jsonl"
            pairs = [
                {
                    "source_path": "/tmp/book.pdf",
                    "entry_head": "prepositional phrase",
                    "notation_text": "A prepositional phrase adds location information.",
                    "context_text": "in the garden",
                    "pair_method": "line_block",
                }
            ]
            with pairs_path.open("w", encoding="utf-8") as handle:
                for row in pairs:
                    handle.write(json.dumps(row) + "\n")

            contract_rows, dataset_rows, report = build_oxford_dictionary_dataset(
                pairs_jsonl=str(pairs_path),
            )

        self.assertEqual(report["stats"]["contracts_built"], 1)
        self.assertTrue(contract_rows)
        self.assertEqual(report["stats"]["topic_mapped_rows"], 1)
        self.assertIsInstance(dataset_rows, list)


if __name__ == "__main__":
    unittest.main()
