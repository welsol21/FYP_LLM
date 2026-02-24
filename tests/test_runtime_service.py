import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from ela_pipeline.runtime import MediaPolicyLimits, RuntimeMediaService
from ela_pipeline.client_storage import build_sentence_hash
from ela_pipeline.runtime.media_pipeline import MediaPipelineResult
from ela_pipeline.runtime.service import TRANSLATION_CONFIG_STATE_KEY


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

    def test_register_media_file_is_idempotent_by_project_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            svc.repo.create_project("Project A", project_id="proj-1")

            first = svc.register_media_file(
                project_id="proj-1",
                name="01.Intro.mp3",
                media_path="artifacts/media_tmp/uploads/01.Intro.mp3",
                size_bytes=1111,
                duration_seconds=10,
            )
            second = svc.register_media_file(
                project_id="proj-1",
                name="01.Intro.mp3",
                media_path="artifacts/media_tmp/uploads/01.Intro.mp3",
                size_bytes=2222,
                duration_seconds=11,
            )

            self.assertEqual(first["id"], second["id"])
            rows = svc.list_files(project_id="proj-1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["size_bytes"], 2222)
            self.assertEqual(rows[0]["duration_seconds"], 11)

    def test_cleanup_duplicate_media_files_removes_legacy_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            svc.repo.create_project("Project A", project_id="proj-1")
            with svc.repo._connect() as conn:  # legacy duplicate fixture
                conn.execute(
                    """
                    INSERT INTO media_files (
                        id, project_id, name, path, duration_seconds, size_bytes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("f1", "proj-1", "01.Intro.mp3", "artifacts/media_tmp/uploads/01.Intro.mp3", 10, 1000, "2026-02-19T00:00:00Z", "2026-02-19T00:00:00Z"),
                )
                conn.execute(
                    """
                    INSERT INTO media_files (
                        id, project_id, name, path, duration_seconds, size_bytes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("f2", "proj-1", "01.Intro.mp3", "artifacts/media_tmp/uploads/01.Intro.mp3", 11, 1001, "2026-02-19T00:01:00Z", "2026-02-19T00:01:00Z"),
                )
                conn.commit()
            removed = svc.repo.cleanup_duplicate_media_files()
            self.assertEqual(removed, 1)
            rows = svc.list_files(project_id="proj-1")
            self.assertEqual(len(rows), 1)

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
            svc.repo.set_workspace_state(
                TRANSLATION_CONFIG_STATE_KEY,
                {
                    "default_provider": "backend_m2m100",
                    "providers": [
                        {"id": "backend_m2m100", "enabled": True, "credentials": {}},
                        {"id": "gpt", "enabled": True, "credentials": {"api_key": "x"}},
                    ],
                },
            )
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
            archive_dir = Path(tmpdir) / "contracts_archive"
            with patch.dict(
                "os.environ",
                {
                    "MEDIA_CONTRACT_ARTIFACTS_DIR": str(artifacts_dir),
                    "MEDIA_CONTRACT_ARCHIVE_DIR": str(archive_dir),
                },
                clear=False,
            ):
                svc = RuntimeMediaService(
                    db_path=Path(tmpdir) / "client.sqlite3",
                    runtime_mode="online",
                    limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
                )
                svc.repo.create_project("Project A", project_id="proj-1")
                svc.repo.create_media_file(
                    project_id="proj-1",
                    media_file_id="file-1",
                    name="short.txt",
                    path=str(media_path),
                    duration_seconds=1,
                    size_bytes=media_path.stat().st_size,
                )
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
                            "translations": {
                                "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                            },
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
            snapshots = list((archive_dir / "unbound").glob(f"*_{result['document_id']}"))
            self.assertTrue(snapshots)
            self.assertTrue((snapshots[0] / "media_contract.json").exists())

    def test_non_default_provider_applies_ui_overlay_without_mutating_canonical_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "short.txt"
            media_path.write_text("She trusted him.", encoding="utf-8")
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            svc.repo.create_project("Project A", project_id="proj-1")
            svc.repo.set_workspace_state(
                TRANSLATION_CONFIG_STATE_KEY,
                {
                    "default_provider": "backend_m2m100",
                    "providers": [
                        {"id": "backend_m2m100", "enabled": True, "credentials": {}},
                        {"id": "gpt", "enabled": True, "credentials": {"api_key": "x"}},
                    ],
                },
            )
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
                        "translations": {
                            "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                        },
                        "linguistic_elements": [],
                    },
                },
            ):
                with patch("ela_pipeline.runtime.service.translate_text_with_provider", return_value="Клиентский перевод"):
                    result = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                        translation_provider="gpt",
                        provider_credentials={"api_key": "x"},
                    )

            self.assertEqual(result["status"], "completed")
            rows = svc.repo.list_document_visualizer_rows(document_id=result["document_id"])
            self.assertEqual(
                rows[0]["sentence_node"]["translations"]["backend_m2m100"]["text"],
                "Она доверяла ему.",
            )
            payload = svc.get_visualizer_payload(document_id=result["document_id"])
            sentence_node = payload["She trusted him."]
            self.assertEqual(
                sentence_node["translations"]["backend_m2m100"]["text"],
                "Она доверяла ему.",
            )
            overlay_values = [
                str(entry.get("text") or "")
                for key, entry in sentence_node["translations"].items()
                if key != "backend_m2m100" and isinstance(entry, dict)
            ]
            self.assertIn("Клиентский перевод", overlay_values)

    def test_visualizer_payload_falls_back_to_backend_translation_when_selected_missing(self):
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
                name="sample.txt",
                path="/tmp/sample.txt",
                duration_seconds=10,
                size_bytes=1024,
            )
            svc.repo.set_workspace_state(
                "media_file_settings:file-1",
                {"translation_provider": "deepl", "subtitles_mode": "bilingual", "voice_choice": "male"},
            )
            svc.repo.create_document(
                document_id="doc-1",
                project_id="proj-1",
                media_file_id="file-1",
                source_type="text",
                source_path="/tmp/sample.txt",
                media_hash="h",
                status="completed",
            )
            svc.repo.replace_media_sentences(
                document_id="doc-1",
                sentences=[
                    {
                        "sentence_idx": 0,
                        "sentence_text": "She trusted him.",
                        "sentence_hash": "h1",
                        "text_ru": "",
                    }
                ],
            )
            svc.repo.upsert_contract_sentence(
                document_id="doc-1",
                sentence_hash="h1",
                sentence_node={
                    "type": "Sentence",
                    "content": "She trusted him.",
                    "node_id": "n1",
                    "translations": {
                        "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                    },
                    "linguistic_elements": [],
                },
            )
            svc.repo.replace_sentence_links(
                document_id="doc-1",
                links=[{"sentence_idx": 0, "sentence_hash": "h1"}],
            )

            payload = svc.get_visualizer_payload(document_id="doc-1")
            sentence_node = payload["She trusted him."]
            self.assertEqual(sentence_node["translations"]["backend_m2m100"]["text"], "Она доверяла ему.")

    def test_export_final_media_artifacts_creates_audio_for_audio_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            doc_dir = Path(tmpdir) / "contracts" / "doc-1"
            doc_dir.mkdir(parents=True, exist_ok=True)
            src_audio = Path(tmpdir) / "sample.mp3"
            src_audio.write_bytes(b"fake")

            def _fake_run(cmd, **kwargs):
                out_path = Path(cmd[-1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"x" * 2048)
                return SimpleNamespace(returncode=0)

            class _FakeCommunicate:
                def __init__(self, text: str, voice: str):
                    self.text = text
                    self.voice = voice

                async def save(self, path: str) -> None:
                    Path(path).write_bytes(b"x" * 2048)

            fake_edge_tts = SimpleNamespace(Communicate=_FakeCommunicate)

            with patch.dict(sys.modules, {"edge_tts": fake_edge_tts}), patch(
                "ela_pipeline.runtime.service.subprocess.run", side_effect=_fake_run
            ), patch("ela_pipeline.runtime.service._probe_audio_duration_ms", return_value=800):
                svc._export_final_media_artifacts(
                    source_type="audio",
                    source_path=str(src_audio),
                    doc_dir=doc_dir,
                    media_sentences=[
                        {"text_ru": "Она доверяла ему.", "sentence_text": "She trusted him."},
                    ],
                )

            self.assertTrue((doc_dir / "translated_audio_ru.mp3").exists())
            self.assertTrue((doc_dir / "translated_video_ru.mp4").exists())

    def test_bilingual_subtitles_support_sequential_and_simultaneous_modes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = RuntimeMediaService(
                db_path=Path(tmpdir) / "client.sqlite3",
                runtime_mode="online",
                limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
            )
            src_audio = Path(tmpdir) / "sample.mp3"
            src_audio.write_bytes(b"fake")

            class _FakeCommunicate:
                def __init__(self, text: str, voice: str):
                    self.text = text
                    self.voice = voice

                async def save(self, path: str) -> None:
                    Path(path).write_bytes(b"x" * 2048)

            def _fake_run(cmd, **kwargs):
                out_path = Path(cmd[-1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"x" * 2048)
                return SimpleNamespace(returncode=0)

            fake_edge_tts = SimpleNamespace(Communicate=_FakeCommunicate)
            media_sentences = [
                {
                    "start_ms": 0,
                    "end_ms": 1000,
                    "text_ru": "Она доверяла ему.",
                    "sentence_text": "She trusted him.",
                }
            ]

            with patch.dict(sys.modules, {"edge_tts": fake_edge_tts}), patch(
                "ela_pipeline.runtime.service.subprocess.run", side_effect=_fake_run
            ), patch("ela_pipeline.runtime.service._probe_audio_duration_ms", return_value=800):
                seq_dir = Path(tmpdir) / "contracts" / "seq"
                seq_dir.mkdir(parents=True, exist_ok=True)
                svc._export_final_media_artifacts(
                    source_type="audio",
                    source_path=str(src_audio),
                    doc_dir=seq_dir,
                    media_sentences=media_sentences,
                    subtitles_mode="bilingual_sequential",
                )

                sim_dir = Path(tmpdir) / "contracts" / "sim"
                sim_dir.mkdir(parents=True, exist_ok=True)
                svc._export_final_media_artifacts(
                    source_type="audio",
                    source_path=str(src_audio),
                    doc_dir=sim_dir,
                    media_sentences=media_sentences,
                    subtitles_mode="bilingual_simultaneous",
                )

            seq_srt = (seq_dir / "subtitles_bilingual.srt").read_text(encoding="utf-8")
            sim_srt = (sim_dir / "subtitles_bilingual.srt").read_text(encoding="utf-8")
            self.assertGreaterEqual(seq_srt.count("-->"), 2)
            self.assertEqual(sim_srt.count("-->"), 1)

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
            body = json.loads(called_req.data.decode("utf-8"))
            self.assertEqual(body["sentenceText"], "She trusted him.")
            self.assertEqual(body["sentenceIdx"], 0)
            self.assertNotIn("translationProvider", body)
            self.assertNotIn("providerCredentials", body)

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

    def test_incremental_cache_hit_skips_media_pipeline(self):
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
                svc.repo.create_media_file(
                    project_id="proj-1",
                    media_file_id="file-1",
                    name="short.txt",
                    path=str(media_path),
                    duration_seconds=1,
                    size_bytes=media_path.stat().st_size,
                )
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
                            "translations": {
                                "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                            },
                            "linguistic_elements": [],
                        },
                    },
                ):
                    first = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                        media_file_id="file-1",
                    )
                self.assertEqual(first["status"], "completed")

                with patch("ela_pipeline.runtime.service.run_media_pipeline", side_effect=AssertionError("must not run on cache hit")):
                    second = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                        media_file_id="file-1",
                    )
                self.assertEqual(second["status"], "completed")

                manifest = svc.repo.get_workspace_state("media_stage_manifest:file:file-1")
                self.assertIsInstance(manifest, dict)
                self.assertTrue(bool(manifest.get("reused_immutable_last_run")))

    def test_force_full_reprocess_bypasses_incremental_cache(self):
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
                svc.repo.create_media_file(
                    project_id="proj-1",
                    media_file_id="file-1",
                    name="short.txt",
                    path=str(media_path),
                    duration_seconds=1,
                    size_bytes=media_path.stat().st_size,
                )
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
                            "translations": {
                                "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                            },
                            "linguistic_elements": [],
                        },
                    },
                ):
                    first = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                        media_file_id="file-1",
                    )
                self.assertEqual(first["status"], "completed")

                mocked_pipeline = MediaPipelineResult(
                    source_type="text",
                    full_text="She trusted him.",
                    text_hash="th2",
                    media_sentences=[
                        {
                            "sentence_idx": 0,
                            "sentence_text": "She trusted him.",
                            "sentence_hash": "h2",
                            "start_ms": 0,
                            "end_ms": 1000,
                            "id": 1,
                            "text_eng": "She trusted him.",
                            "text_ru": "Она доверяла ему.",
                            "units": [],
                            "units_ru": [],
                            "start": 0.0,
                            "end": 1.0,
                        }
                    ],
                    contract_sentences=[
                        {
                            "sentence_idx": 0,
                            "sentence_hash": "h2",
                            "sentence_node": {
                                "type": "Sentence",
                                "content": "She trusted him.",
                                "node_id": "n2",
                                "translations": {
                                    "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                                },
                                "linguistic_elements": [],
                            },
                        }
                    ],
                )
                with patch("ela_pipeline.runtime.service.run_media_pipeline", return_value=mocked_pipeline) as mocked:
                    second = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                        media_file_id="file-1",
                        force_full_reprocess=True,
                    )
                self.assertEqual(second["status"], "completed")
                self.assertEqual(mocked.call_count, 1)

    def test_incremental_cache_invalidates_when_media_changes(self):
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
                svc.repo.create_media_file(
                    project_id="proj-1",
                    media_file_id="file-1",
                    name="short.txt",
                    path=str(media_path),
                    duration_seconds=1,
                    size_bytes=media_path.stat().st_size,
                )
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
                            "translations": {
                                "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                            },
                            "linguistic_elements": [],
                        },
                    },
                ):
                    first = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                        media_file_id="file-1",
                    )
                self.assertEqual(first["status"], "completed")

                media_path.write_text("She trusted him. Again.", encoding="utf-8")
                mocked_pipeline = MediaPipelineResult(
                    source_type="text",
                    full_text="She trusted him. Again.",
                    text_hash="th-new",
                    media_sentences=[
                        {
                            "sentence_idx": 0,
                            "sentence_text": "She trusted him. Again.",
                            "sentence_hash": "h-new",
                            "start_ms": 0,
                            "end_ms": 1200,
                            "id": 1,
                            "text_eng": "She trusted him. Again.",
                            "text_ru": "Она снова доверяла ему.",
                            "units": [],
                            "units_ru": [],
                            "start": 0.0,
                            "end": 1.2,
                        }
                    ],
                    contract_sentences=[
                        {
                            "sentence_idx": 0,
                            "sentence_hash": "h-new",
                            "sentence_node": {
                                "type": "Sentence",
                                "content": "She trusted him. Again.",
                                "node_id": "n-new",
                                "translations": {
                                    "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она снова доверяла ему."}
                                },
                                "linguistic_elements": [],
                            },
                        }
                    ],
                )
                with patch("ela_pipeline.runtime.service.run_media_pipeline", return_value=mocked_pipeline) as mocked:
                    second = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                        media_file_id="file-1",
                    )
                self.assertEqual(second["status"], "completed")
                self.assertEqual(mocked.call_count, 1)

    def test_incremental_cache_invalidates_when_asr_settings_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "short.txt"
            media_path.write_text("She trusted him.", encoding="utf-8")
            artifacts_dir = Path(tmpdir) / "contracts"
            with patch.dict(
                "os.environ",
                {
                    "MEDIA_CONTRACT_ARTIFACTS_DIR": str(artifacts_dir),
                    "ELA_MEDIA_ASR_MODEL": "base",
                },
                clear=False,
            ):
                svc = RuntimeMediaService(
                    db_path=Path(tmpdir) / "client.sqlite3",
                    runtime_mode="online",
                    limits=MediaPolicyLimits(max_duration_min=15, max_size_local_mb=250, max_size_backend_mb=2048),
                )
                svc.repo.create_project("Project A", project_id="proj-1")
                svc.repo.create_media_file(
                    project_id="proj-1",
                    media_file_id="file-1",
                    name="short.txt",
                    path=str(media_path),
                    duration_seconds=1,
                    size_bytes=media_path.stat().st_size,
                )
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
                            "translations": {
                                "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                            },
                            "linguistic_elements": [],
                        },
                    },
                ):
                    first = svc.process_media_now(
                        media_path=str(media_path),
                        project_id="proj-1",
                        media_file_id="file-1",
                    )
                self.assertEqual(first["status"], "completed")

                mocked_pipeline = MediaPipelineResult(
                    source_type="text",
                    full_text="She trusted him.",
                    text_hash="th-asr",
                    media_sentences=[
                        {
                            "sentence_idx": 0,
                            "sentence_text": "She trusted him.",
                            "sentence_hash": "h-asr",
                            "start_ms": 0,
                            "end_ms": 1000,
                            "id": 1,
                            "text_eng": "She trusted him.",
                            "text_ru": "Она доверяла ему.",
                            "units": [],
                            "units_ru": [],
                            "start": 0.0,
                            "end": 1.0,
                        }
                    ],
                    contract_sentences=[
                        {
                            "sentence_idx": 0,
                            "sentence_hash": "h-asr",
                            "sentence_node": {
                                "type": "Sentence",
                                "content": "She trusted him.",
                                "node_id": "n-asr",
                                "translations": {
                                    "backend_m2m100": {"source_lang": "en", "target_lang": "ru", "text": "Она доверяла ему."}
                                },
                                "linguistic_elements": [],
                            },
                        }
                    ],
                )
                with patch.dict("os.environ", {"ELA_MEDIA_ASR_MODEL": "small"}, clear=False):
                    with patch("ela_pipeline.runtime.service.run_media_pipeline", return_value=mocked_pipeline) as mocked:
                        second = svc.process_media_now(
                            media_path=str(media_path),
                            project_id="proj-1",
                            media_file_id="file-1",
                        )
                self.assertEqual(second["status"], "completed")
                self.assertEqual(mocked.call_count, 1)


if __name__ == "__main__":
    unittest.main()
