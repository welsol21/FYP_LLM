import json
import tempfile
import unittest
from pathlib import Path

from ela_pipeline.dataset.export_contract_placeholder_dataset import export_contract_placeholder_dataset


class ExportContractPlaceholderDatasetTests(unittest.TestCase):
    def test_export_contract_placeholder_dataset_flattens_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "rows.jsonl"
            rows = [
                {
                    "row_id": "r1",
                    "source_path": "/tmp/book.pdf",
                    "entry_head": "prepositional phrase",
                    "topic_key": "prepositional_phrases",
                    "node_level": "Phrase",
                    "context_text": "in the garden",
                    "notation_text": "A prepositional phrase adds location information.",
                    "pair_method": "line_block",
                    "matched_template_id": "PHRASE_PP_LOCATION",
                    "book_template_id": "PHRASE_PP_GENERAL",
                    "contract_template_payload": {
                        "note_template_version": "v1",
                        "template_id": "PHRASE_PP_LOCATION",
                        "template_text": "This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses location or spatial position.",
                        "allowed_slots": ["PART_OF_SPEECH", "GRAMMATICAL_ROLE"],
                        "slot_values": {
                            "PART_OF_SPEECH": "prepositional phrase",
                            "GRAMMATICAL_ROLE": "modifier",
                        },
                        "rendered_note_text": "This prepositional phrase works as a modifier and expresses location or spatial position.",
                        "render_status": "template_rendered",
                    },
                }
            ]
            with input_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            exported, report = export_contract_placeholder_dataset(input_jsonl=str(input_path))

        self.assertEqual(report["rows_total"], 1)
        self.assertEqual(report["slot_bearing_rows"], 1)
        self.assertEqual(exported[0]["template_id"], "PHRASE_PP_LOCATION")
        self.assertEqual(exported[0]["allowed_slots"], ["PART_OF_SPEECH", "GRAMMATICAL_ROLE"])
        self.assertEqual(exported[0]["slot_values"]["PART_OF_SPEECH"], "prepositional phrase")


if __name__ == "__main__":
    unittest.main()
