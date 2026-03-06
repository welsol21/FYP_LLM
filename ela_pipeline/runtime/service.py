"""Frontend-ready runtime service: capabilities + local media processing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Any, Callable, Iterable
from urllib import error as urlerror
from urllib import request as urlrequest

from ela_pipeline.client_storage import LocalSQLiteRepository, build_sentence_hash

from .capabilities import build_runtime_capabilities, resolve_deployment_mode, resolve_runtime_mode
from .media_policy import MediaPolicyLimits, load_media_policy_limits_from_env
from .media_pipeline import MediaPipelineResult, run_media_pipeline, translate_text_with_provider
from .media_submission import submit_media_for_processing
from .ui_state import build_runtime_ui_state, build_submission_ui_feedback

TRANSLATION_CONFIG_STATE_KEY = "translation_config"
MEDIA_FILE_SETTINGS_PREFIX = "media_file_settings:"
BACKEND_TRANSLATION_PROVIDER_KEY = "backend_m2m100"
MEDIA_STAGE_MANIFEST_PREFIX = "media_stage_manifest:"
CONTRACT_BUILD_VERSION = "2026-03-04-rulesfirst-v1"


def _normalize_provider_key(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return raw.replace(" ", "_").replace("-", "_")


def _ensure_node_translations_map(
    node: dict[str, Any],
    *,
    canonical_provider: str = BACKEND_TRANSLATION_PROVIDER_KEY,
) -> None:
    if not isinstance(node, dict):
        return
    existing = node.get("translations")
    translations: dict[str, dict[str, Any]] = {}
    if isinstance(existing, dict):
        for key, entry in existing.items():
            provider_key = _normalize_provider_key(str(key))
            if not provider_key or not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            translations[provider_key] = {
                "text": text,
                "source_lang": str(entry.get("source_lang") or "en").strip() or "en",
                "target_lang": str(entry.get("target_lang") or "ru").strip() or "ru",
                "origin": str(entry.get("origin") or "").strip() or "provider",
            }
            created_at = str(entry.get("created_at") or "").strip()
            if created_at:
                translations[provider_key]["created_at"] = created_at

    if translations:
        node["translations"] = translations

    children = node.get("linguistic_elements")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                _ensure_node_translations_map(child, canonical_provider=canonical_provider)


def _pick_translation_entry(
    *,
    node: dict[str, Any],
    preferred_provider: str | None,
    canonical_provider: str = BACKEND_TRANSLATION_PROVIDER_KEY,
) -> dict[str, Any] | None:
    translations = node.get("translations")
    if isinstance(translations, dict):
        preferred_key = _normalize_provider_key(preferred_provider)
        if preferred_key:
            row = translations.get(preferred_key)
            if isinstance(row, dict) and str(row.get("text") or "").strip():
                return row
        canonical_row = translations.get(canonical_provider)
        if isinstance(canonical_row, dict) and str(canonical_row.get("text") or "").strip():
            return canonical_row
        for row in translations.values():
            if isinstance(row, dict) and str(row.get("text") or "").strip():
                return row
    return None


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


def _ffmpeg_escape_filter_path(path: Path) -> str:
    raw = str(path.resolve())
    return raw.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _subtitle_path_for_mode(*, doc_dir: Path, subtitles_mode: str) -> Path:
    mode = str(subtitles_mode or "bilingual").strip().lower()
    if mode in {"source", "source_only", "source only", "en"}:
        return doc_dir / "subtitles_en.srt"
    if mode in {"target", "target_only", "target only", "ru"}:
        return doc_dir / "subtitles_target.srt"
    return doc_dir / "subtitles_bilingual.srt"


def _voice_name_for_choice(voice_choice: str) -> str:
    choice = str(voice_choice or "male").strip().lower()
    if choice.startswith("f"):
        return "ru-RU-SvetlanaNeural"
    return "ru-RU-DmitryNeural"


def _probe_audio_duration_ms(path: Path) -> int:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        sec = float((proc.stdout or "").strip() or "0")
        return max(0, int(round(sec * 1000)))
    except Exception:
        return 0


def _extract_audio_segment_mp3(*, source: Path, start_ms: int, end_ms: int, out_path: Path) -> bool:
    if end_ms <= start_ms:
        return False
    start_sec = max(0.0, float(start_ms) / 1000.0)
    end_sec = max(start_sec + 0.01, float(end_ms) / 1000.0)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start_sec:.3f}",
                "-to",
                f"{end_sec:.3f}",
                "-i",
                str(source),
                "-vn",
                "-acodec",
                "libmp3lame",
                "-q:a",
                "3",
                str(out_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return out_path.exists() and out_path.stat().st_size > 1024
    except Exception:
        return False


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
        raw_timeout = str(os.getenv("ELA_SENTENCE_CONTRACT_TIMEOUT_SEC", "300")).strip()
        try:
            timeout_sec = int(raw_timeout)
        except ValueError:
            timeout_sec = 300
        self.sentence_contract_timeout_sec = max(5, timeout_sec)

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
        force_full_reprocess: bool = False,
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
                    subtitles_mode=str(subtitles_mode or "bilingual"),
                    voice_choice=str(voice_choice or "male"),
                    force_full_reprocess=bool(force_full_reprocess),
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
                    subtitles_mode=str(subtitles_mode or "bilingual"),
                    voice_choice=str(voice_choice or "male"),
                    force_full_reprocess=bool(force_full_reprocess),
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
        if not self._is_current_document_contract(document_id):
            return []
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
        if not self._is_current_document_contract(document_id):
            return {}
        rows = self.repo.list_document_visualizer_rows(document_id=document_id)
        document = self.repo.get_document(document_id)
        selected_provider = None
        if isinstance(document, dict):
            media_file_id = str(document.get("media_file_id") or "").strip()
            if media_file_id:
                settings = self.repo.get_workspace_state(f"{MEDIA_FILE_SETTINGS_PREFIX}{media_file_id}") or {}
                selected_provider = str(settings.get("translation_provider") or "").strip().lower() or None
        payload: dict[str, Any] = {}
        duplicates: dict[str, int] = {}
        for row in rows:
            base = (row.get("sentence_text") or "").strip() or f"sentence_{row['sentence_idx']}"
            seen = duplicates.get(base, 0)
            duplicates[base] = seen + 1
            key = base if seen == 0 else f"{base} #{seen + 1}"
            node = row["sentence_node"]
            text_ru = str(row.get("text_ru") or "").strip()
            if isinstance(node, dict):
                _ensure_node_translations_map(node, canonical_provider=BACKEND_TRANSLATION_PROVIDER_KEY)
                normalized_selected_provider = _normalize_provider_key(selected_provider)
                effective_provider = normalized_selected_provider
                if normalized_selected_provider:
                    node["active_translation_provider"] = normalized_selected_provider
                if text_ru:
                    if not isinstance(node.get("translations"), dict):
                        node["translations"] = {}
                    provider_key = normalized_selected_provider or "overlay_provider"
                    node["translations"][provider_key] = {
                        "text": text_ru,
                        "source_lang": "en",
                        "target_lang": "ru",
                        "origin": "client_overlay",
                    }
                    if not effective_provider:
                        effective_provider = provider_key
                active = _pick_translation_entry(
                    node=node,
                    preferred_provider=effective_provider,
                    canonical_provider=BACKEND_TRANSLATION_PROVIDER_KEY,
                )
                if active is not None and normalized_selected_provider:
                    node["active_translation_provider"] = normalized_selected_provider
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
            analyzed = bool(row["analyzed"])
            document_id = row.get("document_id")
            if analyzed and document_id and not self._is_current_document_contract(str(document_id)):
                analyzed = False
                document_id = None
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
                    "analyzed": analyzed,
                    "document_id": document_id,
                }
            )
        return out

    def _is_current_document_contract(self, document_id: str) -> bool:
        doc_id = str(document_id or "").strip()
        if not doc_id:
            return False
        doc_dir = self._doc_artifacts_dir(document_id=doc_id)
        if not doc_dir.exists():
            return True
        manifest = self._load_stage_manifest(document_id=doc_id)
        if not isinstance(manifest, dict):
            return False
        immutable = manifest.get("immutable")
        if not isinstance(immutable, dict):
            return False
        build_version = str(immutable.get("contract_build_version") or "").strip()
        expected = str(os.getenv("ELA_SENTENCE_CONTRACT_BUILD_VERSION", CONTRACT_BUILD_VERSION)).strip() or CONTRACT_BUILD_VERSION
        return build_version == expected

    @staticmethod
    def _load_stage_manifest(*, document_id: str) -> dict[str, Any] | None:
        doc_dir = RuntimeMediaService._doc_artifacts_dir(document_id=document_id)
        target = doc_dir / "stage_manifest.json"
        if not target.exists() or not target.is_file():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _resolve_classifier_defaults(
        *,
        classifier_provider: str,
        classifier_model_path: str | None,
    ) -> tuple[str, str | None]:
        explicit_provider = str(classifier_provider or "").strip().lower()
        explicit_model_path = str(classifier_model_path or "").strip()

        env_provider = str(os.getenv("ELA_CLASSIFIER_PROVIDER", "")).strip().lower()
        env_model_path = str(os.getenv("ELA_CLASSIFIER_MODEL_PATH", "")).strip()

        default_deberta_dir = "artifacts/models/deberta_classifier_cefr"
        default_tabular_dirs = [
            "artifacts/models/tabular_joint_profile_full_ladder_xgboost_gpu_v2",
            "artifacts/models/tabular_joint_profile_random_forest_v1",
            "artifacts/models/tabular_cefr_baseline_full_ladder_xgboost_gpu_v1",
            "artifacts/models/tabular_cefr_baseline_full_ladder_random_forest_v2",
            "artifacts/models/tabular_cefr_baseline_full_ladder_random_forest",
            "artifacts/models/tabular_cefr_baseline_full_ladder_logreg",
        ]
        def _tabular_dir_ready(path: str) -> bool:
            return (
                os.path.isdir(path)
                and os.path.isfile(os.path.join(path, "classifier_metadata.json"))
                and (
                    os.path.isfile(os.path.join(path, "best_tabular_joint_profile.joblib"))
                    or os.path.isfile(os.path.join(path, "best_tabular_cefr_baseline.joblib"))
                )
            )

        deberta_dir = explicit_model_path or env_model_path or default_deberta_dir
        has_local_deberta = (
            os.path.isdir(deberta_dir)
            and os.path.isfile(os.path.join(deberta_dir, "classifier_metadata.json"))
        )
        default_tabular_dir = next(
            (candidate for candidate in default_tabular_dirs if _tabular_dir_ready(candidate)),
            default_tabular_dirs[0],
        )
        preferred_tabular_dir = default_tabular_dir
        has_local_tabular = _tabular_dir_ready(default_tabular_dir)
        if explicit_provider and explicit_provider != "rule":
            provider = explicit_provider
        elif env_provider:
            provider = env_provider
        else:
            provider = "tabular" if has_local_tabular else ("deberta" if has_local_deberta else "rule")

        if provider not in {"rule", "deberta", "tabular"}:
            raise ValueError("classifier_provider must be one of: rule | deberta | tabular")
        if provider == "deberta":
            return provider, deberta_dir
        if provider == "tabular":
            return provider, explicit_model_path or env_model_path or preferred_tabular_dir
        return provider, None

    def build_sentence_contract(
        self,
        *,
        sentence_text: str,
        sentence_idx: int = 0,
        model_dir: str | None = None,
        note_mode: str = "controlled",
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
        classifier_provider: str = "rule",
        classifier_model_path: str | None = None,
        classifier_device: str = "cuda",
        enable_grammar_classes: bool = True,
    ) -> dict[str, Any]:
        from ela_pipeline.inference.run import run_pipeline

        text = str(sentence_text or "").strip()
        if not text:
            raise ValueError("sentence_text must be non-empty")

        resolved_classifier_provider, resolved_classifier_model_path = self._resolve_classifier_defaults(
            classifier_provider=classifier_provider,
            classifier_model_path=classifier_model_path,
        )

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
            classifier_provider=resolved_classifier_provider,
            classifier_model_path=resolved_classifier_model_path,
            classifier_device=classifier_device,
            enable_grammar_classes=enable_grammar_classes,
        )
        sentence_node = self._select_sentence_node_from_contract(contract=contract, sentence_text=text)
        sentence_text_resolved = str(sentence_node.get("content") or text).strip() or text
        return {
            "sentence_text": sentence_text_resolved,
            "sentence_hash": build_sentence_hash(sentence_text_resolved, int(sentence_idx)),
            "sentence_node": sentence_node,
        }

    def analyze_text_contract(
        self,
        *,
        raw_text: str,
        sentences: list[Any] | None = None,
        generate_notes: bool = True,
    ) -> dict[str, Any]:
        from .razbor_pipeline import build_text_analysis_payload

        return build_text_analysis_payload(
            raw_text=raw_text,
            sentences=sentences,
            generate_notes=generate_notes,
        )

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
        subtitles_mode: str = "bilingual",
        voice_choice: str = "male",
        force_full_reprocess: bool = False,
        document_id: str | None = None,
        stage_callback: Callable[[str, float | None, str | None], None] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        if media_file_id is not None:
            current_settings = self.repo.get_workspace_state(f"{MEDIA_FILE_SETTINGS_PREFIX}{media_file_id}") or {}
            self.repo.set_workspace_state(
                f"{MEDIA_FILE_SETTINGS_PREFIX}{media_file_id}",
                {
                    "translation_provider": str(
                        translation_provider
                        or current_settings.get("translation_provider")
                        or "m2m100"
                    ).strip().lower(),
                    "subtitles_mode": str(subtitles_mode or current_settings.get("subtitles_mode") or "bilingual"),
                    "voice_choice": str(voice_choice or current_settings.get("voice_choice") or "male"),
                },
            )
        effective_translation_provider = str(translation_provider or "").strip().lower() or "m2m100"
        manifest_key = self._manifest_state_key(media_file_id=media_file_id, media_path=media_path)
        media_signature = self._build_media_signature(media_path=media_path)
        immutable_signature = self._build_immutable_signature(media_signature=media_signature)
        variant_signature = self._build_variant_signature(
            translation_provider=effective_translation_provider,
            subtitles_mode=subtitles_mode,
            voice_choice=voice_choice,
        )
        manifest_state = self.repo.get_workspace_state(manifest_key)
        cached_document_id = ""
        reused_immutable = False
        pipeline: MediaPipelineResult | None = None
        if isinstance(manifest_state, dict):
            cached_document_id = str(manifest_state.get("last_document_id") or "").strip()
        if not force_full_reprocess and cached_document_id and isinstance(manifest_state, dict):
            manifest_immutable = manifest_state.get("immutable")
            manifest_immutable_signature = ""
            if isinstance(manifest_immutable, dict):
                manifest_immutable_signature = str(manifest_immutable.get("signature") or "").strip()
            if not manifest_immutable_signature:
                manifest_immutable_signature = str(manifest_state.get("media_signature") or "").strip()
            if manifest_immutable_signature == immutable_signature:
                cached = self._load_cached_pipeline(document_id=cached_document_id)
                if cached is not None:
                    pipeline = cached
                    reused_immutable = True
                    if stage_callback is not None:
                        stage_callback("loading_file", 1.0, "Cache hit: reused extracted text.")
                        if cached.source_type in {"audio", "video"}:
                            stage_callback("transcribing_audio", 1.0, "Cache hit: skipped transcription.")
                        stage_callback("translating_text", 0.02, "Cache hit: reused sentence contracts.")
        if stage_callback is not None and not reused_immutable:
            stage_callback("loading_file", 0.25, "Loading source file")
        source_type = pipeline.source_type if pipeline is not None else self._detect_source_type(media_path)
        if source_type in {"audio", "video"} and stage_callback is not None and not reused_immutable:
            stage_callback("transcribing_audio", 0.05, "Preparing ASR")
        if pipeline is None:
            try:
                pipeline = run_media_pipeline(
                    source_path=media_path,
                    text_contract_builder=lambda *, raw_text, sentences: self._build_text_contract_from_backend(
                        raw_text=raw_text,
                        sentences=sentences,
                    ),
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

        selected_provider = effective_translation_provider
        if selected_provider and selected_provider not in {"m2m100", "our", "backend", "default"}:
            normalized_selected_provider = _normalize_provider_key(selected_provider) or "overlay_provider"
            sentence_total = max(len(pipeline.media_sentences), 1)
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
                        (idx + 1) / sentence_total,
                        f"Overlay sentence translation {idx + 1}/{sentence_total} via {selected_provider}",
                    )

            node_total = sum(
                self._count_nodes_recursive(row.get("sentence_node"))
                for row in pipeline.contract_sentences
                if isinstance(row.get("sentence_node"), dict)
            )
            node_total = max(node_total, 1)
            node_done = 0
            node_cache: dict[str, str] = {}
            for row in pipeline.contract_sentences:
                root = row.get("sentence_node")
                if not isinstance(root, dict):
                    continue
                for node in self._iter_nodes_recursive(root):
                    node_done += 1
                    self._overlay_translation_on_node(
                        node=node,
                        provider_key=normalized_selected_provider,
                        provider_name=selected_provider,
                        provider_credentials=provider_credentials,
                        cache=node_cache,
                    )
                    if stage_callback is not None:
                        stage_callback(
                            "translating_text",
                            min(1.0, node_done / node_total),
                            f"Overlay node translation {node_done}/{node_total} via {selected_provider}",
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
            media_file_id=media_file_id,
            media_path=media_path,
            source_type=pipeline.source_type,
            full_text=pipeline.full_text,
            text_hash=pipeline.text_hash,
            media_sentences=pipeline.media_sentences,
            contract_sentences=pipeline.contract_sentences,
            subtitles_mode=subtitles_mode,
            voice_choice=voice_choice,
            stage_callback=stage_callback,
        )
        if stage_callback is not None:
            stage_callback("exporting_files", 1.0, "Artifacts exported")
        duration_ms = int((time.monotonic() - started) * 1000)
        self.repo.update_document_status(document_id, "completed", processing_duration_ms=duration_ms)
        manifest_payload = {
            "schema_version": 1,
            "media_signature": media_signature,
            "last_document_id": document_id,
            "immutable": {
                "signature": immutable_signature,
                "contract_build_version": str(
                    os.getenv("ELA_SENTENCE_CONTRACT_BUILD_VERSION", CONTRACT_BUILD_VERSION)
                ).strip()
                or CONTRACT_BUILD_VERSION,
                "source_type": pipeline.source_type,
                "text_hash": pipeline.text_hash,
                "media_sentences_count": len(pipeline.media_sentences),
                "contract_sentences_count": len(pipeline.contract_sentences),
            },
            "variant": {
                "signature": variant_signature,
                "translation_provider": selected_provider,
                "subtitles_mode": str(subtitles_mode or "bilingual"),
                "voice_choice": str(voice_choice or "male"),
            },
            "reused_immutable_last_run": reused_immutable,
            "force_full_reprocess_last_run": bool(force_full_reprocess),
            "last_completed_at": dt.datetime.utcnow().isoformat() + "Z",
        }
        self.repo.set_workspace_state(manifest_key, manifest_payload)
        self._persist_stage_manifest_artifact(document_id=document_id, manifest=manifest_payload)
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

    def _persist_stage_manifest_artifact(self, *, document_id: str, manifest: dict[str, Any]) -> None:
        doc_dir = self._doc_artifacts_dir(document_id=document_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "stage_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _iter_nodes_recursive(root: dict[str, Any]) -> Iterable[dict[str, Any]]:
        stack: list[dict[str, Any]] = [root]
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            yield node
            children = node.get("linguistic_elements")
            if isinstance(children, list):
                for child in reversed(children):
                    if isinstance(child, dict):
                        stack.append(child)

    @classmethod
    def _count_nodes_recursive(cls, root: Any) -> int:
        if not isinstance(root, dict):
            return 0
        return sum(1 for _ in cls._iter_nodes_recursive(root))

    def _overlay_translation_on_node(
        self,
        *,
        node: dict[str, Any],
        provider_key: str,
        provider_name: str,
        provider_credentials: dict[str, str] | None,
        cache: dict[str, str],
    ) -> None:
        content = str(node.get("content") or "").strip()
        if not content:
            return
        cache_key = content.casefold()
        translated = cache.get(cache_key)
        if translated is None:
            translated = translate_text_with_provider(
                text=content,
                translation_provider=provider_name,
                provider_credentials=provider_credentials,
            )
            cache[cache_key] = translated
        _ensure_node_translations_map(node, canonical_provider=BACKEND_TRANSLATION_PROVIDER_KEY)
        translations = node.get("translations")
        if not isinstance(translations, dict):
            translations = {}
            node["translations"] = translations
        translations[provider_key] = {
            "text": translated,
            "source_lang": "en",
            "target_lang": "ru",
            "origin": "client_overlay",
        }
        node["active_translation_provider"] = provider_key

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
    def _manifest_state_key(*, media_file_id: str | None, media_path: str) -> str:
        if media_file_id:
            return f"{MEDIA_STAGE_MANIFEST_PREFIX}file:{media_file_id}"
        digest = hashlib.sha256(str(media_path).encode("utf-8")).hexdigest()[:16]
        return f"{MEDIA_STAGE_MANIFEST_PREFIX}path:{digest}"

    @staticmethod
    def _build_media_signature(*, media_path: str) -> str:
        path = Path(media_path)
        if not path.exists():
            return f"missing:{media_path}"
        stat = path.stat()
        payload = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_immutable_signature(*, media_signature: str) -> str:
        asr_model = str(os.getenv("ELA_MEDIA_ASR_MODEL", "base")).strip().lower() or "base"
        asr_lang = str(os.getenv("ELA_MEDIA_ASR_SOURCE_LANG", "en")).strip().lower() or "en"
        backend_url = str(os.getenv("ELA_SENTENCE_CONTRACT_BACKEND_URL", "")).strip().lower()
        contract_build_version = (
            str(os.getenv("ELA_SENTENCE_CONTRACT_BUILD_VERSION", CONTRACT_BUILD_VERSION)).strip()
            or CONTRACT_BUILD_VERSION
        )
        payload = f"{media_signature}|{asr_model}|{asr_lang}|{backend_url}|{contract_build_version}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_variant_signature(
        *,
        translation_provider: str | None,
        subtitles_mode: str,
        voice_choice: str,
    ) -> str:
        provider = str(translation_provider or "").strip().lower() or "m2m100"
        subs = str(subtitles_mode or "bilingual").strip().lower()
        voice = str(voice_choice or "male").strip().lower()
        return f"{provider}|{subs}|{voice}"

    @staticmethod
    def _doc_artifacts_dir(*, document_id: str) -> Path:
        base = Path(os.getenv("MEDIA_CONTRACT_ARTIFACTS_DIR", "artifacts/media_contracts"))
        return base / document_id

    def _load_cached_pipeline(self, *, document_id: str) -> MediaPipelineResult | None:
        doc_dir = self._doc_artifacts_dir(document_id=document_id)
        full_text_path = doc_dir / "full_text.txt"
        media_contract_path = doc_dir / "media_contract.json"
        contract_sentences_path = doc_dir / "contract_sentences.json"
        if not (full_text_path.exists() and media_contract_path.exists() and contract_sentences_path.exists()):
            return None
        try:
            full_text = full_text_path.read_text(encoding="utf-8")
            media_contract = json.loads(media_contract_path.read_text(encoding="utf-8"))
            contract_sentences = json.loads(contract_sentences_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        media_sentences = media_contract.get("media_sentences")
        if not isinstance(media_sentences, list) or not isinstance(contract_sentences, list):
            return None
        source_type = str(media_contract.get("source_type") or "").strip() or self._detect_source_type(
            str(media_contract.get("source_path") or "")
        )
        text_hash = str(media_contract.get("text_hash") or "").strip()
        if not text_hash:
            text_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
        return MediaPipelineResult(
            source_type=source_type,
            full_text=full_text,
            text_hash=text_hash,
            media_sentences=media_sentences,
            contract_sentences=contract_sentences,
        )

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
        subtitles_mode: str,
        voice_choice: str,
        force_full_reprocess: bool,
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
                    subtitles_mode=subtitles_mode,
                    voice_choice=voice_choice,
                    force_full_reprocess=force_full_reprocess,
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

    def _build_text_contract_from_backend(
        self,
        *,
        raw_text: str,
        sentences: list[str],
    ) -> dict[str, Any]:
        return self._request_text_contract(
            raw_text=raw_text,
            sentences=sentences,
        )

    def _persist_media_contract_artifacts(
        self,
        *,
        document_id: str,
        media_file_id: str | None,
        media_path: str,
        source_type: str,
        full_text: str,
        text_hash: str,
        media_sentences: list[dict[str, Any]],
        contract_sentences: list[dict[str, Any]],
        subtitles_mode: str = "bilingual",
        voice_choice: str = "male",
        stage_callback: Callable[[str, float | None, str | None], None] | None = None,
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

        if stage_callback is not None:
            stage_callback("generating_media", 0.32, "Writing full_text.txt")
        (doc_dir / "full_text.txt").write_text(full_text, encoding="utf-8")
        if stage_callback is not None:
            stage_callback("generating_media", 0.38, "Writing media_contract.json")
        (doc_dir / "media_contract.json").write_text(
            json.dumps(media_contract, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.45, "Writing contract_sentences.json")
        (doc_dir / "contract_sentences.json").write_text(
            json.dumps(contract_sentences, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.5, "Writing sentence_link.json")
        (doc_dir / "sentence_link.json").write_text(
            json.dumps(links, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.56, "Writing semantic_units_runtime.json")
        (doc_dir / "semantic_units_runtime.json").write_text(
            json.dumps(legacy_segments, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.62, "Writing bilingual_objects_runtime.json")
        (doc_dir / "bilingual_objects_runtime.json").write_text(
            json.dumps(legacy_segments, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.68, "Writing source subtitles")
        (doc_dir / "subtitles_en.srt").write_text(
            _build_srt(media_sentences, bilingual=False),
            encoding="utf-8",
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.72, "Writing bilingual subtitles")
        (doc_dir / "subtitles_bilingual.srt").write_text(
            _build_srt(media_sentences, bilingual=True),
            encoding="utf-8",
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.76, "Writing target subtitles")
        (doc_dir / "subtitles_target.srt").write_text(
            _build_srt([{**row, "text_eng": ""} for row in media_sentences], bilingual=True),
            encoding="utf-8",
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.82, "Rendering final media artifacts")
        self._export_final_media_artifacts(
            source_type=source_type,
            source_path=media_path,
            doc_dir=doc_dir,
            media_sentences=media_sentences,
            subtitles_mode=subtitles_mode,
            voice_choice=voice_choice,
            stage_callback=stage_callback,
        )
        if stage_callback is not None:
            stage_callback("generating_media", 0.96, "Archiving artifact snapshot")
        self._archive_artifacts_snapshot(
            document_id=document_id,
            media_file_id=media_file_id,
            source_dir=doc_dir,
        )
        if stage_callback is not None:
            stage_callback("generating_media", 1.0, "Contract artifacts persisted")

    @staticmethod
    def _archive_artifacts_snapshot(
        *,
        document_id: str,
        media_file_id: str | None,
        source_dir: Path,
    ) -> None:
        if not source_dir.exists() or not source_dir.is_dir():
            return
        archive_base = Path(os.getenv("MEDIA_CONTRACT_ARCHIVE_DIR", "artifacts/media_contract_archive"))
        file_key = str(media_file_id or "unbound").strip() or "unbound"
        stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        snapshot_dir = archive_base / file_key / f"{stamp}_{document_id}"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        for entry in source_dir.iterdir():
            if not entry.is_file():
                continue
            shutil.copy2(entry, snapshot_dir / entry.name)

    def _export_final_media_artifacts(
        self,
        *,
        source_type: str,
        source_path: str,
        doc_dir: Path,
        media_sentences: list[dict[str, Any]],
        subtitles_mode: str = "bilingual",
        voice_choice: str = "male",
        stage_callback: Callable[[str, float | None, str | None], None] | None = None,
    ) -> None:
        if source_type not in {"audio", "video"}:
            return

        tts_mp3 = doc_dir / "translated_audio_ru.mp3"
        source = Path(source_path)
        try:
            import edge_tts  # type: ignore
            if stage_callback is not None:
                stage_callback("exporting_files", 0.1, "Preparing audio segments")

            mode = str(subtitles_mode or "bilingual_sequential").strip().lower()
            source_modes = {"source", "source_only", "source only", "en"}
            target_modes = {"target", "target_only", "target only", "ru"}
            simultaneous_modes = {"bilingual_simultaneous", "bilingual simultaneous", "simultaneous"}
            include_source = mode in source_modes or mode not in source_modes.union(target_modes)
            include_target = mode in target_modes or mode not in source_modes.union(target_modes)
            bilingual_simultaneous = mode in simultaneous_modes

            timeline_segments: list[dict[str, Any]] = []
            source_subtitle_segments: list[dict[str, Any]] = []
            target_subtitle_segments: list[dict[str, Any]] = []
            sentence_windows: list[dict[str, Any]] = []
            segment_audio_files: list[Path] = []
            current_ms = 0
            gap_ms = 120
            voice_name = _voice_name_for_choice(voice_choice)
            with tempfile.TemporaryDirectory(prefix="ela_tts_") as tmpdir:
                tmp = Path(tmpdir)
                for idx, row in enumerate(media_sentences, start=1):
                    total_segments = max(1, len(media_sentences))
                    if stage_callback is not None:
                        stage_callback(
                            "exporting_files",
                            min(0.55, 0.12 + (idx - 1) / total_segments * 0.4),
                            f"Rendering media segment {idx}/{total_segments}",
                        )
                    text_en = str(row.get("sentence_text") or row.get("text_eng") or "").strip()
                    text_ru = str(row.get("text_ru") or "").strip()
                    window: dict[str, Any] = {
                        "text_eng": text_en,
                        "text_ru": text_ru,
                        "source_start_ms": None,
                        "source_end_ms": None,
                        "target_start_ms": None,
                        "target_end_ms": None,
                    }

                    if include_source:
                        start_ms_raw = int(row.get("start_ms") or 0)
                        end_ms_raw = int(row.get("end_ms") or 0)
                        source_seg = tmp / f"src_{idx:04d}.mp3"
                        if (
                            source.exists()
                            and end_ms_raw > start_ms_raw
                            and _extract_audio_segment_mp3(
                                source=source,
                                start_ms=start_ms_raw,
                                end_ms=end_ms_raw,
                                out_path=source_seg,
                            )
                        ):
                            dur_ms = _probe_audio_duration_ms(source_seg)
                            if dur_ms <= 0:
                                dur_ms = max(300, end_ms_raw - start_ms_raw)
                            start_ms = current_ms
                            end_ms = start_ms + dur_ms
                            timeline_segments.append(
                                {
                                    "start_ms": start_ms,
                                    "end_ms": end_ms,
                                    "text_eng": text_en,
                                    "text_ru": "",
                                }
                            )
                            source_subtitle_segments.append(
                                {
                                    "start_ms": start_ms,
                                    "end_ms": end_ms,
                                    "text_eng": text_en,
                                    "text_ru": "",
                                }
                            )
                            window["source_start_ms"] = start_ms
                            window["source_end_ms"] = end_ms
                            current_ms = end_ms + gap_ms
                            segment_audio_files.append(source_seg)

                    if include_target:
                        text_for_tts = text_ru or text_en
                        if not text_for_tts:
                            continue
                        target_seg = tmp / f"tgt_{idx:04d}.mp3"

                        async def _save_segment(path: Path = target_seg, text: str = text_for_tts) -> None:
                            await edge_tts.Communicate(text, voice_name).save(str(path))

                        asyncio.run(_save_segment())
                        if not target_seg.exists() or target_seg.stat().st_size <= 1024:
                            raise RuntimeError(f"edge-tts synthesis failed for sentence {idx}.")
                        dur_ms = _probe_audio_duration_ms(target_seg)
                        if dur_ms <= 0:
                            raise RuntimeError(f"Unable to probe TTS duration for sentence {idx}.")
                        start_ms = current_ms
                        end_ms = start_ms + dur_ms
                        timeline_segments.append(
                            {
                                "start_ms": start_ms,
                                "end_ms": end_ms,
                                "text_eng": "",
                                "text_ru": text_for_tts,
                            }
                        )
                        target_subtitle_segments.append(
                            {
                                "start_ms": start_ms,
                                "end_ms": end_ms,
                                "text_eng": "",
                                "text_ru": text_for_tts,
                            }
                        )
                        window["target_start_ms"] = start_ms
                        window["target_end_ms"] = end_ms
                        current_ms = end_ms + gap_ms
                        segment_audio_files.append(target_seg)
                    sentence_windows.append(window)

                if not segment_audio_files:
                    return

                if stage_callback is not None:
                    stage_callback("exporting_files", 0.62, "Concatenating final audio track")
                concat_txt = tmp / "concat.txt"
                concat_txt.write_text(
                    "\n".join(f"file '{p.as_posix()}'" for p in segment_audio_files),
                    encoding="utf-8",
                )
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(concat_txt),
                        "-c:a",
                        "libmp3lame",
                        "-q:a",
                        "2",
                        str(tts_mp3),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            # Rebuild subtitle files using real rendered timeline.
            if stage_callback is not None:
                stage_callback("exporting_files", 0.72, "Building subtitle files")
            bilingual_subtitle_segments: list[dict[str, Any]] = []
            if bilingual_simultaneous:
                for row in sentence_windows:
                    starts = [x for x in (row.get("source_start_ms"), row.get("target_start_ms")) if isinstance(x, int)]
                    ends = [x for x in (row.get("source_end_ms"), row.get("target_end_ms")) if isinstance(x, int)]
                    if not starts or not ends:
                        continue
                    bilingual_subtitle_segments.append(
                        {
                            "start_ms": min(starts),
                            "end_ms": max(ends),
                            "text_eng": str(row.get("text_eng") or ""),
                            "text_ru": str(row.get("text_ru") or ""),
                        }
                    )
            else:
                bilingual_subtitle_segments = timeline_segments
            if not bilingual_subtitle_segments:
                bilingual_subtitle_segments = timeline_segments

            (doc_dir / "subtitles_en.srt").write_text(
                _build_srt(source_subtitle_segments if source_subtitle_segments else timeline_segments, bilingual=False),
                encoding="utf-8",
            )
            (doc_dir / "subtitles_bilingual.srt").write_text(
                _build_srt(bilingual_subtitle_segments, bilingual=True),
                encoding="utf-8",
            )
            target_rows = target_subtitle_segments if target_subtitle_segments else [{**row, "text_eng": ""} for row in timeline_segments]
            (doc_dir / "subtitles_target.srt").write_text(
                _build_srt(target_rows, bilingual=True),
                encoding="utf-8",
            )

            if stage_callback is not None:
                stage_callback("exporting_files", 0.84, "Rendering final video")
            out_video = doc_dir / "translated_video_ru.mp4"
            subtitle_path = _subtitle_path_for_mode(doc_dir=doc_dir, subtitles_mode=subtitles_mode)
            escaped_subs = _ffmpeg_escape_filter_path(subtitle_path)
            if source_type == "video" and source.exists():
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(source),
                        "-i",
                        str(tts_mp3),
                        "-vf",
                        f"subtitles='{escaped_subs}'",
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "23",
                        "-c:a",
                        "aac",
                        "-shortest",
                        str(out_video),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=black:s=1280x720:r=25",
                        "-i",
                        str(tts_mp3),
                        "-vf",
                        f"subtitles='{escaped_subs}'",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-tune",
                        "stillimage",
                        "-c:a",
                        "aac",
                        "-shortest",
                        str(out_video),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            if stage_callback is not None:
                stage_callback("exporting_files", 1.0, "Media artifacts exported")
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
            with urlrequest.urlopen(req, timeout=self.sentence_contract_timeout_sec) as resp:  # nosec B310
                raw = resp.read().decode("utf-8")
        except TimeoutError as exc:
            raise RuntimeError(
                f"Backend sentence-contract API timeout after {self.sentence_contract_timeout_sec}s: {endpoint}"
            ) from exc
        except urlerror.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            message = f"Backend sentence-contract API error {exc.code}: {endpoint}"
            if body:
                message = f"{message}; body={body}"
            raise RuntimeError(message) from exc
        except (urlerror.URLError, OSError) as exc:
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

    def _request_text_contract(
        self,
        *,
        raw_text: str,
        sentences: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.sentence_contract_backend_url:
            raise RuntimeError("ELA_SENTENCE_CONTRACT_BACKEND_URL is required for text contract requests.")
        endpoint = f"{self.sentence_contract_backend_url.rstrip('/')}/api/analyze-text"
        payload_dict: dict[str, Any] = {"rawText": str(raw_text or "")}
        if sentences:
            payload_dict["sentences"] = [str(x) for x in sentences if str(x).strip()]
        payload = json.dumps(payload_dict).encode("utf-8")
        req = urlrequest.Request(endpoint, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urlrequest.urlopen(req, timeout=self.sentence_contract_timeout_sec) as resp:  # nosec B310
                raw = resp.read().decode("utf-8")
        except TimeoutError as exc:
            raise RuntimeError(
                f"Backend analyze-text API timeout after {self.sentence_contract_timeout_sec}s: {endpoint}"
            ) from exc
        except urlerror.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            message = f"Backend analyze-text API error {exc.code}: {endpoint}"
            if body:
                message = f"{message}; body={body}"
            raise RuntimeError(message) from exc
        except (urlerror.URLError, OSError) as exc:
            raise RuntimeError(f"Backend analyze-text API unavailable: {endpoint}") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from backend analyze-text API: {endpoint}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"Invalid payload type from backend analyze-text API: {endpoint}")
        if "contract" not in parsed:
            raise RuntimeError(f"Incomplete payload from backend analyze-text API: {endpoint}")
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
