import unittest

from ela_pipeline.classifier.build_template_classifier_dataset import (
    _make_phrase_row,
    _make_sentence_row,
)


class BuildTemplateClassifierDatasetTests(unittest.TestCase):
    def test_sentence_row_uses_contract_classifier_prompt(self):
        row = {
            "sentence_text": "You called him, didn't you?",
            "source_document": {"id": "doc-1", "source_name": "book"},
            "projection_version": "book_projection_v16_slot_normalized",
            "sentence_family_alignment": {},
        }
        candidate = {"source_book": "egiu_2019", "topic": "question tag"}

        built = _make_sentence_row(row, candidate, "SENT_QUESTION_TAG")
        self.assertEqual(built["prompt_template_version"], "contract_template_classifier_v1")
        self.assertIn("predict_template_id_from_contract_context", built["input"])
        self.assertIn('"prompt_template_version": "contract_template_classifier_v1"', built["input"])
        self.assertNotIn('"template_id": "SENT_QUESTION_TAG"', built["input"])

    def test_phrase_row_uses_contract_classifier_prompt(self):
        row = {
            "sentence_text": "American forces killed Shaikh Abdullah al-Ani near the Syrian border.",
            "source_document": {"id": "doc-2", "source_name": "book"},
            "projection_version": "book_projection_v16_slot_normalized",
        }
        phrase_entry = {
            "content": "near the Syrian border",
            "phrase_index": 0,
            "parent_phrase_index": None,
            "part_of_speech": "prepositional phrase",
            "grammatical_role": "modifier",
        }
        candidate = {"source_book": "egiu_2019", "topic": "pp_location"}

        built = _make_phrase_row(row | {"phrase_entries": [phrase_entry]}, phrase_entry, candidate, "PHRASE_PP_LOCATION")
        self.assertEqual(built["prompt_template_version"], "contract_template_classifier_v1")
        self.assertIn("predict_template_id_from_contract_context", built["input"])
        self.assertNotIn('"template_id": "PHRASE_PP_LOCATION"', built["input"])


if __name__ == "__main__":
    unittest.main()
