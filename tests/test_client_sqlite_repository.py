import tempfile
import unittest
from pathlib import Path

from ela_pipeline.client_storage import LocalSQLiteRepository, build_sentence_hash


class LocalSQLiteRepositoryTests(unittest.TestCase):
    def test_sentence_hash_is_deterministic_and_index_sensitive(self):
        h1 = build_sentence_hash("She should have trusted her instincts.", 0)
        h2 = build_sentence_hash("She should   have trusted her instincts.", 0)
        h3 = build_sentence_hash("She should have trusted her instincts.", 1)
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_projects_and_files_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            repo = LocalSQLiteRepository(db_path)

            project = repo.create_project("Project A", project_id="proj-1")
            self.assertEqual(project["id"], "proj-1")

            media = repo.create_media_file(
                project_id="proj-1",
                media_file_id="file-1",
                name="lesson.mp3",
                path="/tmp/lesson.mp3",
                duration_seconds=120,
                size_bytes=1_024_000,
            )
            self.assertEqual(media["id"], "file-1")

            projects = repo.list_projects()
            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0]["name"], "Project A")

            files = repo.list_media_files("proj-1")
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["name"], "lesson.mp3")
            self.assertEqual(files[0]["duration_seconds"], 120)
            self.assertEqual(files[0]["size_bytes"], 1_024_000)

    def test_workspace_state_upsert_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            repo = LocalSQLiteRepository(db_path)

            repo.set_workspace_state("ui:last_project", {"project_id": "p1"})
            row = repo.get_workspace_state("ui:last_project")
            self.assertEqual(row, {"project_id": "p1"})

            repo.set_workspace_state("ui:last_project", {"project_id": "p2"})
            row_updated = repo.get_workspace_state("ui:last_project")
            self.assertEqual(row_updated, {"project_id": "p2"})

    def test_local_edits_roundtrip_and_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            repo = LocalSQLiteRepository(db_path)

            edit_id_1 = repo.add_local_edit(
                sentence_key="s1",
                node_id="w1",
                field_path="cefr_level",
                before_value="A2",
                after_value="B1",
            )
            edit_id_2 = repo.add_local_edit(
                sentence_key="s2",
                node_id="w2",
                field_path="notes[0].text",
                before_value="old",
                after_value="new",
            )

            self.assertGreater(edit_id_1, 0)
            self.assertGreater(edit_id_2, edit_id_1)

            s1_rows = repo.list_local_edits(sentence_key="s1")
            self.assertEqual(len(s1_rows), 1)
            self.assertEqual(s1_rows[0]["after_value"], "B1")

            limited = repo.list_local_edits(limit=1)
            self.assertEqual(len(limited), 1)
            self.assertEqual(limited[0]["sentence_key"], "s2")

    def test_backend_job_queue_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            repo = LocalSQLiteRepository(db_path)

            job = repo.enqueue_backend_job(
                job_id="job-1",
                project_id="proj-1",
                media_file_id="file-1",
                request_payload={"media_path": "/tmp/large.mp4", "duration_seconds": 1800},
            )
            self.assertEqual(job["id"], "job-1")
            self.assertEqual(job["status"], "queued")

            queued = repo.list_backend_jobs(status="queued")
            self.assertEqual(len(queued), 1)
            self.assertEqual(queued[0]["id"], "job-1")
            one = repo.get_backend_job("job-1")
            self.assertIsNotNone(one)
            assert one is not None
            self.assertEqual(one["status"], "queued")

            repo.update_backend_job_status("job-1", "processing")
            processing = repo.list_backend_jobs(status="processing")
            self.assertEqual(len(processing), 1)
            self.assertEqual(processing[0]["id"], "job-1")
            resumable = repo.list_resumable_backend_jobs()
            self.assertEqual(len(resumable), 1)
            self.assertEqual(resumable[0]["id"], "job-1")

            repo.update_backend_job_status("job-1", "failed")
            retried = repo.retry_backend_job("job-1")
            self.assertIsNotNone(retried)
            assert retried is not None
            self.assertEqual(retried["status"], "queued")

    def test_sync_requests_queue_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "client.sqlite3"
            repo = LocalSQLiteRepository(db_path)

            queued = repo.enqueue_sync_request(
                request_id="sync-1",
                request_type="missing_content",
                payload={"source_text": "Hello world."},
            )
            self.assertEqual(queued["id"], "sync-1")
            self.assertEqual(queued["status"], "queued")

            rows = repo.list_sync_requests(status="queued")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], "sync-1")

            repo.update_sync_request_status("sync-1", "sent")
            sent = repo.list_sync_requests(status="sent")
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]["id"], "sync-1")

    def test_documents_and_visualizer_rows_roundtrip(self):
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
            doc = repo.create_document(
                document_id="doc-1",
                project_id="proj-1",
                media_file_id="file-1",
                source_type="audio",
                source_path="/tmp/lesson.mp3",
                media_hash="mh-1",
                status="completed",
            )
            self.assertEqual(doc["id"], "doc-1")

            repo.upsert_document_text(
                document_id="doc-1",
                full_text="She should have trusted her instincts. Before making the decision.",
                text_hash="th-1",
                version=1,
            )

            hash_0 = build_sentence_hash("She should have trusted her instincts.", 0)
            hash_1 = build_sentence_hash("Before making the decision.", 1)
            repo.replace_media_sentences(
                document_id="doc-1",
                sentences=[
                    {
                        "sentence_idx": 0,
                        "sentence_text": "She should have trusted her instincts.",
                        "start_ms": 1000,
                        "end_ms": 2400,
                        "page_no": None,
                        "char_start": None,
                        "char_end": None,
                        "sentence_hash": hash_0,
                    },
                    {
                        "sentence_idx": 1,
                        "sentence_text": "Before making the decision.",
                        "start_ms": 2401,
                        "end_ms": 3200,
                        "page_no": None,
                        "char_start": None,
                        "char_end": None,
                        "sentence_hash": hash_1,
                    },
                ],
            )
            repo.upsert_contract_sentence(
                document_id="doc-1",
                sentence_hash=hash_0,
                sentence_node={"type": "Sentence", "content": "She should have trusted her instincts."},
            )
            repo.upsert_contract_sentence(
                document_id="doc-1",
                sentence_hash=hash_1,
                sentence_node={"type": "Sentence", "content": "Before making the decision."},
            )
            repo.replace_sentence_links(
                document_id="doc-1",
                links=[
                    {"sentence_idx": 0, "sentence_hash": hash_0},
                    {"sentence_idx": 1, "sentence_hash": hash_1},
                ],
            )

            rows = repo.list_document_visualizer_rows(document_id="doc-1")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["sentence_idx"], 0)
            self.assertEqual(rows[0]["sentence_text"], "She should have trusted her instincts.")
            self.assertEqual(rows[0]["sentence_node"]["type"], "Sentence")
            self.assertEqual(rows[1]["sentence_idx"], 1)
            self.assertEqual(rows[1]["sentence_hash"], hash_1)

    def test_document_processing_status_includes_counts_and_latest_job(self):
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
                status="processing",
            )
            repo.upsert_document_text(
                document_id="doc-1",
                full_text="She trusted him.",
                text_hash="th-1",
                version=2,
            )
            h0 = build_sentence_hash("She trusted him.", 0)
            repo.replace_media_sentences(
                document_id="doc-1",
                sentences=[
                    {
                        "sentence_idx": 0,
                        "sentence_text": "She trusted him.",
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
            repo.enqueue_backend_job(
                job_id="job-1",
                project_id="proj-1",
                media_file_id="file-1",
                request_payload={"media_path": "/tmp/lesson.mp3"},
            )
            repo.update_backend_job_status("job-1", "processing")

            status = repo.get_document_processing_status(document_id="doc-1")
            self.assertIsNotNone(status)
            assert status is not None
            self.assertEqual(status["document_id"], "doc-1")
            self.assertEqual(status["status"], "processing")
            self.assertEqual(status["text_present"], True)
            self.assertEqual(status["text_version"], 2)
            self.assertEqual(status["media_sentences_count"], 1)
            self.assertEqual(status["contract_sentences_count"], 1)
            self.assertEqual(status["linked_sentences_count"], 1)
            self.assertIsNotNone(status["latest_backend_job"])
            self.assertEqual(status["latest_backend_job"]["job_id"], "job-1")
            self.assertEqual(status["latest_backend_job"]["status"], "processing")


if __name__ == "__main__":
    unittest.main()
