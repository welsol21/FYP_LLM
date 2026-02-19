import tempfile
import unittest
from pathlib import Path

from ela_pipeline.client_storage import LocalSQLiteRepository
from ela_pipeline.runtime import (
    MediaPolicyLimits,
    build_runtime_capabilities,
    submit_media_for_processing,
)


class RuntimeMediaSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.limits = MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048)

    def test_local_submission_returns_local_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = LocalSQLiteRepository(Path(tmpdir) / "client.sqlite3")
            result = submit_media_for_processing(
                repo=repo,
                media_path="/tmp/short.mp3",
                duration_seconds=300,
                size_bytes=80 * 1024 * 1024,
                runtime_caps=build_runtime_capabilities("online"),
                limits=self.limits,
            )
            self.assertEqual(result["route"], "local")
            self.assertEqual(result["status"], "accepted_local")
            self.assertIsNone(result["job_id"])

    def test_large_submission_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = LocalSQLiteRepository(Path(tmpdir) / "client.sqlite3")
            result = submit_media_for_processing(
                repo=repo,
                media_path="/tmp/long.mp3",
                duration_seconds=1800,
                size_bytes=300 * 1024 * 1024,
                runtime_caps=build_runtime_capabilities("online"),
                limits=self.limits,
                project_id="proj-1",
                media_file_id="file-1",
            )
            self.assertEqual(result["route"], "reject")
            self.assertEqual(result["status"], "rejected")
            self.assertIsNone(result["job_id"])

    def test_offline_submission_rejects_oversized_media(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = LocalSQLiteRepository(Path(tmpdir) / "client.sqlite3")
            result = submit_media_for_processing(
                repo=repo,
                media_path="/tmp/long.mp3",
                duration_seconds=1800,
                size_bytes=300 * 1024 * 1024,
                runtime_caps=build_runtime_capabilities("offline"),
                limits=self.limits,
            )
            self.assertEqual(result["route"], "reject")
            self.assertEqual(result["status"], "rejected")
            self.assertIn("local processing limits", result["message"])
            self.assertEqual(repo.list_backend_jobs(), [])


if __name__ == "__main__":
    unittest.main()
