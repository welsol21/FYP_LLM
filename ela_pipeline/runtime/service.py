"""Frontend-ready runtime service: capabilities + local media processing."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid
from typing import Any, Callable
from urllib import error as urlerror
from urllib import request as urlrequest

from ela_pipeline.client_storage import LocalSQLiteRepository, build_sentence_hash
from ela_pipeline.inference.run import run_pipeline

from .capabilities import build_runtime_capabilities, resolve_deployment_mode, resolve_runtime_mode
from .media_policy import MediaPolicyLimits, load_media_policy_limits_from_env
from .media_pipeline import run_media_pipeline, translate_text_with_provider
from .media_submission import submit_media_for_processing
from .ui_state import build_runtime_ui_state, build_submission_ui_feedback

TRANSLATION_CONFIG_STATE_KEY = "translation_config"
MEDIA_FILE_SETTINGS_PREFIX = "media_file_settings:"


def _builtin_translation_providers() -> list[dict[str, Any]]:
    return [
        {"id": "m2m100", "label": "Our Translator (M2M100)", "kind": "builtin", "enabled": True, "credential_fields": [], "credentials": {}},
        {"id": "hf", "label": "HuggingFace", "kind": "builtin", "enabled": True, "credential_fields": [], "credentials": {}},
        {"id": "gpt", "label": "OpenAI GPT", "kind": "builtin", "enabled": False, "credential_fields": ["api_key"], "credentials": {"api_key": ""}},
        {"id": "deepl", "label": "DeepL", "kind": "builtin", "enabled": False, "credential_fields": ["auth_key"], "credentials": {"auth_key": ""}},
        {
            "id": "lara",
            "label": "Lara",
            "kind": "builtin",
            "enabled": False,
            "credential_fields": ["api_id", "api_secret"],
            "credentials": {"api_id": "", "api_secret": ""},
        },
        {
            "id": "original",
            "label": "Original only (no translation)",
            "kind": "builtin",
            "enabled": True,
            "credential_fields": [],
            "credentials": {},
        },
    ]


def _default_translation_config() -> dict[str, Any]:
    return {"default_provider": "m2m100", "providers": _builtin_translation_providers()}


def _normalize_translation_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = _default_translation_config()
    incoming = raw if isinstance(raw, dict) else {}
    merged: dict[str, dict[str, Any]] = {p["id"]: dict(p) for p in base["providers"]}
    incoming_providers = incoming.get("providers")
    if isinstance(incoming_providers, list):
        for row in incoming_providers:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("id") or "").strip().lower()
            if not pid:
                continue
            item = merged.get(pid, {"id": pid, "kind": "custom", "credential_fields": [], "credentials": {}, "enabled": True})
            item["label"] = str(row.get("label") or item.get("label") or pid).strip() or pid
            item["kind"] = "builtin" if item.get("kind") == "builtin" else str(row.get("kind") or item.get("kind") or "custom")
            item["enabled"] = bool(row.get("enabled", item.get("enabled", True)))
            fields = row.get("credential_fields", item.get("credential_fields", []))
            if not isinstance(fields, list):
                fields = []
            item["credential_fields"] = [str(x).strip() for x in fields if str(x).strip()]
            creds = row.get("credentials", item.get("credentials", {}))
            if not isinstance(creds, dict):
                creds = {}
            normalized_creds: dict[str, str] = {}
            for k, v in creds.items():
                key = str(k).strip()
                if key:
                    normalized_creds[key] = str(v or "")
            for field in item["credential_fields"]:
                normalized_creds.setdefault(field, "")
            item["credentials"] = normalized_creds
            merged[pid] = item
    default_provider = str(incoming.get("default_provider") or base["default_provider"]).strip().lower() or "m2m100"
    if default_provider in merged:
        merged[default_provider]["enabled"] = True
    providers = sorted(merged.values(), key=lambda p: (0 if p.get("kind") == "builtin" else 1, str(p.get("label") or p.get("id"))))
    enabled_ids = {str(p.get("id")) for p in providers if p.get("enabled")}
    if default_provider not in enabled_ids:
        default_provider = "m2m100" if "m2m100" in enabled_ids else next(iter(enabled_ids), "m2m100")
    return {"default_provider": default_provider, "providers": providers}


def _srt_ts(total_ms: int) -> str:
    ms = max(0, int(total_ms))
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    seconds = ms // 1_000
    millis = ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _build_srt(segments: list[dict[str, Any]], *, bilingual: bool) -> str:
    lines: list[str] = []
    idx_out = 1
    for seg in segments:
        start_ms = int(seg.get("start_ms") or 0)
        end_ms = int(seg.get("end_ms") or 0)
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        text_en = str(seg.get("text_eng") or "").strip()
        text_ru = str(seg.get("text_ru") or "").strip()
        if bilingual:
            if text_en and text_ru:
                body = f"{text_en}\n{text_ru}"
            else:
                body = text_en or text_ru
        else:
            body = text_en
        if not body:
            continue
        lines.append(str(idx_out))
        lines.append(f"{_srt_ts(start_ms)} --> {_srt_ts(end_ms)}")
        lines.append(body)
        lines.append("")
        idx_out += 1
    return "\n".join(lines).strip() + "\n"


def _translated_text_for_tts(media_sentences: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for row in media_sentences:
        ru = str(row.get("text_ru") or "").strip()
        en = str(row.get("sentence_text") or row.get("text_eng") or "").strip()
        if ru:
            parts.append(ru)
        elif en:
            parts.append(en)
    return " ".join(parts).strip()


@dataclass
class RuntimeMediaService:
    """Single integration point for UI/desktop layer."""

    db_path: str | Path
    runtime_mode: str = "auto"
    deployment_mode: str = "auto"
    limits: MediaPolicyLimits | None = None
    _local_jobs: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _local_jobs_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.repo = LocalSQLiteRepository(self.db_path)
        self.effective_mode = resolve_runtime_mode(self.runtime_mode)
        self.effective_deployment_mode = resolve_deployment_mode(self.deployment_mode)
        self.caps = build_runtime_capabilities(self.effective_mode, deployment_mode=self.effective_deployment_mode)
        self.limits = self.limits or load_media_policy_limits_from_env()
        self.sentence_contract_backend_url = os.getenv("ELA_SENTENCE_CONTRACT_BACKEND_URL", "").strip()

    def get_ui_state(self) -> dict[str, Any]:
        return build_runtime_ui_state(self.caps)

    def list_projects(self) -> list[dict[str, Any]]:
        return self.repo.list_projects()

    def get_translation_config(self) -> dict[str, Any]:
        stored = self.repo.get_workspace_state(TRANSLATION_CONFIG_STATE_KEY)
        normalized = _normalize_translation_config(stored)
        self.repo.set_workspace_state(TRANSLATION_CONFIG_STATE_KEY, normalized)
        return normalized

    def save_translation_config(self, config: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_translation_config(config)
        self.repo.set_workspace_state(TRANSLATION_CONFIG_STATE_KEY, normalized)
        return normalized

    @staticmethod
    def _provider_credentials(*, provider_id: str, config: dict[str, Any]) -> dict[str, str]:
        for row in config.get("providers", []):
            if not isinstance(row, dict):
                continue
            if str(row.get("id") or "").strip().lower() != provider_id:
                continue
            creds = row.get("credentials")
            if not isinstance(creds, dict):
                return {}
            out: dict[str, str] = {}
            for k, v in creds.items():
                key = str(k).strip()
                if key:
                    out[key] = str(v or "")
            return out
        return {}

    def create_project(self, *, name: str) -> dict[str, Any]:
        created = self.repo.create_project(name=name)
        self.set_selected_project(project_id=created["id"])
        return created

    def get_selected_project(self) -> dict[str, Any]:
        state = self.repo.get_workspace_state("selected_project")
        if not state:
            return {"project_id": None}
        project_id = state.get("project_id")
        if not project_id:
            return {"project_id": None}
        row = next((p for p in self.repo.list_projects() if p["id"] == project_id), None)
        if row is None:
            return {"project_id": None}
        return {"project_id": row["id"], "project_name": row["name"]}

    def set_selected_project(self, *, project_id: str) -> dict[str, Any]:
        row = next((p for p in self.repo.list_projects() if p["id"] == project_id), None)
        if row is None:
            return {"project_id": None}
        self.repo.set_workspace_state("selected_project", {"project_id": project_id})
        return {"project_id": row["id"], "project_name": row["name"]}

    def register_media_file(
        self,
        *,
        project_id: str,
        name: str,
        media_path: str,
        size_bytes: int,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        row = next((p for p in self.repo.list_projects() if p["id"] == project_id), None)
        if row is None:
            return {"error": "project_not_found"}
        return self.repo.create_media_file(
            project_id=project_id,
            name=name,
            path=media_path,
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
        )

    def submit_media(
        self,
        *,
        media_path: str,
        duration_seconds: int,
        size_bytes: int,
        project_id: str | None = None,
        media_file_id: str | None = None,
        translation_provider: str | None = None,
        subtitles_mode: str | None = None,
        voice_choice: str | None = None,
        async_local_processing: bool = False,
    ) -> dict[str, Any]:
        translation_cfg = self.get_translation_config()
        selected_provider = str(translation_provider or translation_cfg.get("default_provider") or "m2m100").strip().lower()
        provider_credentials = self._provider_credentials(provider_id=selected_provider, config=translation_cfg)
        selected = self.get_selected_project()
        effective_project_id = project_id or selected.get("project_id")
        if not effective_project_id:
            raw = {
                "route": "reject",
                "status": "rejected",
                "message": "Create/select project first.",
                "job_id": None,
            }
            return {
                "result": raw,
                "ui_feedback": build_submission_ui_feedback(raw),
            }
        if not any(p["id"] == effective_project_id for p in self.repo.list_projects()):
            raw = {
                "route": "reject",
                "status": "rejected",
                "message": f"Project '{effective_project_id}' not found.",
                "job_id": None,
            }
            return {
                "result": raw,
                "ui_feedback": build_submission_ui_feedback(raw),
            }

        if media_file_id is None:
            media_file_id = f"file-{uuid.uuid4().hex[:12]}"
            self.repo.create_media_file(
                project_id=effective_project_id,
                media_file_id=media_file_id,
                name=Path(media_path).name or media_path,
                path=media_path,
                duration_seconds=duration_seconds,
                size_bytes=size_bytes,
            )
        self.repo.set_workspace_state(
            f"{MEDIA_FILE_SETTINGS_PREFIX}{media_file_id}",
            {
                "translation_provider": selected_provider,
                "subtitles_mode": str(subtitles_mode or "bilingual"),
                "voice_choice": str(voice_choice or "male"),
            },
        )

        raw = submit_media_for_processing(
            repo=self.repo,
            media_path=media_path,
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
            runtime_caps=self.caps,
            limits=self.limits,
            project_id=effective_project_id,
            media_file_id=media_file_id,
            prefer_backend_for_enrichment=False,
        )
        if raw.get("route") == "local":
            if async_local_processing:
                job_id = self._start_local_processing_job(
                    media_path=media_path,
                    project_id=effective_project_id,
                    media_file_id=media_file_id,
                    translation_provider=selected_provider,
                    provider_credentials=provider_credentials,
                )
                raw["job_id"] = job_id
                raw["status"] = "accepted_local"
                raw["message"] = "Local processing started."
            else:
                synced = self.process_media_now(
                    media_path=media_path,
                    project_id=effective_project_id,
                    media_file_id=media_file_id,
                    translation_provider=selected_provider,
                    provider_credentials=provider_credentials,
                )
                raw["document_id"] = synced.get("document_id")
                raw["status"] = "completed_local" if synced.get("status") == "completed" else raw.get("status")
                if synced.get("status") != "completed":
                    raw["route"] = "reject"
                    raw["status"] = "rejected"
                    raw["message"] = str(synced.get("message") or "Local media processing failed.")
        return {
            "result": raw,
            "ui_feedback": build_submission_ui_feedback(raw),
        }

    def get_backend_job_status(self, *, job_id: str) -> dict[str, Any]:
        with self._local_jobs_lock:
            row = self._local_jobs.get(job_id)
        if row is None:
            return {
                "job_id": job_id,
                "status": "not_found",
                "message": "Job not found.",
                "stage_name": "not_found",
                "stage_log": "Job not found.",
                "stage_logs": ["Job not found."],
                "stage_progress": [0, 0, 0, 0, 0],
            }
        return dict(row)

    def list_document_sentences(self, *, document_id: str) -> list[dict[str, Any]]:
        rows = self.repo.list_document_visualizer_rows(document_id=document_id)
        return [
            {
                "sentence_idx": row["sentence_idx"],
                "sentence_text": row["sentence_text"],
                "sentence_hash": row["sentence_hash"],
            }
            for row in rows
        ]

    def list_document_artifacts(self, *, document_id: str) -> list[dict[str, Any]]:
        base = Path(os.getenv("MEDIA_CONTRACT_ARTIFACTS_DIR", "artifacts/media_contracts"))
        doc_dir = (base / document_id).resolve()
        base_resolved = base.resolve()
        if not str(doc_dir).startswith(str(base_resolved)):
            return []
        if not doc_dir.exists() or not doc_dir.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for entry in sorted(doc_dir.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_file():
                continue
            out.append(
                {
                    "name": entry.name,
                    "size_bytes": int(entry.stat().st_size),
                    "download_url": f"/api/document-artifact-download?document_id={document_id}&name={entry.name}",
                }
            )
        return out

    def get_visualizer_payload(self, *, document_id: str) -> dict[str, Any]:
        rows = self.repo.list_document_visualizer_rows(document_id=document_id)
        payload: dict[str, Any] = {}
        duplicates: dict[str, int] = {}
        for row in rows:
            base = (row.get("sentence_text") or "").strip() or f"sentence_{row['sentence_idx']}"
            seen = duplicates.get(base, 0)
            duplicates[base] = seen + 1
            key = base if seen == 0 else f"{base} #{seen + 1}"
            node = row["sentence_node"]
            text_ru = str(row.get("text_ru") or "").strip()
            if text_ru and isinstance(node, dict):
                tr = node.get("translation")
                if not isinstance(tr, dict):
                    node["translation"] = {"source_lang": "en", "target_lang": "ru", "text": text_ru}
                else:
                    tr["text"] = text_ru
            payload[key] = node
        return payload

    def get_document_processing_status(self, *, document_id: str) -> dict[str, Any]:
        status = self.repo.get_document_processing_status(document_id=document_id)
        if status is None:
            return {
                "document_id": document_id,
                "status": "not_found",
                "media_sentences_count": 0,
                "contract_sentences_count": 0,
                "linked_sentences_count": 0,
                "text_present": False,
                "text_length": 0,
                "text_version": 0,
                "latest_backend_job": None,
            }
        return status

    def list_files(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.repo.list_media_files_with_analysis(project_id=project_id)
        out: list[dict[str, Any]] = []
        for row in rows:
            settings_state = self.repo.get_workspace_state(f"{MEDIA_FILE_SETTINGS_PREFIX}{row['id']}") or {}
            tp = str(settings_state.get("translation_provider") or "m2m100")
            subs = str(settings_state.get("subtitles_mode") or "bilingual")
            voice = str(settings_state.get("voice_choice") or "male")
            out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "path": row.get("path"),
                    "size_bytes": row.get("size_bytes"),
                    "duration_seconds": row.get("duration_seconds"),
                    "settings": f"Transl: {tp} / Subs: {subs} / Voice: {voice}",
                    "updated": row["updated_at"],
                    "analyzed": bool(row["analyzed"]),
                    "document_id": row.get("document_id"),
                }
            )
        return out

    def build_sentence_contract(
        self,
        *,
        sentence_text: str,
        sentence_idx: int = 0,
        model_dir: str | None = None,
        note_mode: str = "template_only",
        validation_mode: str = "v2_strict",
        enable_translation: bool = False,
        translation_model: str = "facebook/m2m100_418M",
        translation_source_lang: str = "en",
        translation_target_lang: str = "ru",
        translation_device: str = "auto",
        enable_phonetic: bool = False,
        phonetic_binary: str = "auto",
        enable_synonyms: bool = False,
        synonyms_top_k: int = 5,
        enable_cefr: bool = False,
        cefr_provider: str = "rule",
        cefr_model_path: str = "artifacts/models/t5_cefr/best_model",
    ) -> dict[str, Any]:
        text = str(sentence_text or "").strip()
        if not text:
            raise ValueError("sentence_text must be non-empty")

        contract = run_pipeline(
            text=text,
            model_dir=model_dir,
            validation_mode=validation_mode,
            note_mode=note_mode,
            enable_translation=enable_translation,
            translation_provider="m2m100",
            translation_model=translation_model,
            translation_source_lang=translation_source_lang,
            translation_target_lang=translation_target_lang,
            translation_device=translation_device,
            enable_phonetic=enable_phonetic,
            phonetic_binary=phonetic_binary,
            enable_synonyms=enable_synonyms,
            synonyms_top_k=synonyms_top_k,
            enable_cefr=enable_cefr,
            cefr_provider=cefr_provider,
            cefr_model_path=cefr_model_path,
        )
        sentence_node = self._select_sentence_node_from_contract(contract=contract, sentence_text=text)
        sentence_text_resolved = str(sentence_node.get("content") or text).strip() or text
        return {
            "sentence_text": sentence_text_resolved,
            "sentence_hash": build_sentence_hash(sentence_text_resolved, int(sentence_idx)),
            "sentence_node": sentence_node,
        }

    @staticmethod
    def _select_sentence_node_from_contract(*, contract: dict[str, Any], sentence_text: str) -> dict[str, Any]:
        if not isinstance(contract, dict) or not contract:
            raise RuntimeError("run_pipeline returned empty contract.")
        source_norm = " ".join(sentence_text.strip().split()).casefold()
        for _, value in contract.items():
            if not isinstance(value, dict):
                continue
            content = " ".join(str(value.get("content") or "").strip().split()).casefold()
            if content and content == source_norm:
                return value
        for _, value in contract.items():
            if isinstance(value, dict):
                return value
        raise RuntimeError("run_pipeline returned no sentence node.")

    def process_media_now(
        self,
        *,
        media_path: str,
        project_id: str,
        media_file_id: str | None = None,
        translation_provider: str | None = None,
        provider_credentials: dict[str, str] | None = None,
        document_id: str | None = None,
        stage_callback: Callable[[str, float | None, str | None], None] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        if stage_callback is not None:
            stage_callback("loading_file", 0.25, "Loading source file")
        source_type = self._detect_source_type(media_path)
        if source_type in {"audio", "video"} and stage_callback is not None:
            stage_callback("transcribing_audio", 0.05, "Preparing ASR")
        try:
            pipeline = run_media_pipeline(
                source_path=media_path,
                sentence_contract_builder=lambda *, sentence_text, sentence_idx: self._build_sentence_contract_from_backend_and_local_translation(
                    sentence_text=sentence_text,
                    sentence_idx=sentence_idx,
                ),
                progress_callback=stage_callback,
            )
        except Exception as exc:
            return {
                "job_id": None,
                "status": "error",
                "message": str(exc),
            }

        if stage_callback is not None:
            stage_callback("translating_text", 1.0, "Sentence contract build completed")

        selected_provider = str(translation_provider or "").strip().lower()
        if selected_provider and selected_provider not in {"m2m100", "our", "backend", "default"}:
            total = max(len(pipeline.media_sentences), 1)
            for idx, row in enumerate(pipeline.media_sentences):
                source_text = str(row.get("sentence_text") or "").strip()
                translated = translate_text_with_provider(
                    text=source_text,
                    translation_provider=selected_provider,
                    provider_credentials=provider_credentials,
                )
                row["text_ru"] = translated
                if stage_callback is not None:
                    stage_callback(
                        "translating_text",
                        (idx + 1) / total,
                        f"Overlay translation {idx + 1}/{total} via {selected_provider}",
                    )

        document_id = document_id or f"doc-{uuid.uuid4().hex[:12]}"
        existing_doc = self.repo.get_document(document_id)
        if existing_doc is None:
            self.repo.create_document(
                document_id=document_id,
                project_id=project_id,
                media_file_id=media_file_id,
                source_type=pipeline.source_type,
                source_path=media_path,
                media_hash=f"local:{media_file_id or 'media'}",
                status="processing",
            )
        self.repo.upsert_document_text(
            document_id=document_id,
            full_text=pipeline.full_text,
            text_hash=pipeline.text_hash,
            version=1,
        )
        self.repo.replace_media_sentences(document_id=document_id, sentences=pipeline.media_sentences)
        for row in pipeline.contract_sentences:
            self.repo.upsert_contract_sentence(
                document_id=document_id,
                sentence_hash=row["sentence_hash"],
                sentence_node=row["sentence_node"],
            )
        self.repo.replace_sentence_links(
            document_id=document_id,
            links=[
                {"sentence_idx": row["sentence_idx"], "sentence_hash": row["sentence_hash"]}
                for row in pipeline.media_sentences
            ],
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.25, "Persisting contract artifacts")
        self._persist_media_contract_artifacts(
            document_id=document_id,
            media_path=media_path,
            source_type=pipeline.source_type,
            full_text=pipeline.full_text,
            text_hash=pipeline.text_hash,
            media_sentences=pipeline.media_sentences,
            contract_sentences=pipeline.contract_sentences,
        )
        if stage_callback is not None:
            stage_callback("exporting_files", 1.0, "Artifacts exported")
        duration_ms = int((time.monotonic() - started) * 1000)
        self.repo.update_document_status(document_id, "completed", processing_duration_ms=duration_ms)
        return {
            "job_id": None,
            "status": "completed",
            "document_id": document_id,
            "processing_duration_ms": duration_ms,
            "media_sentences_count": len(pipeline.media_sentences),
            "contract_sentences_count": len(pipeline.contract_sentences),
            "linked_sentences_count": len(pipeline.media_sentences),
            "message": "Local media processed and synced.",
        }

    @staticmethod
    def _detect_source_type(media_path: str) -> str:
        suffix = Path(media_path).suffix.lower()
        if suffix in {".txt", ".md", ".rtf"}:
            return "text"
        if suffix == ".pdf":
            return "pdf"
        if suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}:
            return "audio"
        if suffix in {".mp4", ".mkv", ".mov", ".avi", ".webm"}:
            return "video"
        return "text"

    @staticmethod
    def _stage_progress(stage_name: str, ratio: float | None = None) -> list[int]:
        def clamp(v: float) -> int:
            return max(0, min(100, int(round(v))))

        if ratio is not None:
            r = max(0.0, min(1.0, float(ratio)))
            if stage_name == "loading_file":
                return [clamp(5 + 95 * r), 0, 0, 0, 0]
            if stage_name == "transcribing_audio":
                return [100, clamp(5 + 95 * r), 0, 0, 0]
            if stage_name == "translating_text":
                return [100, 100, clamp(5 + 95 * r), 0, 0]
            if stage_name == "generating_media":
                return [100, 100, 100, clamp(5 + 95 * r), 0]
            if stage_name == "exporting_files":
                return [100, 100, 100, 100, clamp(5 + 95 * r)]
        mapping = {
            "queued": [2, 0, 0, 0, 0],
            "loading_file": [25, 0, 0, 0, 0],
            "transcribing_audio": [100, 45, 0, 0, 0],
            "translating_text": [100, 100, 65, 0, 0],
            "generating_media": [100, 100, 100, 75, 0],
            "exporting_files": [100, 100, 100, 100, 85],
            "completed": [100, 100, 100, 100, 100],
            "error": [100, 100, 100, 100, 100],
        }
        return list(mapping.get(stage_name, [0, 0, 0, 0, 0]))

    def _set_local_job_state(
        self,
        *,
        job_id: str,
        status: str,
        message: str,
        stage_name: str | None = None,
        document_id: str | None = None,
        progress_ratio: float | None = None,
        stage_log: str | None = None,
    ) -> None:
        stage_progress = self._stage_progress(stage_name or status, progress_ratio)
        stage_name_resolved = stage_name or str(status or "")
        message_resolved = str(message or "")
        stage_log_resolved = str(stage_log or "").strip() or None
        with self._local_jobs_lock:
            previous = dict(self._local_jobs.get(job_id) or {})
            logs = list(previous.get("stage_logs") or [])
            if stage_log_resolved:
                if not logs or logs[-1] != stage_log_resolved:
                    logs.append(stage_log_resolved)
            elif message_resolved:
                if not logs or logs[-1] != message_resolved:
                    logs.append(message_resolved)
            logs = logs[-80:]

        payload: dict[str, Any] = {
            "job_id": job_id,
            "status": status,
            "message": message_resolved,
            "stage_name": stage_name_resolved,
            "stage_log": stage_log_resolved or (logs[-1] if logs else ""),
            "stage_logs": logs,
            "stage_progress": stage_progress,
        }
        if document_id:
            payload["document_id"] = document_id
        elif previous.get("document_id"):
            payload["document_id"] = previous.get("document_id")
        if previous.get("document_id") and "document_id" not in payload:
            payload["document_id"] = previous.get("document_id")
        with self._local_jobs_lock:
            self._local_jobs[job_id] = payload

    def _start_local_processing_job(
        self,
        *,
        media_path: str,
        project_id: str,
        media_file_id: str | None,
        translation_provider: str | None,
        provider_credentials: dict[str, str] | None,
    ) -> str:
        job_id = f"local-{uuid.uuid4().hex[:12]}"
        self._set_local_job_state(
            job_id=job_id,
            status="accepted_local",
            message="Local processing started.",
            stage_name="queued",
        )

        def _runner() -> None:
            document_id = f"doc-{uuid.uuid4().hex[:12]}"
            try:
                result = self.process_media_now(
                    media_path=media_path,
                    project_id=project_id,
                    media_file_id=media_file_id,
                    translation_provider=translation_provider,
                    provider_credentials=provider_credentials,
                    document_id=document_id,
                    stage_callback=lambda stage, ratio, log_line: self._set_local_job_state(
                        job_id=job_id,
                        status="running_local",
                        message=f"Stage: {stage.replace('_', ' ')}",
                        stage_name=stage,
                        document_id=document_id,
                        progress_ratio=ratio,
                        stage_log=log_line,
                    ),
                )
                if result.get("status") == "completed":
                    self._set_local_job_state(
                        job_id=job_id,
                        status="completed_local",
                        message="Local processing completed.",
                        stage_name="completed",
                        document_id=document_id,
                        stage_log=f"Total duration: {int(result.get('processing_duration_ms') or 0)} ms",
                    )
                else:
                    self._set_local_job_state(
                        job_id=job_id,
                        status="rejected",
                        message=str(result.get("message") or "Local processing failed."),
                        stage_name="error",
                        document_id=document_id,
                    )
            except Exception as exc:
                self._set_local_job_state(
                    job_id=job_id,
                    status="error",
                    message=str(exc),
                    stage_name="error",
                    document_id=document_id,
                )

        threading.Thread(target=_runner, daemon=True).start()
        return job_id

    def _build_sentence_contract_from_backend_and_local_translation(
        self,
        *,
        sentence_text: str,
        sentence_idx: int,
    ) -> dict[str, Any]:
        return self._request_sentence_contract(
            sentence_text=sentence_text,
            sentence_idx=sentence_idx,
        )

    def _persist_media_contract_artifacts(
        self,
        *,
        document_id: str,
        media_path: str,
        source_type: str,
        full_text: str,
        text_hash: str,
        media_sentences: list[dict[str, Any]],
        contract_sentences: list[dict[str, Any]],
    ) -> None:
        base = Path(os.getenv("MEDIA_CONTRACT_ARTIFACTS_DIR", "artifacts/media_contracts"))
        doc_dir = base / document_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        links = [
            {"sentence_idx": row["sentence_idx"], "sentence_hash": row["sentence_hash"]}
            for row in media_sentences
        ]
        media_contract = {
            "document_id": document_id,
            "source_type": source_type,
            "source_path": media_path,
            "text_hash": text_hash,
            "media_sentences": media_sentences,
        }
        legacy_segments = [
            {
                "id": int(row.get("id") or row.get("sentence_idx", 0) + 1),
                "text_eng": str(row.get("text_eng") or row.get("sentence_text") or ""),
                "units": row.get("units") or [],
                "start": float(row.get("start") or 0.0),
                "end": float(row.get("end") or 0.0),
                "text_ru": str(row.get("text_ru") or ""),
                "units_ru": row.get("units_ru") or [],
            }
            for row in media_sentences
        ]

        (doc_dir / "full_text.txt").write_text(full_text, encoding="utf-8")
        (doc_dir / "media_contract.json").write_text(
            json.dumps(media_contract, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (doc_dir / "contract_sentences.json").write_text(
            json.dumps(contract_sentences, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (doc_dir / "sentence_link.json").write_text(
            json.dumps(links, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (doc_dir / "semantic_units_runtime.json").write_text(
            json.dumps(legacy_segments, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (doc_dir / "bilingual_objects_runtime.json").write_text(
            json.dumps(legacy_segments, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (doc_dir / "subtitles_en.srt").write_text(
            _build_srt(media_sentences, bilingual=False),
            encoding="utf-8",
        )
        (doc_dir / "subtitles_bilingual.srt").write_text(
            _build_srt(media_sentences, bilingual=True),
            encoding="utf-8",
        )
        self._export_final_media_artifacts(
            source_type=source_type,
            source_path=media_path,
            doc_dir=doc_dir,
            media_sentences=media_sentences,
        )

    def _export_final_media_artifacts(
        self,
        *,
        source_type: str,
        source_path: str,
        doc_dir: Path,
        media_sentences: list[dict[str, Any]],
    ) -> None:
        if source_type not in {"audio", "video"}:
            return

        translated_text = _translated_text_for_tts(media_sentences)
        if not translated_text:
            return

        tts_wav = doc_dir / "translated_audio_ru.wav"
        tts_mp3 = doc_dir / "translated_audio_ru.mp3"
        source = Path(source_path)
        try:
            # TTS synthesis from translated sentence stream.
            subprocess.run(
                ["espeak-ng", "-v", "ru", "-w", str(tts_wav)],
                input=translated_text,
                text=True,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # MP3 export for download.
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(tts_wav), "-acodec", "libmp3lame", "-q:a", "2", str(tts_mp3)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if tts_wav.exists():
                tts_wav.unlink(missing_ok=True)

            if source_type == "video" and source.exists():
                out_video = doc_dir / "translated_video_ru.mp4"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(source),
                        "-i",
                        str(tts_mp3),
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-c:v",
                        "copy",
                        "-c:a",
                        "aac",
                        "-shortest",
                        str(out_video),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as exc:
            # Keep pipeline successful even if media rendering fails on one environment.
            (doc_dir / "media_export_error.txt").write_text(str(exc), encoding="utf-8")

    def _request_sentence_contract(
        self,
        *,
        sentence_text: str,
        sentence_idx: int,
    ) -> dict[str, Any]:
        if not self.sentence_contract_backend_url:
            raise RuntimeError("ELA_SENTENCE_CONTRACT_BACKEND_URL is required for sentence contract requests.")
        endpoint = f"{self.sentence_contract_backend_url.rstrip('/')}/api/sentence-contract"
        payload = json.dumps(
            {
                "sentenceText": sentence_text,
                "sentenceIdx": sentence_idx,
            }
        ).encode("utf-8")
        req = urlrequest.Request(endpoint, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urlrequest.urlopen(req, timeout=30) as resp:  # nosec B310
                raw = resp.read().decode("utf-8")
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Backend sentence-contract API unavailable: {endpoint}") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from backend sentence-contract API: {endpoint}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"Invalid payload type from backend sentence-contract API: {endpoint}")
        if "sentence_node" not in parsed or "sentence_hash" not in parsed:
            raise RuntimeError(f"Incomplete payload from backend sentence-contract API: {endpoint}")
        return parsed

    def apply_document_edit(
        self,
        *,
        document_id: str,
        sentence_text: str,
        node_id: str,
        field_path: str,
        new_value: Any,
    ) -> dict[str, Any]:
        rows = self.repo.list_document_visualizer_rows(document_id=document_id)
        keyed: dict[str, dict[str, Any]] = {}
        duplicates: dict[str, int] = {}
        for row in rows:
            base = (row.get("sentence_text") or "").strip() or f"sentence_{row['sentence_idx']}"
            seen = duplicates.get(base, 0)
            duplicates[base] = seen + 1
            key = base if seen == 0 else f"{base} #{seen + 1}"
            keyed[key] = row
        target = keyed.get(sentence_text)
        if target is None:
            return {"status": "error", "message": "Sentence not found."}
        root = target["sentence_node"]
        node = self._find_node_by_id(root, node_id)
        if node is None:
            return {"status": "error", "message": "node_id not found."}
        if not self._set_by_path(node, field_path, new_value):
            return {"status": "error", "message": f"Invalid field path: {field_path}"}
        self.repo.upsert_contract_sentence(
            document_id=document_id,
            sentence_hash=target["sentence_hash"],
            sentence_node=root,
        )
        return {"status": "ok", "message": "Edit applied."}

    @staticmethod
    def _normalize_media_sentences(raw_sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for idx, row in enumerate(raw_sentences):
            sentence_idx = int(row.get("sentence_idx", idx))
            sentence_text = str(
                row.get("sentence_text")
                or row.get("text")
                or row.get("text_eng")
                or ""
            ).strip()
            if not sentence_text:
                continue
            sentence_hash = str(row.get("sentence_hash") or build_sentence_hash(sentence_text, sentence_idx))
            normalized.append(
                {
                    "sentence_idx": sentence_idx,
                    "sentence_text": sentence_text,
                    "start_ms": row.get("start_ms"),
                    "end_ms": row.get("end_ms"),
                    "page_no": row.get("page_no"),
                    "char_start": row.get("char_start"),
                    "char_end": row.get("char_end"),
                    "sentence_hash": sentence_hash,
                }
            )
        normalized.sort(key=lambda r: r["sentence_idx"])
        return normalized

    @staticmethod
    def _normalize_contract_sentences(
        *,
        raw: Any,
        media_sentences: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_idx = {row["sentence_idx"]: row["sentence_hash"] for row in media_sentences}
        by_text_occurrence: dict[str, list[str]] = {}
        for row in media_sentences:
            key = row["sentence_text"].strip().lower()
            by_text_occurrence.setdefault(key, []).append(row["sentence_hash"])
        use_index: dict[str, int] = {}

        rows: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for idx, item in enumerate(raw):
                if not isinstance(item, dict):
                    continue
                node = item.get("sentence_node") or item.get("node")
                if not isinstance(node, dict):
                    continue
                sentence_hash = item.get("sentence_hash")
                if not sentence_hash:
                    sentence_idx = item.get("sentence_idx")
                    if sentence_idx is not None and int(sentence_idx) in by_idx:
                        sentence_hash = by_idx[int(sentence_idx)]
                if not sentence_hash:
                    content = str(node.get("content") or "").strip().lower()
                    hashes = by_text_occurrence.get(content, [])
                    pos = use_index.get(content, 0)
                    if pos < len(hashes):
                        sentence_hash = hashes[pos]
                        use_index[content] = pos + 1
                if not sentence_hash:
                    sentence_hash = build_sentence_hash(str(node.get("content") or f"sentence_{idx}"), idx)
                rows.append({"sentence_hash": str(sentence_hash), "sentence_node": node})
        elif isinstance(raw, dict):
            for idx, (sentence_text, node) in enumerate(raw.items()):
                if not isinstance(node, dict):
                    continue
                key = str(sentence_text).strip().lower()
                hashes = by_text_occurrence.get(key, [])
                pos = use_index.get(key, 0)
                if pos < len(hashes):
                    sentence_hash = hashes[pos]
                    use_index[key] = pos + 1
                else:
                    sentence_hash = build_sentence_hash(str(sentence_text), idx)
                rows.append({"sentence_hash": str(sentence_hash), "sentence_node": node})

        if not rows:
            for row in media_sentences:
                rows.append(
                    {
                        "sentence_hash": row["sentence_hash"],
                        "sentence_node": {
                            "type": "Sentence",
                            "node_id": row["sentence_hash"][:12],
                            "content": row["sentence_text"],
                            "linguistic_elements": [],
                        },
                    }
                )
        return rows

    @staticmethod
    def _normalize_sentence_links(*, raw: Any, media_sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            links: list[dict[str, Any]] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                if "sentence_idx" not in item or "sentence_hash" not in item:
                    continue
                links.append({"sentence_idx": int(item["sentence_idx"]), "sentence_hash": str(item["sentence_hash"])})
            if links:
                links.sort(key=lambda r: r["sentence_idx"])
                return links
        return [
            {"sentence_idx": row["sentence_idx"], "sentence_hash": row["sentence_hash"]}
            for row in media_sentences
        ]

    @staticmethod
    def _find_node_by_id(root: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        stack = [root]
        while stack:
            node = stack.pop()
            if str(node.get("node_id")) == str(node_id):
                return node
            children = node.get("linguistic_elements")
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        stack.append(child)
        return None

    @staticmethod
    def _set_by_path(root: dict[str, Any], path: str, value: Any) -> bool:
        tokens: list[Any] = []
        buf = ""
        i = 0
        while i < len(path):
            ch = path[i]
            if ch == ".":
                if buf:
                    tokens.append(buf)
                    buf = ""
                i += 1
                continue
            if ch == "[":
                if buf:
                    tokens.append(buf)
                    buf = ""
                j = path.find("]", i + 1)
                if j == -1:
                    return False
                idx_txt = path[i + 1 : j]
                if not idx_txt.isdigit():
                    return False
                tokens.append(int(idx_txt))
                i = j + 1
                continue
            buf += ch
            i += 1
        if buf:
            tokens.append(buf)
        if not tokens:
            return False

        cur: Any = root
        for pos, token in enumerate(tokens[:-1]):
            nxt = tokens[pos + 1]
            if isinstance(token, int):
                if not isinstance(cur, list):
                    return False
                while len(cur) <= token:
                    cur.append({} if not isinstance(nxt, int) else [])
                if cur[token] is None:
                    cur[token] = {} if not isinstance(nxt, int) else []
                cur = cur[token]
            else:
                if not isinstance(cur, dict):
                    return False
                if token not in cur or cur[token] is None:
                    cur[token] = {} if not isinstance(nxt, int) else []
                cur = cur[token]

        last = tokens[-1]
        if isinstance(last, int):
            if not isinstance(cur, list):
                return False
            while len(cur) <= last:
                cur.append(None)
            cur[last] = value
            return True
        if not isinstance(cur, dict):
            return False
        cur[last] = value
        return True
