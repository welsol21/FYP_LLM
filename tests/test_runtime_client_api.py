import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.client_storage import LocalSQLiteRepository, build_sentence_hash
from ela_pipeline.runtime import client_api


class RuntimeClientAPITests(unittest.TestCase):
    def test_project_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"

            create_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "create-project",
                "--name",
                "Project A",
            ]
            with patch("sys.argv", create_argv):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    client_api.main()
            created = json.loads(buf.getvalue())
            self.assertEqual(created["name"], "Project A")

            list_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "projects",
            ]
            with patch("sys.argv", list_argv):
                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    client_api.main()
            listed = json.loads(buf2.getvalue())
            self.assertEqual(len(listed), 1)

            selected_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "selected-project",
            ]
            with patch("sys.argv", selected_argv):
                buf3 = io.StringIO()
                with redirect_stdout(buf3):
                    client_api.main()
            selected = json.loads(buf3.getvalue())
            self.assertEqual(selected["project_id"], created["id"])

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

    def test_submit_media_local_processing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            media_path = Path(tmpdir) / "short.txt"
            media_path.write_text("She trusted him.", encoding="utf-8")
            submit_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "--runtime-mode",
                "online",
                "submit-media",
                "--media-path",
                str(media_path),
                "--duration-sec",
                "60",
                "--size-bytes",
                "1024",
                "--project-id",
                "proj-1",
            ]
            repo = LocalSQLiteRepository(db_path)
            repo.create_project("Project A", project_id="proj-1")
            class _Resp:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return b'{"sentence_text":"She trusted him.","sentence_hash":"h1","sentence_node":{"type":"Sentence","content":"She trusted him.","node_id":"n1","linguistic_elements":[]}}'

            with patch.dict("os.environ", {"ELA_SENTENCE_CONTRACT_BACKEND_URL": "http://backend.local"}, clear=False):
                with patch("ela_pipeline.runtime.service.urlrequest.urlopen", return_value=_Resp()):
                    with patch("sys.argv", submit_argv):
                        buf = io.StringIO()
                        with redirect_stdout(buf):
                            client_api.main()
            submit_payload = json.loads(buf.getvalue())
            self.assertEqual(submit_payload["result"]["route"], "local")

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
            self.assertIn("She trusted him.", viz_payload)
            self.assertEqual(viz_payload["She trusted him."]["node_id"], "s1")

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

    def test_document_scoped_visualizer_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            repo = LocalSQLiteRepository(db_path)
            repo.create_project("Project A", project_id="proj-1")
            repo.create_media_file(
                project_id="proj-1",
                media_file_id="file-1",
                name="lesson.mp3",
                path="/tmp/lesson.mp3",
            )
            repo.create_document(
                document_id="doc-1",
                project_id="proj-1",
                media_file_id="file-1",
                source_type="audio",
                source_path="/tmp/lesson.mp3",
                media_hash="mh-1",
                status="completed",
            )
            h0 = build_sentence_hash("She trusted him.", 0)
            repo.replace_media_sentences(
                document_id="doc-1",
                sentences=[
                    {
                        "sentence_idx": 0,
                        "sentence_text": "She trusted him.",
                        "start_ms": 100,
                        "end_ms": 900,
                        "sentence_hash": h0,
                    }
                ],
            )
            repo.upsert_contract_sentence(
                document_id="doc-1",
                sentence_hash=h0,
                sentence_node={"type": "Sentence", "node_id": "s1", "content": "She trusted him.", "linguistic_elements": []},
            )
            repo.replace_sentence_links(
                document_id="doc-1",
                links=[{"sentence_idx": 0, "sentence_hash": h0}],
            )

            payload_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "visualizer-payload-document",
                "--document-id",
                "doc-1",
            ]
            with patch("sys.argv", payload_argv):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    client_api.main()
            payload = json.loads(buf.getvalue())
            self.assertIn("She trusted him.", payload)
            self.assertEqual(payload["She trusted him."]["node_id"], "s1")

            rows_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "document-sentences",
                "--document-id",
                "doc-1",
            ]
            with patch("sys.argv", rows_argv):
                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    client_api.main()
            rows = json.loads(buf2.getvalue())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["sentence_idx"], 0)
            self.assertEqual(rows[0]["sentence_hash"], h0)

            status_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "document-processing-status",
                "--document-id",
                "doc-1",
            ]
            with patch("sys.argv", status_argv):
                buf3 = io.StringIO()
                with redirect_stdout(buf3):
                    client_api.main()
            status = json.loads(buf3.getvalue())
            self.assertEqual(status["document_id"], "doc-1")
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["media_sentences_count"], 1)
            self.assertEqual(status["contract_sentences_count"], 1)

    def test_sentence_contract_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "sentence-contract",
                "--sentence-text",
                "Although she had been warned several times, she still chose to ignore the evidence.",
                "--sentence-idx",
                "2",
            ]
            with patch("sys.argv", argv):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    client_api.main()
            payload = json.loads(buf.getvalue())
            self.assertIn("sentence_hash", payload)
            self.assertEqual(payload["sentence_node"]["type"], "Sentence")
            self.assertIsInstance(payload["sentence_node"].get("linguistic_notes"), list)


if __name__ == "__main__":
    unittest.main()
