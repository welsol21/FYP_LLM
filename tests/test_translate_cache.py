import os
import unittest
from unittest.mock import patch

from ela_pipeline.translate.cache import (
    InMemoryTranslationCache,
    build_translation_cache_from_env,
    build_translation_cache_key,
)


class TranslationCacheTests(unittest.TestCase):
    def test_cache_key_is_deterministic(self):
        first = build_translation_cache_key(
            source_text="Hello",
            source_lang="en",
            target_lang="ru",
            model_name="m2m",
        )
        second = build_translation_cache_key(
            source_text="Hello",
            source_lang="en",
            target_lang="ru",
            model_name="m2m",
        )
        third = build_translation_cache_key(
            source_text="Hello!",
            source_lang="en",
            target_lang="ru",
            model_name="m2m",
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_build_cache_from_env_memory(self):
        with patch.dict(os.environ, {"ELA_TRANSLATION_CACHE_BACKEND": "memory"}, clear=False):
            cache = build_translation_cache_from_env()
        self.assertIsInstance(cache, InMemoryTranslationCache)

    def test_build_cache_from_env_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            cache = build_translation_cache_from_env()
        self.assertIsNone(cache)

    def test_build_cache_from_env_redis_requires_url(self):
        with patch.dict(os.environ, {"ELA_TRANSLATION_CACHE_BACKEND": "redis"}, clear=True):
            with self.assertRaises(ValueError):
                build_translation_cache_from_env()

    def test_build_cache_from_env_rejects_unknown_backend(self):
        with patch.dict(os.environ, {"ELA_TRANSLATION_CACHE_BACKEND": "unknown"}, clear=True):
            with self.assertRaises(ValueError):
                build_translation_cache_from_env()


if __name__ == "__main__":
    unittest.main()
