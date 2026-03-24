"""Lightweight HTTP bridge for frontend -> runtime service."""

from __future__ import annotations

import json
import os
import cgi
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .media_pipeline import warmup_media_models
from .service import RuntimeMediaService


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip()


def _resolve_classifier_settings() -> tuple[str, str | None]:
    provider_raw = _env_str("ELA_CLASSIFIER_PROVIDER", "").lower()
    model_path = _env_str("ELA_CLASSIFIER_MODEL_PATH", "")

    default_tabular_dirs = [
        "artifacts/models/tabular_joint_profile_full_ladder_xgboost_gpu_v2",
        "artifacts/models/tabular_joint_profile_random_forest_v1",
        "artifacts/models/tabular_cefr_baseline_full_ladder_xgboost_gpu_v1",
        "artifacts/models/tabular_cefr_baseline_full_ladder_random_forest_v2",
        "artifacts/models/tabular_cefr_baseline_full_ladder_random_forest",
        "artifacts/models/tabular_cefr_baseline_full_ladder_logreg",
    ]

    def _tabular_dir_ready(path: str) -> bool:
        return (
            os.path.isdir(path)
            and os.path.isfile(os.path.join(path, "classifier_metadata.json"))
            and (
                os.path.isfile(os.path.join(path, "best_tabular_joint_profile.joblib"))
                or os.path.isfile(os.path.join(path, "best_tabular_cefr_baseline.joblib"))
            )
        )

    default_tabular_dir = next(
        (candidate for candidate in default_tabular_dirs if _tabular_dir_ready(candidate)),
        default_tabular_dirs[0],
    )
    preferred_tabular_dir = default_tabular_dir

    if provider_raw:
        provider = provider_raw
    else:
        default_model_dir = "artifacts/models/deberta_classifier_cefr"
        has_tabular = _tabular_dir_ready(default_tabular_dir)
        has_deberta = (
            os.path.isdir(default_model_dir)
            and os.path.isfile(os.path.join(default_model_dir, "classifier_metadata.json"))
        )
        provider = "tabular" if has_tabular else ("deberta" if has_deberta else "rule")
        if not model_path and provider == "deberta":
            model_path = default_model_dir
        if not model_path and provider == "tabular":
            model_path = default_tabular_dir

    if provider == "deberta" and not model_path:
        model_path = "artifacts/models/deberta_classifier_cefr"
    if provider == "tabular" and not model_path:
        model_path = preferred_tabular_dir

    if provider not in {"rule", "deberta", "tabular"}:
        raise ValueError("ELA_CLASSIFIER_PROVIDER must be one of: rule | deberta | tabular")

    return provider, (model_path or None)


SERVICE = RuntimeMediaService(
    db_path=os.getenv("ELA_CLIENT_DB_PATH", "artifacts/client_state.sqlite3"),
    runtime_mode=os.getenv("ELA_RUNTIME_MODE", "auto"),
    deployment_mode=os.getenv("ELA_DEPLOYMENT_MODE", "auto"),
)


def _build_sentence_contract_payload(sentence_text: str, sentence_idx: int) -> dict:
    controlled_model_dir = _env_str("ELA_CONTROLLED_T5_MODEL_DIR", "")
    classifier_provider, classifier_model_path = _resolve_classifier_settings()
    return SERVICE.build_sentence_contract(
        sentence_text=sentence_text,
        sentence_idx=sentence_idx,
        note_mode="controlled",
        model_dir=controlled_model_dir or None,
        validation_mode="v2_strict",
        enable_translation=True,
        translation_model="artifacts/models/m2m100_418M",
        translation_source_lang="en",
        translation_target_lang="ru",
        translation_device="cpu",
        enable_phonetic=True,
        phonetic_binary="auto",
        enable_synonyms=False,
        synonyms_top_k=5,
        enable_cefr=(classifier_provider == "rule"),
        cefr_provider="rule",
        cefr_model_path="artifacts/models/t5_cefr/best_model",
        classifier_provider=classifier_provider,
        classifier_model_path=classifier_model_path,
        classifier_device="cuda",
        enable_grammar_classes=True,
    )


def _run_sentence_contract_warmup() -> None:
    if not _env_bool("ELA_SENTENCE_CONTRACT_WARMUP", True):
        print("[runtime-api] sentence-contract warmup disabled", flush=True)
        return
    warmup_text = str(
        os.getenv(
            "ELA_SENTENCE_CONTRACT_WARMUP_TEXT",
            "She should have trusted her instincts before making the decision.",
        )
    ).strip()
    if not warmup_text:
        print("[runtime-api] sentence-contract warmup skipped: empty warmup text", flush=True)
        return
    print("[runtime-api] sentence-contract warmup started", flush=True)
    try:
        _build_sentence_contract_payload(warmup_text, 0)
        print("[runtime-api] sentence-contract warmup completed", flush=True)
    except Exception as exc:
        # Keep API boot alive even if warmup failed; requests will return runtime error details.
        print(f"[runtime-api] sentence-contract warmup failed: {exc}", flush=True)


