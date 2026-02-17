import unittest

from ela_pipeline.runtime import (
    build_runtime_capabilities,
    build_runtime_ui_state,
    build_submission_ui_feedback,
)


class RuntimeUIStateTests(unittest.TestCase):
    def test_offline_ui_state_contains_disabled_reasons(self):
        state = build_runtime_ui_state(build_runtime_capabilities("offline"))
        self.assertEqual(state["runtime_mode"], "offline")
        self.assertFalse(state["features"]["phonetic"]["enabled"])
        self.assertIn("offline", state["features"]["phonetic"]["reason_if_disabled"].lower())
        self.assertIn("Mode: offline", state["badges"]["mode"])

    def test_online_ui_state_features_enabled(self):
        state = build_runtime_ui_state(build_runtime_capabilities("online"))
        self.assertTrue(state["features"]["phonetic"]["enabled"])
        self.assertTrue(state["features"]["db_persistence"]["enabled"])
        self.assertTrue(state["features"]["backend_jobs"]["enabled"])

    def test_submission_feedback_variants(self):
        local = build_submission_ui_feedback(
            {"route": "local", "message": "local ok", "job_id": None}
        )
        backend = build_submission_ui_feedback(
            {"route": "backend", "message": "queued", "job_id": "job-1"}
        )
        rejected = build_submission_ui_feedback(
            {"route": "reject", "message": "too large", "job_id": None}
        )

        self.assertEqual(local["severity"], "info")
        self.assertEqual(backend["severity"], "warning")
        self.assertIn("job-1", backend["message"])
        self.assertEqual(rejected["severity"], "error")
        self.assertIn("rejected", rejected["title"].lower())


if __name__ == "__main__":
    unittest.main()
