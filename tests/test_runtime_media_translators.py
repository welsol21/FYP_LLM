import unittest
from types import ModuleType
from unittest.mock import patch

from ela_pipeline.runtime.media_pipeline import (
    _resolve_media_translator,
    _select_m2m100_batch_size,
    translate_texts_with_provider,
)


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

    def test_resolve_m2m100_fails_fast_when_runtime_downloads_disabled_and_model_not_bundled(self):
        with patch.dict(
            "os.environ",
            {
                "ELA_MEDIA_DISABLE_RUNTIME_DOWNLOADS": "1",
                "ELA_MEDIA_TRANSLATION_MODEL": "/tmp/ela_missing_models/m2m100_418M",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                _resolve_media_translator(provider_override="m2m100", provider_credentials={})

    def test_select_m2m100_batch_size_uses_length_buckets(self):
        self.assertEqual(_select_m2m100_batch_size(["a"] * 10), 64)
        self.assertEqual(_select_m2m100_batch_size(["x" * 70] * 10), 48)
        self.assertEqual(_select_m2m100_batch_size(["x" * 200] * 10), 32)

    def test_translate_texts_with_provider_deduplicates_casefold_for_m2m100(self):
        class FakeM2M100:
            def __init__(self) -> None:
                self.calls: list[list[str]] = []

            def translate_texts(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:  # noqa: ARG002
                self.calls.append(list(texts))
                return [f"ru:{text}" for text in texts]

        fake_translator = FakeM2M100()
        progress_history: list[tuple[int, int]] = []

        with patch("ela_pipeline.runtime.media_pipeline.M2M100Translator", FakeM2M100), patch(
            "ela_pipeline.runtime.media_pipeline._resolve_media_translator",
            return_value=fake_translator,
        ):
            out = translate_texts_with_provider(
                ["Hello", "hello", "HELLO", "World"],
                translation_provider="m2m100",
                progress_callback=lambda done, total: progress_history.append((done, total)),
            )

        self.assertEqual(fake_translator.calls, [["hello", "world"]])
        self.assertEqual(out["Hello"], "ru:hello")
        self.assertEqual(out["hello"], "ru:hello")
        self.assertEqual(out["HELLO"], "ru:hello")
        self.assertEqual(out["World"], "ru:world")
        self.assertIn((4, 4), progress_history)


if __name__ == "__main__":
    unittest.main()
