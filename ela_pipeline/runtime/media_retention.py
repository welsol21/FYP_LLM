"""Temporary media retention policy (TTL cleanup)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaRetentionConfig:
    temp_dir: Path
    ttl_hours: int

    @property
    def ttl_seconds(self) -> int:
        return self.ttl_hours * 3600


@dataclass(frozen=True)
class MediaCleanupReport:
    scanned_files: int
    deleted_files: int
    kept_files: int
    bytes_deleted: int


def load_media_retention_config_from_env() -> MediaRetentionConfig:
    temp_dir = Path(os.getenv("MEDIA_TEMP_DIR", "artifacts/media_tmp")).expanduser().resolve()
    raw_ttl = os.getenv("MEDIA_RETENTION_TTL_HOURS", "24").strip()
    try:
        ttl_hours = int(raw_ttl)
    except ValueError as exc:
        raise ValueError(f"MEDIA_RETENTION_TTL_HOURS must be integer, got: {raw_ttl!r}") from exc
    if ttl_hours <= 0:
        raise ValueError(f"MEDIA_RETENTION_TTL_HOURS must be > 0, got: {ttl_hours}")
    return MediaRetentionConfig(temp_dir=temp_dir, ttl_hours=ttl_hours)


def cleanup_temp_media(config: MediaRetentionConfig, now_epoch: float | None = None) -> MediaCleanupReport:
    now = now_epoch if now_epoch is not None else time.time()
    scanned = 0
    deleted = 0
    kept = 0
    bytes_deleted = 0

    if not config.temp_dir.exists():
        return MediaCleanupReport(scanned_files=0, deleted_files=0, kept_files=0, bytes_deleted=0)

    for root, _dirs, files in os.walk(config.temp_dir):
        for name in files:
            file_path = Path(root) / name
            try:
                stat = file_path.stat()
            except FileNotFoundError:
                continue

            scanned += 1
            age_seconds = now - stat.st_mtime
            if age_seconds > config.ttl_seconds:
                size = stat.st_size
                try:
                    file_path.unlink()
                except FileNotFoundError:
                    continue
                deleted += 1
                bytes_deleted += size
            else:
                kept += 1

    return MediaCleanupReport(
        scanned_files=scanned,
        deleted_files=deleted,
        kept_files=kept,
        bytes_deleted=bytes_deleted,
    )
