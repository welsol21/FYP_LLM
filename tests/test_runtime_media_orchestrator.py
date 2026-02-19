import unittest

from ela_pipeline.runtime import (
    MediaPolicyLimits,
    build_runtime_capabilities,
    plan_media_execution,
)


class RuntimeMediaOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)

    def test_plan_local_action(self):
        caps = build_runtime_capabilities("online")
        plan = plan_media_execution(
            media_path="/tmp/a.mp3",
            duration_seconds=300,
            size_bytes=100 * 1024 * 1024,
            limits=self.limits,
            runtime_caps=caps,
        )
        self.assertEqual(plan.action, "run_local")

    def test_plan_reject_action(self):
        caps = build_runtime_capabilities("online")
        plan = plan_media_execution(
            media_path="/tmp/c.mp3",
            duration_seconds=300,
            size_bytes=5000 * 1024 * 1024,
            limits=self.limits,
            runtime_caps=caps,
        )
        self.assertEqual(plan.action, "reject")
        self.assertIn("exceeds local processing limits", plan.message)


if __name__ == "__main__":
    unittest.main()
