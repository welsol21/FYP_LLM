import unittest

from ela_pipeline.dataset.template_slot_book_notes import _template_row


class TemplateSlotBookNotesTests(unittest.TestCase):
    def test_sentence_row_uses_topic_template_without_phrase_parse(self):
        row = {
            "context": {
                "node_type": "Sentence",
                "content": "He didn't leave.",
                "sentence_text": "He didn't leave.",
                "part_of_speech": "sentence",
                "grammatical_role": "clause",
            },
            "source": {
                "topic": "negative clause",
            },
            "target": {
                "note_text": "In English negation, not is typically placed after the first auxiliary or after do in do-support clauses.",
            },
        }

        templated_row, flags = _template_row(row, nlp=None)
        projection = templated_row["template_projection"]

        self.assertEqual(projection["template_kind"], "topic_template::sent_negation_general")
        self.assertTrue(projection["templated"])
        self.assertEqual(
            projection["note_template"],
            "This sentence includes clause-level negation, which makes the proposition negative rather than affirmative.",
        )
        self.assertEqual(projection["rendered_note"], projection["note_template"])
        self.assertEqual(flags, [])

    def test_sentence_question_tag_row_uses_placeholder_template_and_slots(self):
        row = {
            "context": {
                "node_type": "Sentence",
                "content": "You will take all the swear words out, won't you?",
                "sentence_text": "You will take all the swear words out, won't you?",
                "part_of_speech": "sentence",
                "grammatical_role": "clause",
            },
            "source": {
                "topic": "question tags",
            },
            "target": {
                "note_text": "Question tags are short reduced questions added to declaratives to seek confirmation.",
            },
        }

        templated_row, _flags = _template_row(row, nlp=None)
        projection = templated_row["template_projection"]

        self.assertEqual(projection["template_kind"], "topic_template::sent_question_tag")
        self.assertTrue(projection["templated"])
        self.assertEqual(projection["slot_values"]["TAG_AUXILIARY"], "won't")
        self.assertEqual(projection["slot_values"]["TAG_PRONOUN"], "you")
        self.assertIn("{{TAG_AUXILIARY}}", projection["note_template"])


if __name__ == "__main__":
    unittest.main()
