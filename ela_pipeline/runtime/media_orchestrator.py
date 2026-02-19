"""High-level media execution orchestration from routing policy decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capabilities import RuntimeCapabilities
from .media_policy import MediaPolicyLimits, decide_media_route


@dataclass(frozen=True)
class MediaExecutionPlan:
    action: str  # run_local | enqueue_backend | reject
    message: str
    backend_job_payload: dict[str, Any] | None = None


def plan_media_execution(
    *,
    media_path: str,
    duration_seconds: int,
    size_bytes: int,
    limits: MediaPolicyLimits,
    runtime_caps: RuntimeCapabilities,
    prefer_backend_for_enrichment: bool = False,
) -> MediaExecutionPlan:
    decision = decide_media_route(
        duration_seconds=duration_seconds,
        size_bytes=size_bytes,
        limits=limits,
        runtime_caps=runtime_caps,
        prefer_backend_for_enrichment=prefer_backend_for_enrichment,
    )
    if decision.route == "local":
        return MediaExecutionPlan(
            action="run_local",
            message=decision.reason,
            backend_job_payload=None,
        )
    if decision.route == "backend":
        return MediaExecutionPlan(
            action="enqueue_backend",
            message=decision.reason,
            backend_job_payload={
                "media_path": media_path,
                "duration_seconds": duration_seconds,
                "size_bytes": size_bytes,
                "policy_reason": decision.reason,
            },
        )
    return MediaExecutionPlan(
        action="reject",
        message=decision.reason,
        backend_job_payload=None,
    )
