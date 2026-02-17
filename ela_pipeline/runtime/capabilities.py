"""Offline/online runtime capability policy."""

from __future__ import annotations

import os
from dataclasses import dataclass

RUNTIME_MODE_OFFLINE = "offline"
RUNTIME_MODE_ONLINE = "online"
RUNTIME_MODE_AUTO = "auto"
_VALID_RUNTIME_MODES = {RUNTIME_MODE_AUTO, RUNTIME_MODE_OFFLINE, RUNTIME_MODE_ONLINE}

DEPLOYMENT_MODE_AUTO = "auto"
DEPLOYMENT_MODE_LOCAL = "local"
DEPLOYMENT_MODE_BACKEND = "backend"
DEPLOYMENT_MODE_DISTRIBUTED = "distributed"
_VALID_DEPLOYMENT_MODES = {
    DEPLOYMENT_MODE_AUTO,
    DEPLOYMENT_MODE_LOCAL,
    DEPLOYMENT_MODE_BACKEND,
    DEPLOYMENT_MODE_DISTRIBUTED,
}

PHONETIC_POLICY_ENABLED = "enabled"
PHONETIC_POLICY_DISABLED = "disabled"
PHONETIC_POLICY_BACKEND_ONLY = "backend_only"
_VALID_PHONETIC_POLICIES = {
    PHONETIC_POLICY_ENABLED,
    PHONETIC_POLICY_DISABLED,
    PHONETIC_POLICY_BACKEND_ONLY,
}


@dataclass(frozen=True)
class RuntimeCapabilities:
    mode: str
    deployment_mode: str
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


def resolve_deployment_mode(cli_mode: str) -> str:
    mode = (cli_mode or DEPLOYMENT_MODE_AUTO).strip().lower()
    if mode not in _VALID_DEPLOYMENT_MODES:
        raise ValueError("deployment_mode must be one of: auto | local | backend | distributed")
    if mode == DEPLOYMENT_MODE_AUTO:
        env_mode = os.getenv("ELA_DEPLOYMENT_MODE", DEPLOYMENT_MODE_LOCAL).strip().lower()
        if env_mode in {DEPLOYMENT_MODE_LOCAL, DEPLOYMENT_MODE_BACKEND, DEPLOYMENT_MODE_DISTRIBUTED}:
            return env_mode
        return DEPLOYMENT_MODE_LOCAL
    return mode


def resolve_phonetic_policy() -> str:
    policy = os.getenv("ELA_PHONETIC_POLICY", PHONETIC_POLICY_ENABLED).strip().lower()
    if policy not in _VALID_PHONETIC_POLICIES:
        raise ValueError("ELA_PHONETIC_POLICY must be one of: enabled | disabled | backend_only")
    return policy


def build_runtime_capabilities(mode: str, deployment_mode: str = DEPLOYMENT_MODE_AUTO) -> RuntimeCapabilities:
    normalized = resolve_runtime_mode(mode)
    resolved_deployment = resolve_deployment_mode(deployment_mode)
    phonetic_policy = resolve_phonetic_policy()
    phonetic_allowed = True
    if phonetic_policy == PHONETIC_POLICY_DISABLED:
        phonetic_allowed = False
    elif phonetic_policy == PHONETIC_POLICY_BACKEND_ONLY and resolved_deployment != DEPLOYMENT_MODE_BACKEND:
        phonetic_allowed = False

    if normalized == RUNTIME_MODE_OFFLINE:
        # Offline profile: no backend dependency and no phonetic (license/deployment gate).
        return RuntimeCapabilities(
            mode=RUNTIME_MODE_OFFLINE,
            deployment_mode=resolved_deployment,
            phonetic_enabled=False,
            db_persistence_enabled=False,
            backend_jobs_enabled=False,
        )
    return RuntimeCapabilities(
        mode=RUNTIME_MODE_ONLINE,
        deployment_mode=resolved_deployment,
        phonetic_enabled=phonetic_allowed,
        db_persistence_enabled=True,
        backend_jobs_enabled=True,
    )


def validate_runtime_feature_request(caps: RuntimeCapabilities, request: RuntimeFeatureRequest) -> None:
    if request.enable_phonetic and not caps.phonetic_enabled:
        raise RuntimeError(
            "Feature unavailable: phonetic enrichment is disabled by runtime policy/license gate for this mode."
        )
    if request.enable_db_persistence and not caps.db_persistence_enabled:
        raise RuntimeError(
            "Feature unavailable in offline mode: DB persistence requires online backend connectivity."
        )
    if request.enable_backend_job and not caps.backend_jobs_enabled:
        raise RuntimeError(
            "Feature unavailable in offline mode: backend async jobs are disabled."
        )
