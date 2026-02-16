import unittest

from ela_pipeline.synonyms.engine import WordNetSynonymProvider


class _FakeWordNet:
    def __init__(self):
        self.calls = []

    def synsets(self, raw, pos=None):
        self.calls.append((raw, pos))
        return []


class SynonymsEngineTests(unittest.TestCase):
    def test_function_pos_returns_empty_without_wordnet_lookup(self):
        provider = object.__new__(WordNetSynonymProvider)
        provider._wn = _FakeWordNet()
        result = provider.get_synonyms("have", pos="auxiliary verb", top_k=5)
        self.assertEqual(result, [])
        self.assertEqual(provider._wn.calls, [])

    def test_lexical_pos_uses_mapped_wordnet_pos(self):
        provider = object.__new__(WordNetSynonymProvider)
        provider._wn = _FakeWordNet()
        provider.get_synonyms("trust", pos="verb", top_k=3)
        self.assertEqual(provider._wn.calls, [("trust", "v")])


if __name__ == "__main__":
    unittest.main()
