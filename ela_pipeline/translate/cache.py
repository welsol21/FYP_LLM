"""Translation cache helpers (optional Redis backend)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Protocol


class TranslationCache(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class InMemoryTranslationCache:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        # TTL ignored for in-memory lightweight fallback.
        self._store[key] = value


@dataclass
class RedisTranslationCache:
    redis_url: str

    def __post_init__(self) -> None:
        try:
            import redis  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise ImportError("redis package is required for RedisTranslationCache") from exc
        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.setex(key, ttl_seconds, value)


def build_translation_cache_key(*, source_text: str, source_lang: str, target_lang: str, model_name: str) -> str:
    payload = f"{model_name}|{source_lang}|{target_lang}|{source_text}".encode("utf-8")
    return "ela:tr:" + hashlib.sha256(payload).hexdigest()


def build_translation_cache_from_env() -> TranslationCache | None:
    backend = os.getenv("ELA_TRANSLATION_CACHE_BACKEND", "").strip().lower()
    if not backend:
        return None
    if backend == "memory":
        return InMemoryTranslationCache()
    if backend == "redis":
        redis_url = os.getenv("ELA_TRANSLATION_CACHE_URL", "").strip()
        if not redis_url:
            raise ValueError("ELA_TRANSLATION_CACHE_URL is required for redis cache backend.")
        return RedisTranslationCache(redis_url=redis_url)
    raise ValueError("ELA_TRANSLATION_CACHE_BACKEND must be one of: memory|redis (or empty)")
