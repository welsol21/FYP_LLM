import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.runtime import client_api


class RuntimeClientAPITests(unittest.TestCase):
    def test_ui_state_command_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "--runtime-mode",
                "offline",
                "ui-state",
            ]
            with patch("sys.argv", argv):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    client_api.main()
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["runtime_mode"], "offline")

    def test_submit_media_and_list_backend_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            submit_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "--runtime-mode",
                "online",
                "submit-media",
                "--media-path",
                "/tmp/long.mp4",
                "--duration-sec",
                "1800",
                "--size-bytes",
                str(300 * 1024 * 1024),
            ]
            with patch("sys.argv", submit_argv):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    client_api.main()
            submit_payload = json.loads(buf.getvalue())
            self.assertEqual(submit_payload["result"]["route"], "backend")

            list_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "backend-jobs",
            ]
            with patch("sys.argv", list_argv):
                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    client_api.main()
            jobs_payload = json.loads(buf2.getvalue())
            self.assertEqual(len(jobs_payload), 1)


if __name__ == "__main__":
    unittest.main()
