import unittest
from unittest.mock import patch

from ela_pipeline.identity import hash_phone_e164, normalize_phone_e164, phone_hash_salt_from_env


class IdentityPolicyTests(unittest.TestCase):
    def test_normalize_phone_e164(self):
        self.assertEqual(normalize_phone_e164("+1 (202) 555-0101"), "+12025550101")
        self.assertEqual(normalize_phone_e164("2025550101"), "+2025550101")

    def test_normalize_phone_e164_rejects_invalid(self):
        with self.assertRaises(ValueError):
            normalize_phone_e164("")
        with self.assertRaises(ValueError):
            normalize_phone_e164("abc")
        with self.assertRaises(ValueError):
            normalize_phone_e164("+12")

    def test_hash_phone_e164_deterministic(self):
        h1 = hash_phone_e164("+1 202 555 0101", salt="pepper")
        h2 = hash_phone_e164("+12025550101", salt="pepper")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_phone_hash_salt_from_env_required(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                phone_hash_salt_from_env()
        with patch.dict("os.environ", {"ELA_PHONE_HASH_SALT": "s3cr3t"}, clear=True):
            self.assertEqual(phone_hash_salt_from_env(), "s3cr3t")


if __name__ == "__main__":
    unittest.main()
