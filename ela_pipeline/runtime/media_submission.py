"""Submission helper: media policy + orchestration + local queue."""

from __future__ import annotations

from typing import Any

from ela_pipeline.client_storage import LocalSQLiteRepository

from .capabilities import RuntimeCapabilities
from .media_orchestrator import plan_media_execution
from .media_policy import MediaPolicyLimits


def submit_media_for_processing(
    *,
    repo: LocalSQLiteRepository,
    media_path: str,
    duration_seconds: int,
    size_bytes: int,
    runtime_caps: RuntimeCapabilities,
    limits: MediaPolicyLimits,
    project_id: str | None = None,
    media_file_id: str | None = None,
    prefer_backend_for_enrichment: bool = False,
) -> dict[str, Any]:
    plan = plan_media_execution(
        media_path=media_path,
        duration_seconds=duration_seconds,
        size_bytes=size_bytes,
        limits=limits,
        runtime_caps=runtime_caps,
        prefer_backend_for_enrichment=prefer_backend_for_enrichment,
    )
    if plan.action == "run_local":
        return {
            "route": "local",
            "status": "accepted_local",
            "message": plan.message,
            "job_id": None,
        }
    return {
        "route": "reject",
        "status": "rejected",
        "message": plan.message,
        "job_id": None,
    }
