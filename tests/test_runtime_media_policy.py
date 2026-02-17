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

    def test_backend_route_when_exceeds_local_duration_but_backend_available(self):
        limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)
        caps = build_runtime_capabilities("online")
        decision = decide_media_route(
            duration_seconds=20 * 60,
            size_bytes=300 * 1024 * 1024,
            limits=limits,
            runtime_caps=caps,
        )
        self.assertEqual(decision.route, "backend")

    def test_reject_when_backend_size_limit_exceeded(self):
        limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)
        caps = build_runtime_capabilities("online")
        decision = decide_media_route(
            duration_seconds=10 * 60,
            size_bytes=(2048 + 1) * 1024 * 1024,
            limits=limits,
            runtime_caps=caps,
        )
        self.assertEqual(decision.route, "reject")
        self.assertIn("exceeds backend hard size limit", decision.reason)
        self.assertIn("limit_local=15m", decision.reason)
        self.assertIn("limit_backend=2048MB", decision.reason)

    def test_reject_when_backend_needed_but_offline_mode(self):
        limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)
        caps = build_runtime_capabilities("offline")
        decision = decide_media_route(
            duration_seconds=16 * 60,
            size_bytes=300 * 1024 * 1024,
            limits=limits,
            runtime_caps=caps,
        )
        self.assertEqual(decision.route, "reject")
        self.assertIn("offline mode", decision.reason)
        self.assertIn("duration=", decision.reason)
        self.assertIn("size=", decision.reason)


if __name__ == "__main__":
    unittest.main()
