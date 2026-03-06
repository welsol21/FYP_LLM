import json
import unittest
from pathlib import Path

from ela_pipeline.validation.validator import validate_razbor_contract


class RazborValidatorTests(unittest.TestCase):
    def test_validates_example_dataset(self):
        path = Path("docs/example_sentences_razbor.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = validate_razbor_contract(payload)
        self.assertTrue(result.ok, msg="\n".join(f"{e.path}: {e.message}" for e in result.errors[:20]))


if __name__ == "__main__":
    unittest.main()
