import unittest

from ela_pipeline.legacy_bridge import (
    apply_node_edit,
    build_visualizer_payload,
    build_visualizer_payload_for_document,
)


class LegacyVisualizerEditorBridgeTests(unittest.TestCase):
    def setUp(self):
        self.doc = {
            "She trusted him.": {
                "type": "Sentence",
                "node_id": "s1",
                "content": "She trusted him.",
                "part_of_speech": "sentence",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "node_id": "p1",
                        "content": "trusted him",
                        "part_of_speech": "verb phrase",
                        "notes": [{"text": "old"}],
                        "linguistic_elements": [
                            {
                                "type": "Word",
                                "node_id": "w1",
                                "content": "trusted",
                                "part_of_speech": "verb",
                                "linguistic_elements": [],
                            }
                        ],
                    }
                ],
            }
        }

    def test_build_visualizer_payload(self):
        tree = build_visualizer_payload(self.doc["She trusted him."])
        self.assertEqual(tree["node_id"], "s1")
        self.assertEqual(tree["linguistic_elements"][0]["node_id"], "p1")
        self.assertEqual(tree["linguistic_elements"][0]["linguistic_elements"][0]["node_id"], "w1")
        self.assertEqual(
            tree["linguistic_elements"][0]["notes"][0]["text"],
            "old",
        )

    def test_build_visualizer_payload_for_document(self):
        payload = build_visualizer_payload_for_document(self.doc)
        self.assertEqual(len(payload), 1)
        self.assertIn("She trusted him.", payload)
        self.assertEqual(payload["She trusted him."]["node_id"], "s1")

    def test_apply_node_edit_updates_target_path(self):
        updated = apply_node_edit(
            self.doc,
            sentence_text="She trusted him.",
            node_id="p1",
            field_path="notes[0].text",
            new_value="new note",
        )
        note = updated["She trusted him."]["linguistic_elements"][0]["notes"][0]["text"]
        self.assertEqual(note, "new note")
        old_note = self.doc["She trusted him."]["linguistic_elements"][0]["notes"][0]["text"]
        self.assertEqual(old_note, "old")


if __name__ == "__main__":
    unittest.main()
