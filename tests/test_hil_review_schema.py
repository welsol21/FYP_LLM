import unittest

from ela_pipeline.hil.review_schema import (
    is_allowed_review_field_path,
    review_field_root,
)


class HILReviewSchemaTests(unittest.TestCase):
    def test_review_field_root(self):
        self.assertEqual(review_field_root("notes[0].text"), "notes")
        self.assertEqual(review_field_root("translation.text"), "translation")
        self.assertEqual(review_field_root("cefr_level"), "cefr_level")
        self.assertIsNone(review_field_root(""))

    def test_allowed_review_field_paths(self):
        self.assertTrue(is_allowed_review_field_path("notes[0].text"))
        self.assertTrue(is_allowed_review_field_path("translation.text"))
        self.assertTrue(is_allowed_review_field_path("phonetic.uk"))
        self.assertTrue(is_allowed_review_field_path("features.number"))
        self.assertTrue(is_allowed_review_field_path("cefr_level"))
        self.assertFalse(is_allowed_review_field_path("unsupported_field"))
        self.assertFalse(is_allowed_review_field_path("bad-path"))


if __name__ == "__main__":
    unittest.main()
