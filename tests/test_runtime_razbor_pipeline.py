import unittest

from ela_pipeline.runtime.razbor_pipeline import build_text_analysis_payload
from ela_pipeline.validation.validator import validate_razbor_contract


class RuntimeRazborPipelineTests(unittest.TestCase):
    def test_build_text_analysis_payload_from_raw_text(self):
        payload = build_text_analysis_payload(
            raw_text="She trusted him. He apologized.",
            generate_notes=False,
        )

        self.assertEqual(payload["sentences"], ["She trusted him.", "He apologized."])
        self.assertEqual(len(payload["razbor"]), 2)
        self.assertEqual(set(payload["notes_sources"]), {"empty"})

        first_item = payload["razbor"][0]
        self.assertEqual(first_item["input"], "She trusted him.")
        self.assertEqual(first_item["notes"], {"elementary": "", "intermediate": "", "advanced": ""})
        self.assertTrue(validate_razbor_contract(first_item).ok)

        contract = payload["contract"]
        self.assertIn("She trusted him.", contract)
        sentence_node = contract["She trusted him."]
        self.assertEqual(sentence_node["type"], "Sentence")
        self.assertEqual(sentence_node["linguistic_notes"], [])
        self.assertGreater(len(sentence_node["linguistic_elements"]), 0)

        phrase = sentence_node["linguistic_elements"][0]
        self.assertEqual(phrase["type"], "Phrase")
        self.assertIsInstance(phrase["linguistic_notes"], list)

        words = phrase["linguistic_elements"]
        self.assertGreater(len(words), 0)
        self.assertTrue(any("lemma=" in " ".join(word.get("linguistic_notes", [])) for word in words))

    def test_build_text_analysis_payload_accepts_sentence_array(self):
        payload = build_text_analysis_payload(
            raw_text="",
            sentences=["I live in Cork.", "She has a car."],
            generate_notes=False,
        )
        self.assertEqual(payload["sentences"], ["I live in Cork.", "She has a car."])
        self.assertEqual(len(payload["razbor"]), 2)
        self.assertIn("I live in Cork.", payload["contract"])
        self.assertIn("She has a car.", payload["contract"])


if __name__ == "__main__":
    unittest.main()
