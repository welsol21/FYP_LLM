import unittest
from unittest.mock import patch

from ela_pipeline.runtime.capabilities import build_runtime_capabilities
from ela_pipeline.runtime.media_policy import (
    MediaPolicyLimits,
    decide_media_route,
    load_media_policy_limits_from_env,
)


class RuntimeMediaPolicyTests(unittest.TestCase):
    def test_load_limits_from_env(self):
        with patch.dict(
            "os.environ",
            {
                "MEDIA_MAX_DURATION_MIN": "15",
                "MEDIA_MAX_SIZE_LOCAL_MB": "250",
                "MEDIA_MAX_SIZE_BACKEND_MB": "2048",
            },
            clear=False,
        ):
            limits = load_media_policy_limits_from_env()
        self.assertEqual(limits.max_duration_min, 15)
        self.assertEqual(limits.max_size_local_mb, 250)
        self.assertEqual(limits.max_size_backend_mb, 2048)

    def test_local_route_when_duration_and_size_fit_local_limits(self):
        limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)
        caps = build_runtime_capabilities("online")
        decision = decide_media_route(
            duration_seconds=14 * 60,
            size_bytes=200 * 1024 * 1024,
            limits=limits,
            runtime_caps=caps,
        )
        self.assertEqual(decision.route, "local")
        self.assertIn("duration=", decision.reason)
        self.assertIn("size=", decision.reason)

    def test_reject_when_exceeds_local_limits(self):
        limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)
        caps = build_runtime_capabilities("online")
        decision = decide_media_route(
            duration_seconds=20 * 60,
            size_bytes=300 * 1024 * 1024,
            limits=limits,
            runtime_caps=caps,
        )
        self.assertEqual(decision.route, "reject")
        self.assertIn("exceeds local processing limits", decision.reason)

    def test_backend_enrichment_flag_is_ignored_and_keeps_local_route(self):
        limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)
        caps = build_runtime_capabilities("online")
        decision = decide_media_route(
            duration_seconds=5 * 60,
            size_bytes=50 * 1024 * 1024,
            limits=limits,
            runtime_caps=caps,
            prefer_backend_for_enrichment=True,
        )
        self.assertEqual(decision.route, "local")

    def test_reject_when_size_limit_exceeded(self):
        limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)
        caps = build_runtime_capabilities("online")
        decision = decide_media_route(
            duration_seconds=10 * 60,
            size_bytes=(250 + 1) * 1024 * 1024,
            limits=limits,
            runtime_caps=caps,
        )
        self.assertEqual(decision.route, "reject")
        self.assertIn("exceeds local processing limits", decision.reason)
        self.assertIn("limit_local=15m", decision.reason)
        self.assertIn("limit_local=250MB", decision.reason)


if __name__ == "__main__":
    unittest.main()
