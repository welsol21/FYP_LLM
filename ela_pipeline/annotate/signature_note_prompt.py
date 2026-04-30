"""Prompt helpers for signature-only note generation."""

from __future__ import annotations

from typing import Any


SIGNATURE_ONLY_PROMPT_TEMPLATE_VERSION = "signature_only_input_v1"


def build_signature_note_training_prompt(
    *,
    signature_text: str,
    node_level: str,
    audience_level: str = "intermediate",
    depth: int = 2,
    family_id: str = "",
) -> str:
    del node_level, audience_level, depth, family_id
    return str(signature_text or "").strip()
