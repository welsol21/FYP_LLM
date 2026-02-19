"""Lightweight HTTP bridge for frontend -> runtime service."""

from __future__ import annotations

import cgi
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import RuntimeMediaService


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


SERVICE = RuntimeMediaService(
    db_path=os.getenv("ELA_CLIENT_DB_PATH", "artifacts/client_state.sqlite3"),
    runtime_mode=os.getenv("ELA_RUNTIME_MODE", "auto"),
    deployment_mode=os.getenv("ELA_DEPLOYMENT_MODE", "auto"),
    demo_auto_progress_jobs=os.getenv("ELA_DEMO_AUTO_PROGRESS_JOBS", "1") == "1",
)


class RuntimeApiHandler(BaseHTTPRequestHandler):
    server_version = "ELARuntimeHTTP/1.0"

    def _send_json(self, payload: dict | list, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({"status": "ok"})
            return
        if path == "/api/ui-state":
            self._send_json(SERVICE.get_ui_state())
            return
        if path == "/api/projects":
            self._send_json(SERVICE.list_projects())
            return
        if path == "/api/selected-project":
            self._send_json(SERVICE.get_selected_project())
            return
        if path == "/api/backend-jobs":
            self._send_json(SERVICE.list_backend_jobs())
            return
        if path == "/api/backend-job-status":
            job_id = (query.get("job_id") or [""])[0]
            if not job_id:
                self._send_json({"error": "job_id is required"}, status=400)
                return
            self._send_json(SERVICE.get_backend_job_status(job_id=job_id))
            return
        if path == "/api/files":
            project_id = (query.get("project_id") or [None])[0]
            self._send_json(SERVICE.list_files(project_id=project_id))
            return
        if path == "/api/visualizer-payload":
            document_id = (query.get("document_id") or [""])[0]
            if not document_id:
                self._send_json({}, status=200)
                return
            self._send_json(SERVICE.get_visualizer_payload(document_id=document_id))
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        content_type = self.headers.get("Content-Type", "")

        if path == "/api/upload":
            if "multipart/form-data" not in content_type:
                self._send_json({"error": "multipart/form-data is required"}, status=400)
                return
            storage = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                },
            )
            upload_item = storage["file"] if "file" in storage else None
            if upload_item is None or not getattr(upload_item, "filename", None):
                self._send_json({"error": "file field is required"}, status=400)
                return
            base_dir = Path(os.getenv("MEDIA_TEMP_DIR", "artifacts/media_tmp")) / "uploads"
            base_dir.mkdir(parents=True, exist_ok=True)
            safe_name = Path(str(upload_item.filename)).name
            save_path = base_dir / safe_name
            data = upload_item.file.read()
            save_path.write_bytes(data)
            self._send_json(
                {
                    "fileName": safe_name,
                    "mediaPath": str(save_path),
                    "sizeBytes": len(data),
                }
            )
            return

        body = self._read_json_body()

        if path == "/api/submit-media":
            media_path = str(body.get("mediaPath") or body.get("media_path") or "").strip()
            duration = _env_int("ELA_DEFAULT_DURATION_SEC", 1) if body.get("durationSec") is None else int(body.get("durationSec") or 0)
            size = _env_int("ELA_DEFAULT_SIZE_BYTES", 0) if body.get("sizeBytes") is None else int(body.get("sizeBytes") or 0)
            if not media_path:
                self._send_json({"error": "mediaPath is required"}, status=400)
                return
            if duration <= 0:
                duration = 1
            try:
                payload = SERVICE.submit_media(
                    media_path=media_path,
                    duration_seconds=duration,
                    size_bytes=size,
                    project_id=body.get("projectId"),
                    media_file_id=body.get("mediaFileId"),
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
            return
        if path == "/api/projects":
            name = str(body.get("name") or "").strip()
            if not name:
                self._send_json({"error": "name is required"}, status=400)
                return
            self._send_json(SERVICE.create_project(name=name))
            return

        if path == "/api/selected-project":
            project_id = str(body.get("projectId") or body.get("project_id") or "").strip()
            if not project_id:
                self._send_json({"error": "projectId is required"}, status=400)
                return
            selected = SERVICE.set_selected_project(project_id=project_id)
            if not selected.get("project_id"):
                self._send_json({"error": "project not found"}, status=404)
                return
            self._send_json(selected)
            return
        if path == "/api/register-media":
            project_id = str(body.get("projectId") or body.get("project_id") or "").strip()
            media_path = str(body.get("mediaPath") or body.get("media_path") or "").strip()
            name = str(body.get("name") or "").strip()
            size = int(body.get("sizeBytes") or body.get("size_bytes") or 0)
            duration = body.get("durationSec")
            if not project_id:
                self._send_json({"error": "projectId is required"}, status=400)
                return
            if not name:
                self._send_json({"error": "name is required"}, status=400)
                return
            if not media_path:
                self._send_json({"error": "mediaPath is required"}, status=400)
                return
            created = SERVICE.register_media_file(
                project_id=project_id,
                name=name,
                media_path=media_path,
                size_bytes=size,
                duration_seconds=int(duration) if duration is not None else None,
            )
            if created.get("error") == "project_not_found":
                self._send_json({"error": "project not found"}, status=404)
                return
            self._send_json(created)
            return

        if path == "/api/retry-backend-job":
            job_id = str(body.get("jobId") or body.get("job_id") or "")
            if not job_id:
                self._send_json({"error": "jobId is required"}, status=400)
                return
            self._send_json(SERVICE.retry_backend_job(job_id=job_id))
            return

        if path == "/api/resume-backend-jobs":
            self._send_json(SERVICE.resume_backend_jobs())
            return

        if path == "/api/sync-backend-result":
            job_id = str(body.get("jobId") or body.get("job_id") or "")
            if not job_id:
                self._send_json({"error": "jobId is required"}, status=400)
                return
            self._send_json(SERVICE.sync_backend_result_auto(job_id=job_id))
            return

        if path == "/api/apply-edit":
            document_id = str(body.get("documentId") or "")
            sentence_text = str(body.get("sentenceText") or "")
            node_id = str(body.get("nodeId") or "")
            field_path = str(body.get("fieldPath") or "")
            if not document_id:
                self._send_json({"status": "error", "message": "documentId is required."}, status=400)
                return
            result = SERVICE.apply_document_edit(
                document_id=document_id,
                sentence_text=sentence_text,
                node_id=node_id,
                field_path=field_path,
                new_value=body.get("newValue"),
            )
            self._send_json(result, status=200 if result.get("status") == "ok" else 400)
            return

        if path == "/api/sentence-contract":
            sentence_text = str(body.get("sentenceText") or body.get("sentence_text") or "").strip()
            if not sentence_text:
                self._send_json({"error": "sentenceText is required"}, status=400)
                return
            sentence_idx_raw = body.get("sentenceIdx", body.get("sentence_idx", 0))
            try:
                sentence_idx = int(sentence_idx_raw)
            except (TypeError, ValueError):
                self._send_json({"error": "sentenceIdx must be an integer"}, status=400)
                return
            try:
                payload = SERVICE.build_sentence_contract(
                    sentence_text=sentence_text,
                    sentence_idx=sentence_idx,
                )
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
            return

        self._send_json({"error": "Not found"}, status=404)


def main() -> None:
    host = os.getenv("ELA_RUNTIME_HTTP_HOST", "0.0.0.0")
    port = _env_int("ELA_RUNTIME_HTTP_PORT", 8000)
    server = ThreadingHTTPServer((host, port), RuntimeApiHandler)
    print(f"[runtime-api] serving on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
