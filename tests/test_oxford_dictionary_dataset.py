import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.dataset.build_oxford_dictionary_dataset import (
    _pair_quality_ok,
    build_oxford_dictionary_dataset,
    infer_topic_key,
)
from ela_pipeline.dataset.template_topic_mapping import topic_to_template_id


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

    def test_topic_to_template_id_handles_normalized_oxford_topic_keys(self):
        self.assertEqual(topic_to_template_id("Sentence", "conditional_sentences"), "SENT_CONDITIONAL_GENERAL")
        self.assertEqual(topic_to_template_id("Sentence", "that_clause"), "SENT_NOUN_CLAUSE_THAT")
        self.assertEqual(topic_to_template_id("Phrase", "prepositions"), "PHRASE_PP_GENERAL")

    def test_pair_quality_ok_filters_metalinguistic_contexts(self):
        self.assertTrue(_pair_quality_ok("conditional_sentences", "If I see them, I will tell them"))
        self.assertTrue(_pair_quality_ok("that_clause", "That you believe such nonsense amazes me"))
        self.assertFalse(_pair_quality_ok("that_clause", "Although some *relative clauses begin with that"))
        self.assertFalse(_pair_quality_ok("prepositions", "There was at one time considerable prejudice against so-called"))


if __name__ == "__main__":
    unittest.main()
