import tempfile
import unittest
from pathlib import Path

from ela_pipeline.client_storage import LocalSQLiteRepository


class LocalSQLiteRepositoryTests(unittest.TestCase):
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

            repo.update_backend_job_status("job-1", "processing")
            processing = repo.list_backend_jobs(status="processing")
            self.assertEqual(len(processing), 1)
            self.assertEqual(processing[0]["id"], "job-1")


if __name__ == "__main__":
    unittest.main()
