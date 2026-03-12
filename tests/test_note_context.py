import unittest

from ela_pipeline.annotate.note_context import build_note_context_prompt


class NoteContextPromptTests(unittest.TestCase):
    def test_prompt_excludes_content_and_translation_payload(self):
        sentence = {
            "type": "Sentence",
            "content": "She should have trusted him.",
            "part_of_speech": "sentence",
            "grammatical_role": "clause",
            "cefr_level": "B1",
            "tense": "past",
            "aspect": "perfect",
            "mood": "modal",
            "voice": "active",
            "finiteness": "finite",
            "tam_construction": "modal_perfect",
            "grammar_classes": [{"class_id": "modal_perfect", "confidence": 0.9}],
            "translations": {"m2m100": {"text": "..."}} ,
            "active_translation_provider": "m2m100",
            "linguistic_elements": [],
        }
        node = {
            "type": "Phrase",
            "content": "should have trusted",
            "part_of_speech": "verb phrase",
            "grammatical_role": "predicate",
            "cefr_level": "B1",
            "tense": "past",
            "aspect": "perfect",
            "mood": "modal",
            "voice": "active",
            "finiteness": "finite",
            "tam_construction": "modal_perfect",
            "grammar_classes": [{"class_id": "modal_perfect", "confidence": 0.9}],
            "translations": {"m2m100": {"text": "..."}} ,
            "active_translation_provider": "m2m100",
            "linguistic_notes": ["legacy"],
            "linguistic_elements": [],
        }
        prompt = build_note_context_prompt(
            node=node,
            parent=sentence,
            sentence_node=sentence,
            path_types=["Sentence", "Phrase"],
            depth=1,
            sibling_index=0,
            sibling_count=1,
        )
        self.assertIn("self.type=Phrase", prompt)
        self.assertIn("self.grammar_classes=modal_perfect", prompt)
        self.assertNotIn("should have trusted", prompt)
        self.assertNotIn("m2m100", prompt)
        self.assertNotIn("legacy", prompt)


if __name__ == "__main__":
    unittest.main()
