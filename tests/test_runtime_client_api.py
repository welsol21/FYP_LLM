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

    def test_visualizer_payload_and_apply_edit_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            input_json = Path(tmpdir) / "input.json"
            output_json = Path(tmpdir) / "output.json"
            input_doc = {
                "She trusted him.": {
                    "type": "Sentence",
                    "node_id": "s1",
                    "content": "She trusted him.",
                    "linguistic_elements": [
                        {
                            "type": "Phrase",
                            "node_id": "p1",
                            "content": "trusted him",
                            "notes": [{"text": "old"}],
                            "linguistic_elements": [],
                        }
                    ],
                }
            }
            input_json.write_text(json.dumps(input_doc), encoding="utf-8")

            viz_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "visualizer-payload",
                "--input-json",
                str(input_json),
            ]
            with patch("sys.argv", viz_argv):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    client_api.main()
            viz_payload = json.loads(buf.getvalue())
            self.assertEqual(len(viz_payload), 1)
            self.assertEqual(viz_payload[0]["tree"]["node_id"], "s1")

            edit_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "apply-edit",
                "--input-json",
                str(input_json),
                "--output-json",
                str(output_json),
                "--sentence-text",
                "She trusted him.",
                "--node-id",
                "p1",
                "--field-path",
                "notes[0].text",
                "--new-value-json",
                "\"new\"",
            ]
            with patch("sys.argv", edit_argv):
                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    client_api.main()
            result = json.loads(buf2.getvalue())
            self.assertEqual(result["status"], "ok")
            saved = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(saved["She trusted him."]["linguistic_elements"][0]["notes"][0]["text"], "new")


if __name__ == "__main__":
    unittest.main()
