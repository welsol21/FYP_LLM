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


if __name__ == "__main__":
    unittest.main()
