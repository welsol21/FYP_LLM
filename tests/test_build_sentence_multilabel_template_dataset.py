import unittest

from ela_pipeline.classifier.build_sentence_multilabel_template_dataset import _make_row


class BuildSentenceMultilabelTemplateDatasetTests(unittest.TestCase):
    def test_make_row_uses_contract_classifier_prompt(self):
        item = {
            "sentence_text": "You called him, didn't you?",
            "source_document": {"id": "doc-1", "source_name": "book"},
            "projection_version": "book_projection_v16_slot_normalized",
            "sentence_note_candidates": [
                {
                    "source_book": "egiu_2019",
                    "topic": "question tag",
                    "note_text": "Question tags repeat didn't and use you as the pronoun subject.",
                    "slot_rendered_note": "Question tags repeat didn't and use you as the pronoun subject.",
                }
            ],
            "phrase_entries": [],
            "sentence_family_alignment": {},
        }

        row = _make_row(item)
        self.assertIsNotNone(row)
        self.assertEqual(row["prompt_template_version"], "contract_template_classifier_v1")
        self.assertIn("predict_multilabel_template_ids_from_contract_context", row["input"])
        self.assertEqual(row["template_ids"], ["SENT_QUESTION_TAG"])


if __name__ == "__main__":
    unittest.main()
