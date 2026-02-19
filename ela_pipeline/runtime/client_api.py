"""JSON CLI facade for frontend integration (framework-agnostic)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ela_pipeline.legacy_bridge import (
    apply_node_edit,
    build_visualizer_payload_for_document,
)
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
    sub.add_parser("projects", help="List projects.")
    sub.add_parser("translation-config", help="Get translation providers config.")
    set_translation_config = sub.add_parser("set-translation-config", help="Set translation providers config from JSON file.")
    set_translation_config.add_argument("--input-json", required=True)

    create_project = sub.add_parser("create-project", help="Create project and select it.")
    create_project.add_argument("--name", required=True)

    sub.add_parser("selected-project", help="Get selected project from workspace state.")
    set_selected_project = sub.add_parser("set-selected-project", help="Set selected project.")
    set_selected_project.add_argument("--project-id", required=True)

    submit_media = sub.add_parser("submit-media", help="Submit media for local client-side processing.")
    submit_media.add_argument("--media-path", required=True)
    submit_media.add_argument("--duration-sec", type=int, required=True)
    submit_media.add_argument("--size-bytes", type=int, required=True)
    submit_media.add_argument("--project-id", default=None)
    submit_media.add_argument("--media-file-id", default=None)
    submit_media.add_argument("--translation-provider", default=None)
    submit_media.add_argument("--subtitles-mode", default=None)
    submit_media.add_argument("--voice-choice", default=None)

    queue_missing = sub.add_parser("queue-missing-content", help="Queue missing corpus content sync request.")
    queue_missing.add_argument("--source-text", required=True)
    queue_missing.add_argument("--source-lang", default="en")

    sync_list = sub.add_parser("sync-queue", help="List sync queue.")
    sync_list.add_argument("--limit", type=int, default=None)

    viz_payload = sub.add_parser("visualizer-payload", help="Build visualizer payload from contract JSON file.")
    viz_payload.add_argument("--input-json", required=True)

    viz_doc_payload = sub.add_parser(
        "visualizer-payload-document",
        help="Build visualizer payload from persisted local document by document_id.",
    )
    viz_doc_payload.add_argument("--document-id", required=True)

    doc_sentences = sub.add_parser(
        "document-sentences",
        help="List document sentence rows (idx/text/hash) for visualizer navigation.",
    )
    doc_sentences.add_argument("--document-id", required=True)

    doc_processing_status = sub.add_parser(
        "document-processing-status",
        help="Return document processing status/counters for UI polling.",
    )
    doc_processing_status.add_argument("--document-id", required=True)

    sentence_contract = sub.add_parser(
        "sentence-contract",
        help="Build one sentence-level contract payload (backend sentence API equivalent).",
    )
    sentence_contract.add_argument("--sentence-text", required=True)
    sentence_contract.add_argument("--sentence-idx", type=int, default=0)

    apply_edit = sub.add_parser("apply-edit", help="Apply node edit to contract JSON and save output.")
    apply_edit.add_argument("--input-json", required=True)
    apply_edit.add_argument("--output-json", required=True)
    apply_edit.add_argument("--sentence-text", required=True)
    apply_edit.add_argument("--node-id", required=True)
    apply_edit.add_argument("--field-path", required=True)
    apply_edit.add_argument("--new-value-json", required=True, help="JSON literal for new value.")

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

    if args.cmd == "projects":
        _print_json(media_service.list_projects())
        return
    if args.cmd == "translation-config":
        _print_json(media_service.get_translation_config())
        return
    if args.cmd == "set-translation-config":
        with open(args.input_json, "r", encoding="utf-8") as f:
            payload = json.load(f)
        _print_json(media_service.save_translation_config(payload))
        return

    if args.cmd == "create-project":
        _print_json(media_service.create_project(name=args.name))
        return

    if args.cmd == "selected-project":
        _print_json(media_service.get_selected_project())
        return

    if args.cmd == "set-selected-project":
        _print_json(media_service.set_selected_project(project_id=args.project_id))
        return

    if args.cmd == "submit-media":
        payload = media_service.submit_media(
            media_path=args.media_path,
            duration_seconds=args.duration_sec,
            size_bytes=args.size_bytes,
            project_id=args.project_id,
            media_file_id=args.media_file_id,
            translation_provider=args.translation_provider,
            subtitles_mode=args.subtitles_mode,
            voice_choice=args.voice_choice,
        )
        _print_json(payload)
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

    if args.cmd == "visualizer-payload":
        with open(args.input_json, "r", encoding="utf-8") as f:
            doc = json.load(f)
        _print_json(build_visualizer_payload_for_document(doc))
        return

    if args.cmd == "visualizer-payload-document":
        _print_json(media_service.get_visualizer_payload(document_id=args.document_id))
        return

    if args.cmd == "document-sentences":
        _print_json(media_service.list_document_sentences(document_id=args.document_id))
        return

    if args.cmd == "document-processing-status":
        _print_json(media_service.get_document_processing_status(document_id=args.document_id))
        return

    if args.cmd == "sentence-contract":
        _print_json(
            media_service.build_sentence_contract(
                sentence_text=args.sentence_text,
                sentence_idx=args.sentence_idx,
            )
        )
        return

    if args.cmd == "apply-edit":
        with open(args.input_json, "r", encoding="utf-8") as f:
            doc = json.load(f)
        new_value = json.loads(args.new_value_json)
        updated = apply_node_edit(
            doc,
            sentence_text=args.sentence_text,
            node_id=args.node_id,
            field_path=args.field_path,
            new_value=new_value,
        )
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(updated, f, ensure_ascii=False, indent=2)
        _print_json({"status": "ok", "output_json": args.output_json})
        return

    raise RuntimeError(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
