"""Deterministic sentence-level keys for persistence."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

HASH_VERSION = "v1"


def canonicalize_text(text: str) -> str:
    raw = str(text or "")
    normalized = unicodedata.normalize("NFC", raw)
    collapsed = " ".join(normalized.split())
    return collapsed.strip()


def _canonical_context(context: dict[str, Any] | None) -> str:
    payload = context or {}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build_sentence_key(
    *,
    sentence_text: str,
    source_lang: str,
    target_lang: str,
    pipeline_context: dict[str, Any] | None,
    hash_version: str = HASH_VERSION,
) -> str:
    canonical_text = canonicalize_text(sentence_text)
    src = canonicalize_text(source_lang).lower()
    tgt = canonicalize_text(target_lang).lower()
    ctx = _canonical_context(pipeline_context)
    material = f"{hash_version}|{canonical_text}|{src}|{tgt}|{ctx}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

