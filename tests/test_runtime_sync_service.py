import tempfile
import unittest
from pathlib import Path

from ela_pipeline.runtime import SyncService


class RuntimeSyncServiceTests(unittest.TestCase):
    def test_queue_missing_content_and_mark_sent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = SyncService(db_path=Path(tmpdir) / "client.sqlite3")
            req = svc.queue_missing_content(source_text="Brand new sentence.", source_lang="en")
            self.assertEqual(req["request_type"], "missing_content")
            queued = svc.list_queued()
            self.assertEqual(len(queued), 1)
            self.assertEqual(queued[0]["id"], req["id"])

            svc.mark_sent(req["id"])
            self.assertEqual(svc.list_queued(), [])

    def test_queue_large_media_reference_and_mark_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = SyncService(db_path=Path(tmpdir) / "client.sqlite3")
            req = svc.queue_large_media_reference(
                media_path="/tmp/huge.mp4",
                duration_seconds=3600,
                size_bytes=3 * 1024 * 1024 * 1024,
            )
            self.assertEqual(req["request_type"], "large_media_reference")
            svc.mark_failed(req["id"])
            self.assertEqual(svc.list_queued(), [])


if __name__ == "__main__":
    unittest.main()
