"""UI-facing helpers for runtime capability badges and fallback messaging."""

from __future__ import annotations

from typing import Any

from .capabilities import RuntimeCapabilities


def build_runtime_ui_state(caps: RuntimeCapabilities) -> dict[str, Any]:
    """Return UI-friendly capability matrix for badges and disabled states."""
    feature_state = {
        "phonetic": {
            "enabled": caps.phonetic_enabled,
            "reason_if_disabled": (
                "Unavailable in offline mode (license/deployment gate)." if not caps.phonetic_enabled else ""
            ),
        },
        "db_persistence": {
            "enabled": caps.db_persistence_enabled,
            "reason_if_disabled": (
                "Unavailable in offline mode (requires backend connectivity)." if not caps.db_persistence_enabled else ""
            ),
        },
    }
    return {
        "runtime_mode": caps.mode,
        "deployment_mode": caps.deployment_mode,
        "badges": {
            "mode": f"Mode: {caps.mode}",
            "deployment": f"Deployment: {caps.deployment_mode}",
            "phonetic": "Phonetic: on" if caps.phonetic_enabled else "Phonetic: off",
        },
        "features": feature_state,
    }


def build_submission_ui_feedback(submission_result: dict[str, Any]) -> dict[str, str]:
    """Normalize submission result into compact UI message payload."""
    route = str(submission_result.get("route") or "")
    message = str(submission_result.get("message") or "")
    if route == "local":
        return {
            "severity": "info",
            "title": "Local processing started",
            "message": message,
        }
    return {
        "severity": "error",
        "title": "File rejected by media policy",
        "message": message,
    }
