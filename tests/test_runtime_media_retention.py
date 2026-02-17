import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.runtime.media_retention import (
    MediaRetentionConfig,
    cleanup_temp_media,
    load_media_retention_config_from_env,
)


class RuntimeMediaRetentionTests(unittest.TestCase):
    def test_load_config_from_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                "os.environ",
                {
                    "MEDIA_TEMP_DIR": tmpdir,
                    "MEDIA_RETENTION_TTL_HOURS": "12",
                },
                clear=False,
            ):
                cfg = load_media_retention_config_from_env()
        self.assertEqual(cfg.ttl_hours, 12)
        self.assertEqual(str(cfg.temp_dir), str(Path(tmpdir).resolve()))

    def test_cleanup_deletes_only_expired_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_file = root / "old.bin"
            new_file = root / "new.bin"
            old_file.write_bytes(b"x" * 100)
            new_file.write_bytes(b"y" * 50)

            now = time.time()
            os.utime(old_file, (now - 26 * 3600, now - 26 * 3600))
            os.utime(new_file, (now - 2 * 3600, now - 2 * 3600))

            cfg = MediaRetentionConfig(temp_dir=root, ttl_hours=24)
            report = cleanup_temp_media(cfg, now_epoch=now)

            self.assertEqual(report.scanned_files, 2)
            self.assertEqual(report.deleted_files, 1)
            self.assertEqual(report.kept_files, 1)
            self.assertEqual(report.bytes_deleted, 100)
            self.assertFalse(old_file.exists())
            self.assertTrue(new_file.exists())

    def test_cleanup_non_existing_dir(self):
        cfg = MediaRetentionConfig(temp_dir=Path("/tmp/does-not-exist-retention-test"), ttl_hours=24)
        report = cleanup_temp_media(cfg, now_epoch=time.time())
        self.assertEqual(report.scanned_files, 0)
        self.assertEqual(report.deleted_files, 0)
        self.assertEqual(report.kept_files, 0)


if __name__ == "__main__":
    unittest.main()
