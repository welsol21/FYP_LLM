"""Offline/online runtime capability policy."""

from __future__ import annotations

import os
from dataclasses import dataclass

RUNTIME_MODE_OFFLINE = "offline"
RUNTIME_MODE_ONLINE = "online"
RUNTIME_MODE_AUTO = "auto"
_VALID_RUNTIME_MODES = {RUNTIME_MODE_AUTO, RUNTIME_MODE_OFFLINE, RUNTIME_MODE_ONLINE}


@dataclass(frozen=True)
class RuntimeCapabilities:
    mode: str
    phonetic_enabled: bool
    db_persistence_enabled: bool
    backend_jobs_enabled: bool


@dataclass(frozen=True)
class RuntimeFeatureRequest:
    enable_phonetic: bool = False
    enable_db_persistence: bool = False
    enable_backend_job: bool = False


def resolve_runtime_mode(cli_mode: str) -> str:
    mode = (cli_mode or RUNTIME_MODE_AUTO).strip().lower()
    if mode not in _VALID_RUNTIME_MODES:
        raise ValueError("runtime_mode must be one of: auto | offline | online")
    if mode == RUNTIME_MODE_AUTO:
        env_mode = os.getenv("ELA_RUNTIME_MODE", RUNTIME_MODE_ONLINE).strip().lower()
        if env_mode in {RUNTIME_MODE_OFFLINE, RUNTIME_MODE_ONLINE}:
            return env_mode
        return RUNTIME_MODE_ONLINE
    return mode


def build_runtime_capabilities(mode: str) -> RuntimeCapabilities:
    normalized = resolve_runtime_mode(mode)
    if normalized == RUNTIME_MODE_OFFLINE:
        # Offline profile: no backend dependency and no phonetic (license/deployment gate).
        return RuntimeCapabilities(
            mode=RUNTIME_MODE_OFFLINE,
            phonetic_enabled=False,
            db_persistence_enabled=False,
            backend_jobs_enabled=False,
        )
    return RuntimeCapabilities(
        mode=RUNTIME_MODE_ONLINE,
        phonetic_enabled=True,
        db_persistence_enabled=True,
        backend_jobs_enabled=True,
    )


def validate_runtime_feature_request(caps: RuntimeCapabilities, request: RuntimeFeatureRequest) -> None:
    if request.enable_phonetic and not caps.phonetic_enabled:
        raise RuntimeError(
            "Feature unavailable in offline mode: phonetic enrichment is disabled by runtime policy."
        )
    if request.enable_db_persistence and not caps.db_persistence_enabled:
        raise RuntimeError(
            "Feature unavailable in offline mode: DB persistence requires online backend connectivity."
        )
    if request.enable_backend_job and not caps.backend_jobs_enabled:
        raise RuntimeError(
            "Feature unavailable in offline mode: backend async jobs are disabled."
        )
