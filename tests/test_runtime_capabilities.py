import unittest
from unittest.mock import patch

from ela_pipeline.runtime.capabilities import (
    RuntimeFeatureRequest,
    build_runtime_capabilities,
    resolve_deployment_mode,
    resolve_phonetic_policy,
    resolve_runtime_mode,
    validate_runtime_feature_request,
)


class RuntimeCapabilitiesTests(unittest.TestCase):
    def test_resolve_runtime_mode_auto_defaults_to_online(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_runtime_mode("auto"), "online")

    def test_resolve_runtime_mode_auto_from_env(self):
        with patch.dict("os.environ", {"ELA_RUNTIME_MODE": "offline"}, clear=True):
            self.assertEqual(resolve_runtime_mode("auto"), "offline")

    def test_resolve_deployment_mode_auto_from_env(self):
        with patch.dict("os.environ", {"ELA_DEPLOYMENT_MODE": "backend"}, clear=True):
            self.assertEqual(resolve_deployment_mode("auto"), "backend")

    def test_resolve_phonetic_policy(self):
        with patch.dict("os.environ", {"ELA_PHONETIC_POLICY": "backend_only"}, clear=True):
            self.assertEqual(resolve_phonetic_policy(), "backend_only")

    def test_offline_blocks_phonetic_and_db_persistence(self):
        with patch.dict("os.environ", {"ELA_PHONETIC_POLICY": "enabled"}, clear=False):
            caps = build_runtime_capabilities("offline")

        with self.assertRaisesRegex(RuntimeError, "phonetic enrichment"):
            validate_runtime_feature_request(
                caps,
                RuntimeFeatureRequest(enable_phonetic=True),
            )

        with self.assertRaisesRegex(RuntimeError, "DB persistence"):
            validate_runtime_feature_request(
                caps,
                RuntimeFeatureRequest(enable_db_persistence=True),
            )

    def test_offline_allows_non_backend_features(self):
        with patch.dict("os.environ", {"ELA_PHONETIC_POLICY": "enabled"}, clear=False):
            caps = build_runtime_capabilities("offline")
        validate_runtime_feature_request(
            caps,
            RuntimeFeatureRequest(
                enable_phonetic=False,
                enable_db_persistence=False,
                enable_backend_job=False,
            ),
        )

    def test_online_allows_all_features(self):
        with patch.dict("os.environ", {"ELA_PHONETIC_POLICY": "enabled"}, clear=False):
            caps = build_runtime_capabilities("online", deployment_mode="backend")
        validate_runtime_feature_request(
            caps,
            RuntimeFeatureRequest(
                enable_phonetic=True,
                enable_db_persistence=True,
                enable_backend_job=True,
            ),
        )

    def test_backend_only_policy_disables_phonetic_in_local_deployment(self):
        with patch.dict("os.environ", {"ELA_PHONETIC_POLICY": "backend_only"}, clear=False):
            caps = build_runtime_capabilities("online", deployment_mode="local")
            self.assertFalse(caps.phonetic_enabled)
            with self.assertRaisesRegex(RuntimeError, "license gate"):
                validate_runtime_feature_request(
                    caps,
                    RuntimeFeatureRequest(enable_phonetic=True),
                )


if __name__ == "__main__":
    unittest.main()
