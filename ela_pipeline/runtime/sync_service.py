"""Client-side sync queue for content missing in shared corpus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ela_pipeline.client_storage import LocalSQLiteRepository


@dataclass
class SyncService:
    """Queue-based sync service to be consumed by UI or background worker."""

    db_path: str | Path

    def __post_init__(self) -> None:
        self.repo = LocalSQLiteRepository(self.db_path)

    def queue_missing_content(self, *, source_text: str, source_lang: str = "en", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "source_text": source_text,
            "source_lang": source_lang,
            "metadata": metadata or {},
        }
        return self.repo.enqueue_sync_request(
            request_type="missing_content",
            payload=payload,
        )

    def queue_large_media_reference(
        self,
        *,
        media_path: str,
        duration_seconds: int,
        size_bytes: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "media_path": media_path,
            "duration_seconds": duration_seconds,
            "size_bytes": size_bytes,
            "metadata": metadata or {},
        }
        return self.repo.enqueue_sync_request(
            request_type="large_media_reference",
            payload=payload,
        )

    def list_queued(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self.repo.list_sync_requests(status="queued", limit=limit)

    def mark_sent(self, request_id: str) -> None:
        self.repo.update_sync_request_status(request_id, "sent")

    def mark_failed(self, request_id: str) -> None:
        self.repo.update_sync_request_status(request_id, "failed")
