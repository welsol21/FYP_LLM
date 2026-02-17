import tempfile
import unittest
from pathlib import Path

from ela_pipeline.runtime import MediaPolicyLimits, RuntimeMediaService


class RuntimeMediaServiceTests(unittest.TestCase):
    def test_ui_state_exposes_mode_and_feature_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="offline",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            ui_state = svc.get_ui_state()
            self.assertEqual(ui_state["runtime_mode"], "offline")
            self.assertFalse(ui_state["features"]["backend_jobs"]["enabled"])

    def test_submit_media_backend_queue_and_feedback_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            response = svc.submit_media(
                media_path="/tmp/long.mp4",
                duration_seconds=1800,
                size_bytes=300 * 1024 * 1024,
                project_id="proj-1",
                media_file_id="file-1",
            )
            self.assertEqual(response["result"]["route"], "backend")
            self.assertEqual(response["ui_feedback"]["severity"], "warning")
            jobs = svc.list_backend_jobs(status="queued")
            self.assertEqual(len(jobs), 1)

    def test_submit_media_reject_returns_error_feedback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="offline",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            response = svc.submit_media(
                media_path="/tmp/long.mp4",
                duration_seconds=1800,
                size_bytes=300 * 1024 * 1024,
            )
            self.assertEqual(response["result"]["route"], "reject")
            self.assertEqual(response["ui_feedback"]["severity"], "error")
            self.assertEqual(svc.list_backend_jobs(), [])


if __name__ == "__main__":
    unittest.main()
