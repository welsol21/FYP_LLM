"""Media routing and validation policy (duration + size)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .capabilities import RuntimeCapabilities


@dataclass(frozen=True)
class MediaPolicyLimits:
    max_duration_min: int
    max_size_local_mb: int
    max_size_backend_mb: int

    @property
    def max_duration_seconds(self) -> int:
        return self.max_duration_min * 60

    @property
    def max_size_local_bytes(self) -> int:
        return self.max_size_local_mb * 1024 * 1024

    @property
    def max_size_backend_bytes(self) -> int:
        return self.max_size_backend_mb * 1024 * 1024


@dataclass(frozen=True)
class MediaRoutingDecision:
    route: str  # local | backend | reject
    reason: str


def _to_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got: {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got: {value}")
    return value


def load_media_policy_limits_from_env() -> MediaPolicyLimits:
    return MediaPolicyLimits(
        max_duration_min=_to_int_env("MEDIA_MAX_DURATION_MIN", 15),
        max_size_local_mb=_to_int_env("MEDIA_MAX_SIZE_LOCAL_MB", 250),
        max_size_backend_mb=_to_int_env("MEDIA_MAX_SIZE_BACKEND_MB", 2048),
    )


def _fmt_metrics(duration_seconds: int, size_bytes: int, limits: MediaPolicyLimits) -> str:
    duration_min = duration_seconds / 60.0
    size_mb = size_bytes / (1024 * 1024)
    return (
        f"duration={duration_min:.2f}m (limit_local={limits.max_duration_min}m), "
        f"size={size_mb:.2f}MB (limit_local={limits.max_size_local_mb}MB, "
        f"limit_backend={limits.max_size_backend_mb}MB)"
    )


def decide_media_route(
    *,
    duration_seconds: int,
    size_bytes: int,
    limits: MediaPolicyLimits,
    runtime_caps: RuntimeCapabilities,
) -> MediaRoutingDecision:
    if duration_seconds <= 0:
        raise ValueError(f"duration_seconds must be > 0, got: {duration_seconds}")
    if size_bytes <= 0:
        raise ValueError(f"size_bytes must be > 0, got: {size_bytes}")

    metrics = _fmt_metrics(duration_seconds, size_bytes, limits)

    if size_bytes > limits.max_size_backend_bytes:
        return MediaRoutingDecision(
            route="reject",
            reason=f"Media rejected: exceeds backend hard size limit; {metrics}",
        )

    local_ok = duration_seconds <= limits.max_duration_seconds and size_bytes <= limits.max_size_local_bytes
    if local_ok:
        return MediaRoutingDecision(
            route="local",
            reason=f"Media accepted for local processing; {metrics}",
        )

    if not runtime_caps.backend_jobs_enabled:
        return MediaRoutingDecision(
            route="reject",
            reason=f"Media requires backend route but backend jobs are disabled in offline mode; {metrics}",
        )

    return MediaRoutingDecision(
        route="backend",
        reason=f"Media routed to backend async processing; {metrics}",
    )
