import unittest

from ela_pipeline.db.keys import HASH_VERSION, build_sentence_key, canonicalize_text


class DBKeysTests(unittest.TestCase):
    def test_canonicalize_text_normalizes_whitespace(self):
        raw = "  She   trusted   him.\n"
        self.assertEqual(canonicalize_text(raw), "She trusted him.")

    def test_sentence_key_is_deterministic_and_context_sensitive(self):
        ctx_a = {"cefr_provider": "t5", "synonyms": True}
        ctx_b = {"cefr_provider": "rule", "synonyms": True}

        key1 = build_sentence_key(
            sentence_text="She trusted him.",
            source_lang="en",
            target_lang="ru",
            pipeline_context=ctx_a,
            hash_version=HASH_VERSION,
        )
        key2 = build_sentence_key(
            sentence_text="She trusted him.",
            source_lang="en",
            target_lang="ru",
            pipeline_context=ctx_a,
            hash_version=HASH_VERSION,
        )
        key3 = build_sentence_key(
            sentence_text="She trusted him.",
            source_lang="en",
            target_lang="ru",
            pipeline_context=ctx_b,
            hash_version=HASH_VERSION,
        )

        self.assertEqual(key1, key2)
        self.assertNotEqual(key1, key3)
        self.assertEqual(len(key1), 64)

