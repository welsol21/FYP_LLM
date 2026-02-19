import unittest
from types import ModuleType
from unittest.mock import patch

from ela_pipeline.runtime.media_pipeline import _resolve_media_translator


class RuntimeMediaTranslatorTests(unittest.TestCase):
    def test_resolve_lara_translator_uses_credentials_and_translation(self):
        calls: dict[str, str] = {}

        class FakeCredentials:
            def __init__(self, api_id: str, api_secret: str) -> None:
                calls["api_id"] = api_id
                calls["api_secret"] = api_secret

        class FakeResponse:
            translation = "Она доверяла ему."

        class FakeTranslator:
            def __init__(self, creds) -> None:  # noqa: ANN001
                self.creds = creds

            def translate(self, text: str, source: str, target: str):  # noqa: ANN201
                calls["text"] = text
                calls["source"] = source
                calls["target"] = target
                return FakeResponse()

        fake_module = ModuleType("lara_sdk")
        fake_module.Credentials = FakeCredentials
        fake_module.Translator = FakeTranslator

        with patch.dict("sys.modules", {"lara_sdk": fake_module}):
            translator = _resolve_media_translator(
                provider_override="lara",
                provider_credentials={"api_id": "id123", "api_secret": "sec456"},
            )
            translated = translator.translate_text("She trusted him.", source_lang="en", target_lang="ru")

        self.assertEqual(translated, "Она доверяла ему.")
        self.assertEqual(calls["api_id"], "id123")
        self.assertEqual(calls["api_secret"], "sec456")
        self.assertEqual(calls["text"], "She trusted him.")
        self.assertEqual(calls["source"], "en-US")
        self.assertEqual(calls["target"], "ru-RU")

    def test_resolve_lara_translator_requires_credentials(self):
        with self.assertRaises(RuntimeError):
            _resolve_media_translator(provider_override="lara", provider_credentials={})


if __name__ == "__main__":
    unittest.main()
