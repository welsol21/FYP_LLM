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
                "--project-id",
                "proj-1",
            ]
            repo = LocalSQLiteRepository(db_path)
            repo.create_project("Project A", project_id="proj-1")
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
            job_id = jobs_payload[0]["id"]

            status_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "backend-job-status",
                "--job-id",
                job_id,
            ]
            with patch("sys.argv", status_argv):
                buf3 = io.StringIO()
                with redirect_stdout(buf3):
                    client_api.main()
            status_payload = json.loads(buf3.getvalue())
            self.assertEqual(status_payload["job_id"], job_id)
            self.assertEqual(status_payload["status"], "queued")

            resume_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "resume-backend-jobs",
            ]
            with patch("sys.argv", resume_argv):
                buf4 = io.StringIO()
                with redirect_stdout(buf4):
                    client_api.main()
            resume_payload = json.loads(buf4.getvalue())
            self.assertEqual(resume_payload["resumed_count"], 1)
            self.assertEqual(resume_payload["jobs"][0]["job_id"], job_id)

            repo = LocalSQLiteRepository(db_path)
            repo.update_backend_job_status(job_id, "failed")
            retry_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "retry-backend-job",
                "--job-id",
                job_id,
            ]
            with patch("sys.argv", retry_argv):
                buf5 = io.StringIO()
                with redirect_stdout(buf5):
                    client_api.main()
            retry_payload = json.loads(buf5.getvalue())
            self.assertEqual(retry_payload["status"], "queued")

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

    def test_sync_backend_result_command(self):
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
            repo.enqueue_backend_job(
                job_id="job-1",
                project_id="proj-1",
                media_file_id="file-1",
                request_payload={"media_path": "/tmp/lesson.mp3"},
            )
            result_json = Path(tmpdir) / "backend_result.json"
            result_json.write_text(
                json.dumps(
                    {
                        "document": {
                            "id": "doc-1",
                            "project_id": "proj-1",
                            "media_file_id": "file-1",
                            "source_type": "audio",
                            "source_path": "/tmp/lesson.mp3",
                            "media_hash": "mh-1",
                            "full_text": "She trusted him.",
                            "text_hash": "th-1",
                            "text_version": 1,
                        },
                        "media_sentences": [{"sentence_idx": 0, "sentence_text": "She trusted him."}],
                        "contract_sentences": [
                            {
                                "sentence_idx": 0,
                                "sentence_node": {
                                    "type": "Sentence",
                                    "node_id": "s1",
                                    "content": "She trusted him.",
                                    "linguistic_elements": [],
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            sync_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "sync-backend-result",
                "--job-id",
                "job-1",
                "--result-json",
                str(result_json),
            ]
            with patch("sys.argv", sync_argv):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    client_api.main()
            synced = json.loads(buf.getvalue())
            self.assertEqual(synced["status"], "completed")
            self.assertEqual(synced["document_id"], "doc-1")

            status_argv = [
                "client_api",
                "--db-path",
                str(db_path),
                "document-processing-status",
                "--document-id",
                "doc-1",
            ]
            with patch("sys.argv", status_argv):
                buf2 = io.StringIO()
                with redirect_stdout(buf2):
                    client_api.main()
            status = json.loads(buf2.getvalue())
            self.assertEqual(status["status"], "completed")


if __name__ == "__main__":
    unittest.main()
