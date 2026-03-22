import unittest

from ela_pipeline.dataset.build_t5_dataset_from_projected_corpus import (
    _make_phrase_row,
    _make_sentence_row,
)


class BuildT5DatasetFromProjectedCorpusTests(unittest.TestCase):
    def test_sentence_row_uses_contract_template_prompt(self):
        row = {
            "sentence_text": "You called him, didn't you?",
            "source_document": {"id": "doc-1", "source_name": "book"},
            "sentence_note_candidates": [],
            "phrase_entries": [],
            "projection_version": "book_projection_v16_slot_normalized",
        }
        candidate = {
            "source_book": "egiu_2019",
            "topic": "question tag",
            "origin_unit": "u1",
            "match_level": "sentence",
            "note_text": "Question tags repeat didn't and use you as the pronoun subject.",
            "slot_template_text": 'Question tags repeat "{{TAG_AUXILIARY}}" and use "{{TAG_PRONOUN}}" as the pronoun subject.',
            "slot_templated": True,
            "slot_rendered_note": "Question tags repeat didn't and use you as the pronoun subject.",
        }

        built = _make_sentence_row(row, candidate)
        self.assertEqual(built["prompt_template_version"], "contract_template_v2")
        self.assertEqual(built["template_id"], "SENT_QUESTION_TAG")
        self.assertIn('"template_id": "SENT_QUESTION_TAG"', built["input"])
        self.assertIn("rewrite_linguistic_note_template_from_contract_template", built["input"])
        self.assertEqual(
            built["target"],
            'Question tags repeat "{{TAG_AUXILIARY}}" and use "{{TAG_PRONOUN}}" as the pronoun subject.',
        )
        self.assertEqual(built["note_target_variant"], "slot_template")

    def test_phrase_row_uses_contract_template_prompt(self):
        row = {
            "sentence_text": "American forces killed Shaikh Abdullah al-Ani near the Syrian border.",
            "source_document": {"id": "doc-2", "source_name": "book"},
            "projection_version": "book_projection_v16_slot_normalized",
            "phrase_entries": [
                {
                    "phrase_index": 0,
                    "parent_phrase_index": None,
                    "content": "near the Syrian border",
                    "part_of_speech": "prepositional phrase",
                    "grammatical_role": "modifier",
                    "source_span": {"start": 36, "end": 59},
                    "note_candidates": [],
                }
            ],
        }
        candidate = {
            "source_book": "egiu_2019",
            "topic": "pp_location",
            "origin_unit": "u2",
            "match_level": "phrase",
            "note_text": "This prepositional phrase works as a modifier and expresses location or spatial position.",
            "slot_rendered_note": "This prepositional phrase works as a modifier and expresses location or spatial position.",
        }

        built = _make_phrase_row(row, row["phrase_entries"][0], candidate)
        self.assertEqual(built["prompt_template_version"], "contract_template_v2")
        self.assertEqual(built["template_id"], "PHRASE_PP_LOCATION")
        self.assertIn('"template_id": "PHRASE_PP_LOCATION"', built["input"])
        self.assertIn("rewrite_linguistic_note_template_from_contract_template", built["input"])
        self.assertEqual(
            built["target"],
            "This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses location or spatial position.",
        )
        self.assertEqual(built["note_target_variant"], "contract_template")


if __name__ == "__main__":
    unittest.main()
