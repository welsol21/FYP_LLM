import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.runtime import MediaPolicyLimits, RuntimeMediaService
from ela_pipeline.client_storage import build_sentence_hash


class RuntimeMediaServiceTests(unittest.TestCase):
    def test_projects_create_select_and_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            created = svc.create_project(name="Project A")
            self.assertEqual(created["name"], "Project A")
            listed = svc.list_projects()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], created["id"])
            selected = svc.get_selected_project()
            self.assertEqual(selected["project_id"], created["id"])
            switched = svc.set_selected_project(project_id=created["id"])
            self.assertEqual(switched["project_name"], "Project A")

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
            svc.repo.create_project("Project A", project_id="proj-1")
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
            polled = svc.get_backend_job_status(job_id=jobs[0]["id"])
            self.assertEqual(polled["status"], "queued")

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

    def test_submit_media_rejects_without_selected_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            response = svc.submit_media(
                media_path="/tmp/short.mp3",
                duration_seconds=300,
                size_bytes=80 * 1024 * 1024,
            )
            self.assertEqual(response["result"]["route"], "reject")
            self.assertIn("project", response["result"]["message"].lower())

    def test_service_respects_deployment_mode_for_phonetic_policy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"ELA_PHONETIC_POLICY": "backend_only"}, clear=False):
                local_svc = RuntimeMediaService(
                    db_path=Path(tmpdir) / "client.sqlite3",
                    runtime_mode="online",
                    deployment_mode="local",
                    limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
                )
                backend_svc = RuntimeMediaService(
                    db_path=Path(tmpdir) / "client2.sqlite3",
                    runtime_mode="online",
                    deployment_mode="backend",
                    limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
                )
            self.assertFalse(local_svc.caps.phonetic_enabled)
            self.assertTrue(backend_svc.caps.phonetic_enabled)

    def test_document_visualizer_payload_and_sentence_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            svc.repo.create_project("Project A", project_id="proj-1")
            svc.repo.create_media_file(
                project_id="proj-1",
                media_file_id="file-1",
                name="lesson.mp3",
                path="/tmp/lesson.mp3",
            )
            svc.repo.create_document(
                document_id="doc-1",
                project_id="proj-1",
                media_file_id="file-1",
                source_type="audio",
                source_path="/tmp/lesson.mp3",
                media_hash="mh-1",
                status="completed",
            )
            h0 = build_sentence_hash("She trusted him.", 0)
            h1 = build_sentence_hash("She trusted him.", 1)
            svc.repo.replace_media_sentences(
                document_id="doc-1",
                sentences=[
                    {
                        "sentence_idx": 0,
                        "sentence_text": "She trusted him.",
                        "start_ms": 100,
                        "end_ms": 900,
                        "sentence_hash": h0,
                    },
                    {
                        "sentence_idx": 1,
                        "sentence_text": "She trusted him.",
                        "start_ms": 901,
                        "end_ms": 1800,
                        "sentence_hash": h1,
                    },
                ],
            )
            svc.repo.upsert_contract_sentence(
                document_id="doc-1",
                sentence_hash=h0,
                sentence_node={"type": "Sentence", "content": "She trusted him.", "node_id": "s1", "linguistic_elements": []},
            )
            svc.repo.upsert_contract_sentence(
                document_id="doc-1",
                sentence_hash=h1,
                sentence_node={"type": "Sentence", "content": "She trusted him.", "node_id": "s2", "linguistic_elements": []},
            )
            svc.repo.replace_sentence_links(
                document_id="doc-1",
                links=[
                    {"sentence_idx": 0, "sentence_hash": h0},
                    {"sentence_idx": 1, "sentence_hash": h1},
                ],
            )

            sentence_rows = svc.list_document_sentences(document_id="doc-1")
            self.assertEqual(len(sentence_rows), 2)
            self.assertEqual(sentence_rows[0]["sentence_idx"], 0)
            self.assertEqual(sentence_rows[1]["sentence_idx"], 1)

            payload = svc.get_visualizer_payload(document_id="doc-1")
            self.assertEqual(len(payload), 2)
            self.assertIn("She trusted him.", payload)
            self.assertIn("She trusted him. #2", payload)
            self.assertEqual(payload["She trusted him."]["node_id"], "s1")
            self.assertEqual(payload["She trusted him. #2"]["node_id"], "s2")

    def test_document_processing_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            svc.repo.create_project("Project A", project_id="proj-1")
            svc.repo.create_media_file(
                project_id="proj-1",
                media_file_id="file-1",
                name="lesson.mp3",
                path="/tmp/lesson.mp3",
            )
            svc.repo.create_document(
                document_id="doc-1",
                project_id="proj-1",
                media_file_id="file-1",
                source_type="audio",
                source_path="/tmp/lesson.mp3",
                media_hash="mh-1",
                status="processing",
            )
            h0 = build_sentence_hash("She trusted him.", 0)
            svc.repo.replace_media_sentences(
                document_id="doc-1",
                sentences=[{"sentence_idx": 0, "sentence_text": "She trusted him.", "sentence_hash": h0}],
            )
            svc.repo.upsert_contract_sentence(
                document_id="doc-1",
                sentence_hash=h0,
                sentence_node={"type": "Sentence", "node_id": "s1", "content": "She trusted him.", "linguistic_elements": []},
            )
            svc.repo.replace_sentence_links(
                document_id="doc-1",
                links=[{"sentence_idx": 0, "sentence_hash": h0}],
            )
            svc.repo.enqueue_backend_job(
                job_id="job-1",
                project_id="proj-1",
                media_file_id="file-1",
                request_payload={"media_path": "/tmp/lesson.mp3"},
            )
            svc.repo.update_backend_job_status("job-1", "processing")

            status = svc.get_document_processing_status(document_id="doc-1")
            self.assertEqual(status["document_id"], "doc-1")
            self.assertEqual(status["status"], "processing")
            self.assertEqual(status["media_sentences_count"], 1)
            self.assertEqual(status["contract_sentences_count"], 1)
            self.assertEqual(status["linked_sentences_count"], 1)
            self.assertIsNotNone(status["latest_backend_job"])
            self.assertEqual(status["latest_backend_job"]["job_id"], "job-1")

            missing = svc.get_document_processing_status(document_id="missing-doc")
            self.assertEqual(missing["document_id"], "missing-doc")
            self.assertEqual(missing["status"], "not_found")

    def test_retry_and_resume_backend_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            job = svc.repo.enqueue_backend_job(
                job_id="job-1",
                project_id="proj-1",
                media_file_id="file-1",
                request_payload={"media_path": "/tmp/long.mp4"},
            )
            self.assertEqual(job["status"], "queued")

            resumed = svc.resume_backend_jobs()
            self.assertEqual(resumed["resumed_count"], 1)
            self.assertEqual(resumed["jobs"][0]["job_id"], "job-1")

            svc.repo.update_backend_job_status("job-1", "failed")
            retry = svc.retry_backend_job(job_id="job-1")
            self.assertEqual(retry["status"], "queued")

            svc.repo.update_backend_job_status("job-1", "processing")
            retry_blocked = svc.retry_backend_job(job_id="job-1")
            self.assertEqual(retry_blocked["status"], "processing")

    def test_sync_backend_result_materializes_document_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            svc.repo.create_project("Project A", project_id="proj-1")
            svc.repo.create_media_file(
                project_id="proj-1",
                media_file_id="file-1",
                name="lesson.mp3",
                path="/tmp/lesson.mp3",
            )
            svc.repo.enqueue_backend_job(
                job_id="job-1",
                project_id="proj-1",
                media_file_id="file-1",
                request_payload={"media_path": "/tmp/lesson.mp3"},
            )
            backend_result = {
                "document": {
                    "id": "doc-1",
                    "project_id": "proj-1",
                    "media_file_id": "file-1",
                    "source_type": "audio",
                    "source_path": "/tmp/lesson.mp3",
                    "media_hash": "mh-1",
                    "full_text": "She trusted him. Before making the decision.",
                    "text_hash": "th-1",
                    "text_version": 1,
                },
                "media_sentences": [
                    {"sentence_idx": 0, "sentence_text": "She trusted him.", "start_ms": 100, "end_ms": 800},
                    {"sentence_idx": 1, "sentence_text": "Before making the decision.", "start_ms": 801, "end_ms": 1400},
                ],
                "contract_sentences": [
                    {
                        "sentence_idx": 0,
                        "sentence_node": {
                            "type": "Sentence",
                            "node_id": "s1",
                            "content": "She trusted him.",
                            "linguistic_elements": [],
                        },
                    },
                    {
                        "sentence_idx": 1,
                        "sentence_node": {
                            "type": "Sentence",
                            "node_id": "s2",
                            "content": "Before making the decision.",
                            "linguistic_elements": [],
                        },
                    },
                ],
            }

            synced = svc.sync_backend_result(job_id="job-1", result=backend_result)
            self.assertEqual(synced["status"], "completed")
            self.assertEqual(synced["document_id"], "doc-1")
            self.assertEqual(synced["media_sentences_count"], 2)
            self.assertEqual(synced["contract_sentences_count"], 2)
            self.assertEqual(synced["linked_sentences_count"], 2)

            doc_status = svc.get_document_processing_status(document_id="doc-1")
            self.assertEqual(doc_status["status"], "completed")
            self.assertEqual(doc_status["media_sentences_count"], 2)
            self.assertEqual(doc_status["contract_sentences_count"], 2)
            self.assertEqual(doc_status["latest_backend_job"]["status"], "completed")

            payload = svc.get_visualizer_payload(document_id="doc-1")
            self.assertEqual(len(payload), 2)
            self.assertIn("She trusted him.", payload)
            self.assertIn("Before making the decision.", payload)


if __name__ == "__main__":
    unittest.main()
