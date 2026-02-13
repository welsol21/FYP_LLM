import unittest

from ela_pipeline.annotate.local_generator import LocalT5Annotator


class NodeSuitabilityTests(unittest.TestCase):
    def setUp(self):
        self.annotator = LocalT5Annotator.__new__(LocalT5Annotator)

    def test_word_note_must_anchor_content(self):
        node = {"type": "Word", "content": "artifact", "tense": "null", "part_of_speech": "noun"}
        self.assertFalse(
            self.annotator._is_note_suitable_for_node(
                node,
                "This is a noun that names an entity in context.",
            )
        )
        self.assertTrue(
            self.annotator._is_note_suitable_for_node(
                node,
                "'artifact' is a noun that names an entity in context.",
            )
        )
        self.assertFalse(
            self.annotator._is_note_suitable_for_node(
                node,
                "artifact is a noun that names an entity in context.",
            )
        )

    def test_sentence_note_checks_scope(self):
        node = {"type": "Sentence", "content": "X", "tense": "past", "part_of_speech": "sentence"}
        self.assertFalse(
            self.annotator._is_note_suitable_for_node(
                node,
                "Main clause in the present simple with a clear structure.",
            )
        )
        self.assertTrue(
            self.annotator._is_note_suitable_for_node(
                node,
                "This sentence is a complete clause with a finite predicate.",
            )
        )

    def test_rejected_candidates_are_deduplicated_with_stats(self):
        rejected_items = [
            {"text": "Verb-centred phrase expressing what happens to or about the subject.", "reason": "MODEL_OUTPUT_LOW_QUALITY"},
            {"text": "Verb-centred phrase expressing what happens to or about the subject.", "reason": "MODEL_OUTPUT_LOW_QUALITY"},
            {"text": "Verb-centred phrase expressing what happens to or about the subject.", "reason": "MODEL_NOTE_UNSUITABLE"},
        ]
        deduped, stats = self.annotator._build_rejection_stats(rejected_items)
        self.assertEqual(
            deduped,
            ["Verb-centred phrase expressing what happens to or about the subject"],
        )
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["count"], 3)
        self.assertEqual(
            set(stats[0]["reasons"]),
            {"MODEL_OUTPUT_LOW_QUALITY", "MODEL_NOTE_UNSUITABLE"},
        )


if __name__ == "__main__":
    unittest.main()
