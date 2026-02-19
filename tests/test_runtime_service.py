import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ela_pipeline.runtime import MediaPolicyLimits, RuntimeMediaService
from ela_pipeline.client_storage import build_sentence_hash


class RuntimeMediaServiceTests(unittest.TestCase):
    def test_translation_config_defaults_and_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            cfg = svc.get_translation_config()
            self.assertEqual(cfg["default_provider"], "m2m100")
            provider_ids = {row["id"] for row in cfg["providers"]}
            self.assertIn("m2m100", provider_ids)
            self.assertIn("gpt", provider_ids)

            saved = svc.save_translation_config(
                {
                    "default_provider": "gpt",
                    "providers": cfg["providers"]
                    + [
                        {
                            "id": "myapi",
                            "label": "My API",
                            "kind": "custom",
                            "enabled": True,
                            "credential_fields": ["token"],
                            "credentials": {"token": "abc"},
                        }
                    ],
                }
            )
            self.assertEqual(saved["default_provider"], "gpt")
            self.assertIn("myapi", {row["id"] for row in saved["providers"]})

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
            self.assertNotIn("backend_jobs", ui_state["features"])

    def test_submit_media_local_processing_and_feedback_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "short.txt"
            media_path.write_text("She trusted him.", encoding="utf-8")
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            svc.repo.create_project("Project A", project_id="proj-1")
            with patch.object(
                svc,
                "_request_sentence_contract",
                return_value={
                    "sentence_text": "She trusted him.",
                    "sentence_hash": "h1",
                    "sentence_node": {
                        "type": "Sentence",
                        "content": "She trusted him.",
                        "node_id": "n1",
                        "linguistic_elements": [],
                    },
                },
            ):
                response = svc.submit_media(
                    media_path=str(media_path),
                    duration_seconds=60,
                    size_bytes=1024,
                    project_id="proj-1",
                )
            self.assertEqual(response["result"]["route"], "local")
            self.assertEqual(response["ui_feedback"]["severity"], "info")
            self.assertEqual(response["result"]["status"], "completed_local")

    def test_process_media_now_persists_media_contract_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "short.txt"
            media_path.write_text("She trusted him.", encoding="utf-8")
            artifacts_dir = Path(tmpdir) / "contracts"
            with patch.dict(
                "os.environ",
                {
                    "MEDIA_CONTRACT_ARTIFACTS_DIR": str(artifacts_dir),
                },
                clear=False,
            ):
                svc = RuntimeMediaService(
                    db_path=Path(tmpdir) / "client.sqlite3",
                    runtime_mode="online",
                    limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
                )
                svc.repo.create_project("Project A", project_id="proj-1")
                with patch.object(
                    svc,
                    "_request_sentence_contract",
                    return_value={
                        "sentence_text": "She trusted him.",
                        "sentence_hash": "h1",
                        "sentence_node": {
                            "type": "Sentence",
                            "content": "She trusted him.",
                            "node_id": "n1",
                            "translation": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."},
                            "linguistic_elements": [],
                        },
                    },
                ):
                    result = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                    )
            self.assertEqual(result["status"], "completed")
            doc_dir = artifacts_dir / result["document_id"]
            self.assertTrue((doc_dir / "full_text.txt").exists())
            self.assertTrue((doc_dir / "media_contract.json").exists())
            self.assertTrue((doc_dir / "contract_sentences.json").exists())
            self.assertTrue((doc_dir / "sentence_link.json").exists())
            self.assertTrue((doc_dir / "semantic_units_runtime.json").exists())
            self.assertTrue((doc_dir / "bilingual_objects_runtime.json").exists())
            self.assertTrue((doc_dir / "subtitles_en.srt").exists())
            self.assertTrue((doc_dir / "subtitles_bilingual.srt").exists())
            bilingual_srt = (doc_dir / "subtitles_bilingual.srt").read_text(encoding="utf-8")
            self.assertIn("She trusted him.", bilingual_srt)
            self.assertIn("Она доверяла ему.", bilingual_srt)

    def test_submit_media_reject_returns_error_feedback(self):
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
            )
            self.assertEqual(response["result"]["route"], "reject")
            self.assertEqual(response["ui_feedback"]["severity"], "error")

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
            status = svc.get_document_processing_status(document_id="doc-1")
            self.assertEqual(status["document_id"], "doc-1")
            self.assertEqual(status["status"], "processing")
            self.assertEqual(status["media_sentences_count"], 1)
            self.assertEqual(status["contract_sentences_count"], 1)
            self.assertEqual(status["linked_sentences_count"], 1)
            self.assertIsNone(status["latest_backend_job"])

            missing = svc.get_document_processing_status(document_id="missing-doc")
            self.assertEqual(missing["document_id"], "missing-doc")
            self.assertEqual(missing["status"], "not_found")

    def test_build_sentence_contract_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            payload = svc.build_sentence_contract(
                sentence_text="She should have trusted her instincts before making the decision.",
                sentence_idx=3,
            )
            self.assertEqual(payload["sentence_text"], "She should have trusted her instincts before making the decision.")
            self.assertTrue(payload["sentence_hash"])
            node = payload["sentence_node"]
            self.assertEqual(node["type"], "Sentence")
            self.assertIsInstance(node.get("linguistic_notes"), list)
            self.assertIn("translation", node)

    def test_request_sentence_contract_uses_backend_endpoint_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"ELA_SENTENCE_CONTRACT_BACKEND_URL": "http://backend.local"}, clear=False):
                svc = RuntimeMediaService(
                    db_path=Path(tmpdir) / "client.sqlite3",
                    runtime_mode="online",
                    limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
                )

            class _Resp:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return b'{"sentence_text":"She trusted him.","sentence_hash":"h1","sentence_node":{"type":"Sentence","content":"She trusted him.","node_id":"n1","linguistic_elements":[]}}'

            with patch("ela_pipeline.runtime.service.urlrequest.urlopen", return_value=_Resp()) as mocked:
                payload = svc._request_sentence_contract(sentence_text="She trusted him.", sentence_idx=0)
            self.assertEqual(payload["sentence_hash"], "h1")
            called_req = mocked.call_args.args[0]
            self.assertIn("/api/sentence-contract", called_req.full_url)

    def test_request_sentence_contract_raises_when_backend_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"ELA_SENTENCE_CONTRACT_BACKEND_URL": "http://backend.local"}, clear=False):
                svc = RuntimeMediaService(
                    db_path=Path(tmpdir) / "client.sqlite3",
                    runtime_mode="online",
                    limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
                )
            with patch("ela_pipeline.runtime.service.urlrequest.urlopen", side_effect=OSError("offline")):
                with self.assertRaisesRegex(RuntimeError, "Backend sentence-contract API unavailable"):
                    svc._request_sentence_contract(sentence_text="She trusted him.", sentence_idx=0)

    def test_request_sentence_contract_raises_when_backend_url_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"ELA_SENTENCE_CONTRACT_BACKEND_URL": ""}, clear=False):
                svc = RuntimeMediaService(
                    db_path=Path(tmpdir) / "client.sqlite3",
                    runtime_mode="online",
                    limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
                )
            with self.assertRaisesRegex(RuntimeError, "ELA_SENTENCE_CONTRACT_BACKEND_URL is required"):
                svc._request_sentence_contract(sentence_text="She trusted him.", sentence_idx=0)


if __name__ == "__main__":
    unittest.main()
