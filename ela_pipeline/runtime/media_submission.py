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
) -> dict[str, Any]:
    plan = plan_media_execution(
        media_path=media_path,
        duration_seconds=duration_seconds,
        size_bytes=size_bytes,
        limits=limits,
        runtime_caps=runtime_caps,
    )
    if plan.action == "run_local":
        return {
            "route": "local",
            "status": "accepted_local",
            "message": plan.message,
            "job_id": None,
        }
    if plan.action == "enqueue_backend":
        payload = plan.backend_job_payload or {}
        job = repo.enqueue_backend_job(
            request_payload=payload,
            project_id=project_id,
            media_file_id=media_file_id,
        )
        return {
            "route": "backend",
            "status": "queued_backend",
            "message": plan.message,
            "job_id": job["id"],
        }
    return {
        "route": "reject",
        "status": "rejected",
        "message": plan.message,
        "job_id": None,
    }
