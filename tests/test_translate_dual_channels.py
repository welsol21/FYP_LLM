import unittest

from ela_pipeline.inference.run import _attach_translation
from ela_pipeline.translate.channels import build_dual_translation_channels


class _FakeTranslator:
    model_name = "fake-model"

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        return f"T[{target_lang}]: {text}"


class TranslateDualChannelsTests(unittest.TestCase):
    def test_build_dual_channels_fallback(self):
        lit, idi = build_dual_translation_channels(literary_text="Hello", target_lang="en")
        self.assertEqual(lit, "Hello")
        self.assertEqual(idi, "Hello")

    def test_attach_translation_dual_channels(self):
        doc = {
            "She trusted him.": {
                "type": "Sentence",
                "content": "She trusted him.",
                "linguistic_elements": [
                    {
                        "type": "Phrase",
                        "content": "trusted him",
                        "linguistic_elements": [],
                    }
                ],
            }
        }
        _attach_translation(
            doc,
            translator=_FakeTranslator(),
            source_lang="en",
            target_lang="ru",
            include_node_translations=True,
            dual_channels=True,
        )
        sent = doc["She trusted him."]
        self.assertIn("translation_literary", sent)
        self.assertIn("translation_idiomatic", sent)
        self.assertIn("translation", sent)
        phrase = sent["linguistic_elements"][0]
        self.assertIn("translation_literary", phrase)
        self.assertIn("translation_idiomatic", phrase)
        self.assertIn("translation", phrase)


if __name__ == "__main__":
    unittest.main()
