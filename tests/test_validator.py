import json
import unittest

from ela_pipeline.validation.validator import validate_contract, validate_frozen_structure


class ValidatorTests(unittest.TestCase):
    def test_sample_contract_valid(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        result = validate_contract(data)
        self.assertTrue(result.ok, msg=str(result.errors))

    def test_frozen_detects_content_change(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            skeleton = json.load(f)

        enriched = json.loads(json.dumps(skeleton))
        key = next(iter(enriched))
        enriched[key]["linguistic_elements"][0]["content"] = "BROKEN"

        result = validate_frozen_structure(skeleton, enriched)
        self.assertFalse(result.ok)

    def test_rejects_one_word_phrase(self):
        with open("docs/sample.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sentence_key = next(iter(data))
        sentence = data[sentence_key]
        sentence["linguistic_elements"][0]["linguistic_elements"] = [
            sentence["linguistic_elements"][0]["linguistic_elements"][0]
        ]

        result = validate_contract(data)
        self.assertFalse(result.ok)
        self.assertTrue(
            any("at least 2 Word nodes" in err.message for err in result.errors),
            msg=str(result.errors),
        )


if __name__ == "__main__":
    unittest.main()
