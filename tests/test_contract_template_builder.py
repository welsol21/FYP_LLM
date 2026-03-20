import unittest

from ela_pipeline.annotate.contract_template_builder import (
    build_contract_template_payload,
    build_contract_template_training_prompt,
    resolve_generated_template_text,
)


class ContractTemplateBuilderTests(unittest.TestCase):
    def test_builds_question_tag_sentence_template_payload(self):
        sentence = {
            "type": "Sentence",
            "node_id": "s1",
            "content": "You called him, didn't you?",
            "part_of_speech": "sentence",
            "grammatical_role": "clause",
            "cefr_level": "B1",
            "tam_construction": "none",
            "grammar_classes": [{"class_id": "question_tag", "confidence": 0.9}],
            "linguistic_elements": [],
        }

        payload = build_contract_template_payload(
            node=sentence,
            sentence_node=sentence,
            parent=None,
            path_types=["Sentence"],
            depth=0,
            sibling_index=0,
            sibling_count=1,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["template_id"], "SENT_QUESTION_TAG")
        self.assertEqual(payload["slot_values"]["TAG_AUXILIARY"], "didn't")
        self.assertEqual(payload["slot_values"]["TAG_PRONOUN"], "you")
        self.assertIn("{{TAG_AUXILIARY}}", payload["template_text"])
        self.assertEqual(
            payload["rendered_note_text"],
            "Question tags repeat didn't and use you as the pronoun subject.",
        )

    def test_builds_phrase_slot_payload_from_contract_tree(self):
        phrase = {
            "type": "Phrase",
            "node_id": "p1",
            "parent_id": "s1",
            "content": "near the Syrian border",
            "part_of_speech": "prepositional phrase",
            "grammatical_role": "modifier",
            "cefr_level": "A2",
            "tam_construction": "none",
            "grammar_classes": [{"class_id": "prepositional_relation_phrase", "confidence": 0.9}],
            "source_span": {"start": 36, "end": 59},
            "linguistic_elements": [
                {
                    "type": "Word",
                    "content": "near",
                    "part_of_speech": "preposition",
                    "grammatical_role": "marker",
                    "source_span": {"start": 36, "end": 40},
                    "linguistic_elements": [],
                },
                {
                    "type": "Word",
                    "content": "the",
                    "part_of_speech": "article",
                    "grammatical_role": "determiner",
                    "source_span": {"start": 41, "end": 44},
                    "linguistic_elements": [],
                },
                {
                    "type": "Word",
                    "content": "Syrian",
                    "part_of_speech": "adjective",
                    "grammatical_role": "modifier",
                    "source_span": {"start": 45, "end": 51},
                    "linguistic_elements": [],
                },
                {
                    "type": "Word",
                    "content": "border",
                    "part_of_speech": "noun",
                    "grammatical_role": "object",
                    "source_span": {"start": 52, "end": 58},
                    "linguistic_elements": [],
                },
            ],
        }
        sentence = {
            "type": "Sentence",
            "node_id": "s1",
            "content": "American forces killed Shaikh Abdullah al-Ani near the Syrian border.",
            "part_of_speech": "sentence",
            "grammatical_role": "clause",
            "cefr_level": "B1",
            "tam_construction": "none",
            "grammar_classes": [],
            "linguistic_elements": [
                {
                    "type": "Word",
                    "content": "Ani",
                    "part_of_speech": "proper noun",
                    "grammatical_role": "object",
                    "source_span": {"start": 31, "end": 34},
                    "linguistic_elements": [],
                },
                phrase,
            ],
        }

        payload = build_contract_template_payload(
            node=phrase,
            sentence_node=sentence,
            parent=sentence,
            path_types=["Sentence", "Phrase"],
            depth=1,
            sibling_index=1,
            sibling_count=2,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["template_id"], "PHRASE_PP_LOCATION")
        self.assertEqual(payload["slot_values"]["PART_OF_SPEECH"], "prepositional phrase")
        self.assertEqual(payload["slot_values"]["GRAMMATICAL_ROLE"], "modifier")
        self.assertEqual(
            payload["rendered_note_text"],
            "This prepositional phrase works as a modifier and expresses location or spatial position.",
        )

    def test_serializes_training_prompt_from_template_payload(self):
        sentence = {
            "type": "Sentence",
            "node_id": "s1",
            "content": "You called him, didn't you?",
            "part_of_speech": "sentence",
            "grammatical_role": "clause",
            "cefr_level": "B1",
            "tam_construction": "none",
            "grammar_classes": [{"class_id": "question_tag", "confidence": 0.9}],
            "linguistic_elements": [],
        }
        payload = build_contract_template_payload(
            node=sentence,
            sentence_node=sentence,
            parent=None,
            path_types=["Sentence"],
            depth=0,
            sibling_index=0,
            sibling_count=1,
        )

        prompt = build_contract_template_training_prompt(payload or {}, node_level="Sentence")
        self.assertIn("rewrite_linguistic_note_template_from_contract_template", prompt)
        self.assertIn('"prompt_template_version": "contract_template_v2"', prompt)
        self.assertIn('"template_id": "SENT_QUESTION_TAG"', prompt)
        self.assertIn('"deterministic_note": "Question tags repeat didn\'t and use you as the pronoun subject."', prompt)

    def test_generated_template_text_falls_back_when_slots_do_not_match(self):
        resolved, status = resolve_generated_template_text(
            'Here, "{{OBJECT_NP}}" is linked by "{{PREPOSITION}}".',
            default_template_text='This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses location.',
            allowed_slots=["PART_OF_SPEECH", "GRAMMATICAL_ROLE"],
        )
        self.assertEqual(
            resolved,
            "This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses location.",
        )
        self.assertEqual(status, "template_fallback_slot_mismatch")

    def test_generated_template_text_falls_back_on_prompt_leakage(self):
        resolved, status = resolve_generated_template_text(
            "Keep exactly the same placeholders as in the template_text field. Return template text only.",
            default_template_text='This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses location.',
            allowed_slots=["PART_OF_SPEECH", "GRAMMATICAL_ROLE"],
        )
        self.assertEqual(
            resolved,
            "This {{PART_OF_SPEECH}} works as a {{GRAMMATICAL_ROLE}} and expresses location.",
        )
        self.assertEqual(status, "template_fallback_prompt_leakage")


if __name__ == "__main__":
    unittest.main()
