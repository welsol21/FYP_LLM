"""Frontend-ready runtime service: capabilities, media submit, backend queue access."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ela_pipeline.client_storage import LocalSQLiteRepository

from .capabilities import build_runtime_capabilities, resolve_runtime_mode
from .media_policy import MediaPolicyLimits, load_media_policy_limits_from_env
from .media_submission import submit_media_for_processing
from .ui_state import build_runtime_ui_state, build_submission_ui_feedback


@dataclass
class RuntimeMediaService:
    """Single integration point for UI/desktop layer."""

    db_path: str | Path
    runtime_mode: str = "auto"
    limits: MediaPolicyLimits | None = None

    def __post_init__(self) -> None:
        self.repo = LocalSQLiteRepository(self.db_path)
        self.effective_mode = resolve_runtime_mode(self.runtime_mode)
        self.caps = build_runtime_capabilities(self.effective_mode)
        self.limits = self.limits or load_media_policy_limits_from_env()

    def get_ui_state(self) -> dict[str, Any]:
        return build_runtime_ui_state(self.caps)

    def submit_media(
        self,
        *,
        media_path: str,
        duration_seconds: int,
        size_bytes: int,
        project_id: str | None = None,
        media_file_id: str | None = None,
    ) -> dict[str, Any]:
        raw = submit_media_for_processing(
            repo=self.repo,
            media_path=media_path,
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
            runtime_caps=self.caps,
            limits=self.limits,
            project_id=project_id,
            media_file_id=media_file_id,
        )
        return {
            "result": raw,
            "ui_feedback": build_submission_ui_feedback(raw),
        }

    def list_backend_jobs(self, *, status: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        return self.repo.list_backend_jobs(status=status, limit=limit)
