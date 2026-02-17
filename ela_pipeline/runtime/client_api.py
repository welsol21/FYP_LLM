"""JSON CLI facade for frontend integration (framework-agnostic)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import RuntimeMediaService
from .sync_service import SyncService


def _print_json(payload):
    print(json.dumps(payload, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Runtime client API facade (JSON output).")
    parser.add_argument("--db-path", default="artifacts/client_state.sqlite3")
    parser.add_argument("--runtime-mode", default="auto", choices=["auto", "offline", "online"])
    parser.add_argument("--deployment-mode", default="auto", choices=["auto", "local", "backend", "distributed"])

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ui-state", help="Return runtime UI payload.")

    submit_media = sub.add_parser("submit-media", help="Submit media for local/backend routing.")
    submit_media.add_argument("--media-path", required=True)
    submit_media.add_argument("--duration-sec", type=int, required=True)
    submit_media.add_argument("--size-bytes", type=int, required=True)
    submit_media.add_argument("--project-id", default=None)
    submit_media.add_argument("--media-file-id", default=None)

    jobs = sub.add_parser("backend-jobs", help="List local backend job queue.")
    jobs.add_argument("--status", default=None)
    jobs.add_argument("--limit", type=int, default=None)

    queue_missing = sub.add_parser("queue-missing-content", help="Queue missing corpus content sync request.")
    queue_missing.add_argument("--source-text", required=True)
    queue_missing.add_argument("--source-lang", default="en")

    sync_list = sub.add_parser("sync-queue", help="List sync queue.")
    sync_list.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()
    db_path = Path(args.db_path)
    media_service = RuntimeMediaService(
        db_path=db_path,
        runtime_mode=args.runtime_mode,
        deployment_mode=args.deployment_mode,
    )
    sync_service = SyncService(db_path=db_path)

    if args.cmd == "ui-state":
        _print_json(media_service.get_ui_state())
        return

    if args.cmd == "submit-media":
        payload = media_service.submit_media(
            media_path=args.media_path,
            duration_seconds=args.duration_sec,
            size_bytes=args.size_bytes,
            project_id=args.project_id,
            media_file_id=args.media_file_id,
        )
        _print_json(payload)
        return

    if args.cmd == "backend-jobs":
        _print_json(media_service.list_backend_jobs(status=args.status, limit=args.limit))
        return

    if args.cmd == "queue-missing-content":
        _print_json(
            sync_service.queue_missing_content(
                source_text=args.source_text,
                source_lang=args.source_lang,
            )
        )
        return

    if args.cmd == "sync-queue":
        _print_json(sync_service.list_queued(limit=args.limit))
        return

    raise RuntimeError(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