def _run_media_pipeline_warmup() -> None:
    if not _env_bool("ELA_MEDIA_PIPELINE_WARMUP", True):
        print("[runtime-api] media warmup disabled", flush=True)
        return
    warmup_asr = _env_bool("ELA_MEDIA_WARMUP_ASR", True)
    warmup_translation = _env_bool("ELA_MEDIA_WARMUP_TRANSLATION", True)
    print(
        f"[runtime-api] media warmup started "
        f"(asr={str(warmup_asr).lower()}, translation={str(warmup_translation).lower()})",
        flush=True,
    )
    try:
        warmup_media_models(
            spacy_model="en_core_web_sm",
            warmup_asr=warmup_asr,
            warmup_translation=warmup_translation,
        )
        print("[runtime-api] media warmup completed", flush=True)
    except Exception as exc:
        print(f"[runtime-api] media warmup failed: {exc}", flush=True)


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
        if path == "/api/visualizer-payload":
            document_id = (query.get("document_id") or [""])[0]
            if not document_id:
                self._send_json({}, status=200)
                return
            self._send_json(SERVICE.get_visualizer_payload(document_id=document_id))
            return
        if path == "/api/backend-job-status":
            job_id = (query.get("job_id") or [""])[0]
            if not job_id:
                self._send_json({"error": "job_id is required"}, status=400)
                return
            self._send_json(SERVICE.get_backend_job_status(job_id=job_id))
            return
        if path == "/api/document-artifacts":
            document_id = (query.get("document_id") or [""])[0]
            if not document_id:
                self._send_json([], status=200)
                return
            self._send_json(SERVICE.list_document_artifacts(document_id=document_id))
            return
        if path == "/api/document-artifact-download":
            document_id = (query.get("document_id") or [""])[0]
            name = (query.get("name") or [""])[0]
            if not document_id or not name:
                self._send_json({"error": "document_id and name are required"}, status=400)
                return
            base = Path(os.getenv("MEDIA_CONTRACT_ARTIFACTS_DIR", "artifacts/media_contracts")).resolve()
            candidate = (base / document_id / name).resolve()
            if not str(candidate).startswith(str(base)) or not candidate.exists() or not candidate.is_file():
                self._send_json({"error": "Not found"}, status=404)
                return
            data = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'attachment; filename="{candidate.name}"')
            self.end_headers()
            self.wfile.write(data)
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
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
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
            self._send_json({"fileName": safe_name, "mediaPath": str(save_path), "sizeBytes": len(data)})
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
                    translation_provider=body.get("translationProvider"),
                    subtitles_mode=body.get("subtitlesMode"),
                    voice_choice=body.get("voiceChoice"),
                    force_full_reprocess=bool(body.get("forceFullReprocess")),
                    async_local_processing=True,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
            return
        if path == "/api/cancel-job":
            job_id = str(body.get("job_id") or body.get("jobId") or "").strip()
            if not job_id:
                self._send_json({"error": "job_id is required"}, status=400)
                return
            payload = SERVICE.cancel_backend_job(job_id=job_id)
            self._send_json(payload, status=200 if payload.get("status") == "ok" else 404)
            return
        if path == "/api/delete-analysis":
            document_id = str(body.get("document_id") or body.get("documentId") or "").strip()
            if not document_id:
                self._send_json({"error": "document_id is required"}, status=400)
                return
            payload = SERVICE.delete_analysis(document_id=document_id)
            self._send_json(payload, status=200 if payload.get("status") == "ok" else 404)
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
                payload = _build_sentence_contract_payload(sentence_text, sentence_idx)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(payload)
            return

        self._send_json({"error": "Not found"}, status=404)


def main() -> None:
    import threading

    host = os.getenv("ELA_RUNTIME_HTTP_HOST", "0.0.0.0")
    port = _env_int("ELA_RUNTIME_HTTP_PORT", 8000)
    server = ThreadingHTTPServer((host, port), RuntimeApiHandler)
    print(f"[runtime-api] serving on http://{host}:{port}", flush=True)

    # Run warmup in a background thread so the server starts accepting connections
    # immediately.  Without this, the 2-3 minute warmup window leaves the port
    # closed and Cloudflare / nginx return 502 "Bad Gateway" for any request that
    # arrives during that window.
    def _warmup():
        _run_sentence_contract_warmup()
        _run_media_pipeline_warmup()

    threading.Thread(target=_warmup, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
