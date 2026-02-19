"""Frontend-ready runtime service: capabilities, media submit, backend queue access."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import uuid
from typing import Any

from ela_pipeline.client_storage import LocalSQLiteRepository, build_sentence_hash

from .capabilities import build_runtime_capabilities, resolve_deployment_mode, resolve_runtime_mode
from .media_policy import MediaPolicyLimits, load_media_policy_limits_from_env
from .media_pipeline import build_sentence_contract, run_media_pipeline
from .media_submission import submit_media_for_processing
from .ui_state import build_runtime_ui_state, build_submission_ui_feedback


@dataclass
class RuntimeMediaService:
    """Single integration point for UI/desktop layer."""

    db_path: str | Path
    runtime_mode: str = "auto"
    deployment_mode: str = "auto"
    limits: MediaPolicyLimits | None = None
    demo_auto_progress_jobs: bool = False

    def __post_init__(self) -> None:
        self.repo = LocalSQLiteRepository(self.db_path)
        self.effective_mode = resolve_runtime_mode(self.runtime_mode)
        self.effective_deployment_mode = resolve_deployment_mode(self.deployment_mode)
        self.caps = build_runtime_capabilities(self.effective_mode, deployment_mode=self.effective_deployment_mode)
        self.limits = self.limits or load_media_policy_limits_from_env()
        self.media_enrichment_backend_only = os.getenv("ELA_MEDIA_ENRICHMENT_BACKEND_ONLY", "1").strip() not in {
            "0",
            "false",
            "False",
        }

    def get_ui_state(self) -> dict[str, Any]:
        return build_runtime_ui_state(self.caps)

    def list_projects(self) -> list[dict[str, Any]]:
        return self.repo.list_projects()

    def create_project(self, *, name: str) -> dict[str, Any]:
        created = self.repo.create_project(name=name)
        self.set_selected_project(project_id=created["id"])
        return created

    def get_selected_project(self) -> dict[str, Any]:
        state = self.repo.get_workspace_state("selected_project")
        if not state:
            return {"project_id": None}
        project_id = state.get("project_id")
        if not project_id:
            return {"project_id": None}
        row = next((p for p in self.repo.list_projects() if p["id"] == project_id), None)
        if row is None:
            return {"project_id": None}
        return {"project_id": row["id"], "project_name": row["name"]}

    def set_selected_project(self, *, project_id: str) -> dict[str, Any]:
        row = next((p for p in self.repo.list_projects() if p["id"] == project_id), None)
        if row is None:
            return {"project_id": None}
        self.repo.set_workspace_state("selected_project", {"project_id": project_id})
        return {"project_id": row["id"], "project_name": row["name"]}

    def register_media_file(
        self,
        *,
        project_id: str,
        name: str,
        media_path: str,
        size_bytes: int,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        row = next((p for p in self.repo.list_projects() if p["id"] == project_id), None)
        if row is None:
            return {"error": "project_not_found"}
        return self.repo.create_media_file(
            project_id=project_id,
            name=name,
            path=media_path,
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
        )

    def submit_media(
        self,
        *,
        media_path: str,
        duration_seconds: int,
        size_bytes: int,
        project_id: str | None = None,
        media_file_id: str | None = None,
    ) -> dict[str, Any]:
        selected = self.get_selected_project()
        effective_project_id = project_id or selected.get("project_id")
        if not effective_project_id:
            raw = {
                "route": "reject",
                "status": "rejected",
                "message": "Create/select project first.",
                "job_id": None,
            }
            return {
                "result": raw,
                "ui_feedback": build_submission_ui_feedback(raw),
            }
        if not any(p["id"] == effective_project_id for p in self.repo.list_projects()):
            raw = {
                "route": "reject",
                "status": "rejected",
                "message": f"Project '{effective_project_id}' not found.",
                "job_id": None,
            }
            return {
                "result": raw,
                "ui_feedback": build_submission_ui_feedback(raw),
            }

        if media_file_id is None:
            media_file_id = f"file-{uuid.uuid4().hex[:12]}"
            self.repo.create_media_file(
                project_id=effective_project_id,
                media_file_id=media_file_id,
                name=Path(media_path).name or media_path,
                path=media_path,
                duration_seconds=duration_seconds,
                size_bytes=size_bytes,
            )

        raw = submit_media_for_processing(
            repo=self.repo,
            media_path=media_path,
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
            runtime_caps=self.caps,
            limits=self.limits,
            project_id=effective_project_id,
            media_file_id=media_file_id,
            prefer_backend_for_enrichment=self.media_enrichment_backend_only,
        )
        if raw.get("route") == "local":
            synced = self.process_media_now(
                media_path=media_path,
                project_id=effective_project_id,
                media_file_id=media_file_id,
            )
            raw["document_id"] = synced.get("document_id")
            raw["status"] = "completed_local" if synced.get("status") == "completed" else raw.get("status")
            if synced.get("status") != "completed":
                raw["route"] = "reject"
                raw["status"] = "rejected"
                raw["message"] = str(synced.get("message") or "Local media processing failed.")
        return {
            "result": raw,
            "ui_feedback": build_submission_ui_feedback(raw),
        }

    def list_backend_jobs(self, *, status: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        return self.repo.list_backend_jobs(status=status, limit=limit)

    def get_backend_job_status(self, *, job_id: str) -> dict[str, Any]:
        row = self.repo.get_backend_job(job_id)
        if row is None:
            return {"job_id": job_id, "status": "not_found"}
        if self.demo_auto_progress_jobs:
            # Demo worker emulation: progress queued->processing->completed on status checks.
            if row["status"] == "queued":
                self.repo.update_backend_job_status(job_id, "processing")
                row = self.repo.get_backend_job(job_id) or row
            elif row["status"] == "processing":
                self.repo.update_backend_job_status(job_id, "completed")
                row = self.repo.get_backend_job(job_id) or row
        return {
            "job_id": row["id"],
            "status": row["status"],
            "updated_at": row["updated_at"],
            "project_id": row["project_id"],
            "media_file_id": row["media_file_id"],
        }

    def retry_backend_job(self, *, job_id: str) -> dict[str, Any]:
        current = self.repo.get_backend_job(job_id)
        if current is None:
            return {"job_id": job_id, "status": "not_found", "message": "Job not found."}
        if current["status"] not in {"failed", "error", "canceled"}:
            return {
                "job_id": job_id,
                "status": current["status"],
                "message": f"Job is not retryable from status '{current['status']}'.",
            }
        retried = self.repo.retry_backend_job(job_id)
        assert retried is not None
        return {
            "job_id": job_id,
            "status": retried["status"],
            "message": "Job moved to queued.",
        }

    def resume_backend_jobs(self, *, limit: int | None = None) -> dict[str, Any]:
        rows = self.repo.list_resumable_backend_jobs(limit=limit)
        return {
            "resumed_count": len(rows),
            "jobs": [
                {
                    "job_id": row["id"],
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                    "project_id": row["project_id"],
                    "media_file_id": row["media_file_id"],
                }
                for row in rows
            ],
        }

    def list_document_sentences(self, *, document_id: str) -> list[dict[str, Any]]:
        rows = self.repo.list_document_visualizer_rows(document_id=document_id)
        return [
            {
                "sentence_idx": row["sentence_idx"],
                "sentence_text": row["sentence_text"],
                "sentence_hash": row["sentence_hash"],
            }
            for row in rows
        ]

    def get_visualizer_payload(self, *, document_id: str) -> dict[str, Any]:
        rows = self.repo.list_document_visualizer_rows(document_id=document_id)
        payload: dict[str, Any] = {}
        duplicates: dict[str, int] = {}
        for row in rows:
            base = (row.get("sentence_text") or "").strip() or f"sentence_{row['sentence_idx']}"
            seen = duplicates.get(base, 0)
            duplicates[base] = seen + 1
            key = base if seen == 0 else f"{base} #{seen + 1}"
            payload[key] = row["sentence_node"]
        return payload

    def get_document_processing_status(self, *, document_id: str) -> dict[str, Any]:
        status = self.repo.get_document_processing_status(document_id=document_id)
        if status is None:
            return {
                "document_id": document_id,
                "status": "not_found",
                "media_sentences_count": 0,
                "contract_sentences_count": 0,
                "linked_sentences_count": 0,
                "text_present": False,
                "text_length": 0,
                "text_version": 0,
                "latest_backend_job": None,
            }
        return status

    def list_files(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.repo.list_media_files_with_analysis(project_id=project_id)
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "path": row.get("path"),
                    "size_bytes": row.get("size_bytes"),
                    "duration_seconds": row.get("duration_seconds"),
                    "settings": "HF / Runtime",
                    "updated": row["updated_at"],
                    "analyzed": bool(row["analyzed"]),
                    "document_id": row.get("document_id"),
                }
            )
        return out

    def build_sentence_contract(
        self,
        *,
        sentence_text: str,
        sentence_idx: int = 0,
    ) -> dict[str, Any]:
        return build_sentence_contract(
            sentence_text=sentence_text,
            sentence_idx=sentence_idx,
        )

    def sync_backend_result(self, *, job_id: str, result: dict[str, Any]) -> dict[str, Any]:
        job = self.repo.get_backend_job(job_id)
        if job is None:
            return {"job_id": job_id, "status": "not_found", "message": "Job not found."}

        document_meta = (result.get("document") or {}) if isinstance(result, dict) else {}
        document_id = (
            result.get("document_id")
            or document_meta.get("id")
            or f"doc-{job_id}"
        )
        project_id = document_meta.get("project_id") or job.get("project_id")
        media_file_id = document_meta.get("media_file_id") or job.get("media_file_id")
        source_path = document_meta.get("source_path") or job.get("request_payload", {}).get("media_path") or ""
        source_type = document_meta.get("source_type") or self._infer_source_type(source_path)
        media_hash = document_meta.get("media_hash") or f"job:{job_id}"

        existing_doc = self.repo.get_document(document_id)
        if existing_doc is None:
            if not project_id:
                return {
                    "job_id": job_id,
                    "status": "error",
                    "message": "Cannot create document without project_id.",
                }
            self.repo.create_document(
                document_id=document_id,
                project_id=project_id,
                media_file_id=media_file_id,
                source_type=source_type,
                source_path=source_path,
                media_hash=media_hash,
                status="processing",
            )

        media_sentences = self._normalize_media_sentences(result.get("media_sentences") or [])
        if not media_sentences:
            return {
                "job_id": job_id,
                "status": "error",
                "message": "Backend result has no media_sentences.",
            }

        full_text = (
            result.get("full_text")
            or document_meta.get("full_text")
            or " ".join(row["sentence_text"] for row in media_sentences).strip()
        )
        text_hash = document_meta.get("text_hash") or hashlib.sha256(full_text.encode("utf-8")).hexdigest()
        text_version = int(document_meta.get("text_version") or result.get("text_version") or 1)
        self.repo.upsert_document_text(
            document_id=document_id,
            full_text=full_text,
            text_hash=text_hash,
            version=text_version,
        )
        self.repo.replace_media_sentences(document_id=document_id, sentences=media_sentences)

        contract_rows = self._normalize_contract_sentences(
            raw=result.get("contract_sentences"),
            media_sentences=media_sentences,
        )
        for row in contract_rows:
            self.repo.upsert_contract_sentence(
                document_id=document_id,
                sentence_hash=row["sentence_hash"],
                sentence_node=row["sentence_node"],
            )

        links = self._normalize_sentence_links(
            raw=result.get("sentence_links"),
            media_sentences=media_sentences,
        )
        self.repo.replace_sentence_links(document_id=document_id, links=links)
        self.repo.update_document_status(document_id, "completed")
        self.repo.update_backend_job_status(job_id, "completed")

        return {
            "job_id": job_id,
            "status": "completed",
            "document_id": document_id,
            "media_sentences_count": len(media_sentences),
            "contract_sentences_count": len(contract_rows),
            "linked_sentences_count": len(links),
            "message": "Backend result synced to local document tables.",
        }

    def sync_backend_result_auto(self, *, job_id: str) -> dict[str, Any]:
        job = self.repo.get_backend_job(job_id)
        if job is None:
            return {"job_id": job_id, "status": "not_found", "message": "Job not found."}
        if job["status"] != "completed":
            return {"job_id": job_id, "status": job["status"], "message": "Job is not completed yet."}
        media_path = str(job.get("request_payload", {}).get("media_path") or "")
        if not media_path:
            return {"job_id": job_id, "status": "error", "message": "Missing media path in backend job payload."}
        return self.process_media_now(
            media_path=media_path,
            project_id=job.get("project_id") or "proj-default",
            media_file_id=job.get("media_file_id"),
            job_id=job_id,
        )

    def process_media_now(
        self,
        *,
        media_path: str,
        project_id: str,
        media_file_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            pipeline = run_media_pipeline(source_path=media_path)
        except Exception as exc:
            if job_id:
                self.repo.update_backend_job_status(job_id, "failed")
            return {
                "job_id": job_id,
                "status": "error",
                "message": str(exc),
            }

        document_id = f"doc-{job_id}" if job_id else f"doc-{uuid.uuid4().hex[:12]}"
        result = {
            "document": {
                "id": document_id,
                "project_id": project_id,
                "media_file_id": media_file_id,
                "source_type": pipeline.source_type,
                "source_path": media_path,
                "media_hash": f"job:{job_id}" if job_id else f"local:{media_file_id or 'media'}",
                "full_text": pipeline.full_text,
                "text_hash": pipeline.text_hash,
                "text_version": 1,
            },
            "media_sentences": pipeline.media_sentences,
            "contract_sentences": pipeline.contract_sentences,
        }
        if job_id:
            return self.sync_backend_result(job_id=job_id, result=result)

        existing_doc = self.repo.get_document(document_id)
        if existing_doc is None:
            self.repo.create_document(
                document_id=document_id,
                project_id=project_id,
                media_file_id=media_file_id,
                source_type=pipeline.source_type,
                source_path=media_path,
                media_hash=f"local:{media_file_id or 'media'}",
                status="processing",
            )
        self.repo.upsert_document_text(
            document_id=document_id,
            full_text=pipeline.full_text,
            text_hash=pipeline.text_hash,
            version=1,
        )
        self.repo.replace_media_sentences(document_id=document_id, sentences=pipeline.media_sentences)
        for row in pipeline.contract_sentences:
            self.repo.upsert_contract_sentence(
                document_id=document_id,
                sentence_hash=row["sentence_hash"],
                sentence_node=row["sentence_node"],
            )
        self.repo.replace_sentence_links(
            document_id=document_id,
            links=[
                {"sentence_idx": row["sentence_idx"], "sentence_hash": row["sentence_hash"]}
                for row in pipeline.media_sentences
            ],
        )
        self.repo.update_document_status(document_id, "completed")
        return {
            "job_id": None,
            "status": "completed",
            "document_id": document_id,
            "media_sentences_count": len(pipeline.media_sentences),
            "contract_sentences_count": len(pipeline.contract_sentences),
            "linked_sentences_count": len(pipeline.media_sentences),
            "message": "Local media processed and synced.",
        }

    def apply_document_edit(
        self,
        *,
        document_id: str,
        sentence_text: str,
        node_id: str,
        field_path: str,
        new_value: Any,
    ) -> dict[str, Any]:
        rows = self.repo.list_document_visualizer_rows(document_id=document_id)
        keyed: dict[str, dict[str, Any]] = {}
        duplicates: dict[str, int] = {}
        for row in rows:
            base = (row.get("sentence_text") or "").strip() or f"sentence_{row['sentence_idx']}"
            seen = duplicates.get(base, 0)
            duplicates[base] = seen + 1
            key = base if seen == 0 else f"{base} #{seen + 1}"
            keyed[key] = row
        target = keyed.get(sentence_text)
        if target is None:
            return {"status": "error", "message": "Sentence not found."}
        root = target["sentence_node"]
        node = self._find_node_by_id(root, node_id)
        if node is None:
            return {"status": "error", "message": "node_id not found."}
        if not self._set_by_path(node, field_path, new_value):
            return {"status": "error", "message": f"Invalid field path: {field_path}"}
        self.repo.upsert_contract_sentence(
            document_id=document_id,
            sentence_hash=target["sentence_hash"],
            sentence_node=root,
        )
        return {"status": "ok", "message": "Edit applied."}

    @staticmethod
    def _infer_source_type(source_path: str) -> str:
        suffix = Path(source_path or "").suffix.lower()
        if suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}:
            return "audio"
        if suffix in {".mp4", ".mkv", ".mov", ".avi", ".webm"}:
            return "video"
        if suffix in {".pdf"}:
            return "pdf"
        return "text"

    @staticmethod
    def _normalize_media_sentences(raw_sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for idx, row in enumerate(raw_sentences):
            sentence_idx = int(row.get("sentence_idx", idx))
            sentence_text = str(
                row.get("sentence_text")
                or row.get("text")
                or row.get("text_eng")
                or ""
            ).strip()
            if not sentence_text:
                continue
            sentence_hash = str(row.get("sentence_hash") or build_sentence_hash(sentence_text, sentence_idx))
            normalized.append(
                {
                    "sentence_idx": sentence_idx,
                    "sentence_text": sentence_text,
                    "start_ms": row.get("start_ms"),
                    "end_ms": row.get("end_ms"),
                    "page_no": row.get("page_no"),
                    "char_start": row.get("char_start"),
                    "char_end": row.get("char_end"),
                    "sentence_hash": sentence_hash,
                }
            )
        normalized.sort(key=lambda r: r["sentence_idx"])
        return normalized

    @staticmethod
    def _normalize_contract_sentences(
        *,
        raw: Any,
        media_sentences: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_idx = {row["sentence_idx"]: row["sentence_hash"] for row in media_sentences}
        by_text_occurrence: dict[str, list[str]] = {}
        for row in media_sentences:
            key = row["sentence_text"].strip().lower()
            by_text_occurrence.setdefault(key, []).append(row["sentence_hash"])
        use_index: dict[str, int] = {}

        rows: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for idx, item in enumerate(raw):
                if not isinstance(item, dict):
                    continue
                node = item.get("sentence_node") or item.get("node")
                if not isinstance(node, dict):
                    continue
                sentence_hash = item.get("sentence_hash")
                if not sentence_hash:
                    sentence_idx = item.get("sentence_idx")
                    if sentence_idx is not None and int(sentence_idx) in by_idx:
                        sentence_hash = by_idx[int(sentence_idx)]
                if not sentence_hash:
                    content = str(node.get("content") or "").strip().lower()
                    hashes = by_text_occurrence.get(content, [])
                    pos = use_index.get(content, 0)
                    if pos < len(hashes):
                        sentence_hash = hashes[pos]
                        use_index[content] = pos + 1
                if not sentence_hash:
                    sentence_hash = build_sentence_hash(str(node.get("content") or f"sentence_{idx}"), idx)
                rows.append({"sentence_hash": str(sentence_hash), "sentence_node": node})
        elif isinstance(raw, dict):
            for idx, (sentence_text, node) in enumerate(raw.items()):
                if not isinstance(node, dict):
                    continue
                key = str(sentence_text).strip().lower()
                hashes = by_text_occurrence.get(key, [])
                pos = use_index.get(key, 0)
                if pos < len(hashes):
                    sentence_hash = hashes[pos]
                    use_index[key] = pos + 1
                else:
                    sentence_hash = build_sentence_hash(str(sentence_text), idx)
                rows.append({"sentence_hash": str(sentence_hash), "sentence_node": node})

        if not rows:
            for row in media_sentences:
                rows.append(
                    {
                        "sentence_hash": row["sentence_hash"],
                        "sentence_node": {
                            "type": "Sentence",
                            "node_id": row["sentence_hash"][:12],
                            "content": row["sentence_text"],
                            "linguistic_elements": [],
                        },
                    }
                )
        return rows

    @staticmethod
    def _normalize_sentence_links(*, raw: Any, media_sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            links: list[dict[str, Any]] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                if "sentence_idx" not in item or "sentence_hash" not in item:
                    continue
                links.append({"sentence_idx": int(item["sentence_idx"]), "sentence_hash": str(item["sentence_hash"])})
            if links:
                links.sort(key=lambda r: r["sentence_idx"])
                return links
        return [
            {"sentence_idx": row["sentence_idx"], "sentence_hash": row["sentence_hash"]}
            for row in media_sentences
        ]

    @staticmethod
    def _find_node_by_id(root: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        stack = [root]
        while stack:
            node = stack.pop()
            if str(node.get("node_id")) == str(node_id):
                return node
            children = node.get("linguistic_elements")
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        stack.append(child)
        return None

    @staticmethod
    def _set_by_path(root: dict[str, Any], path: str, value: Any) -> bool:
        tokens: list[Any] = []
        buf = ""
        i = 0
        while i < len(path):
            ch = path[i]
            if ch == ".":
                if buf:
                    tokens.append(buf)
                    buf = ""
                i += 1
                continue
            if ch == "[":
                if buf:
                    tokens.append(buf)
                    buf = ""
                j = path.find("]", i + 1)
                if j == -1:
                    return False
                idx_txt = path[i + 1 : j]
                if not idx_txt.isdigit():
                    return False
                tokens.append(int(idx_txt))
                i = j + 1
                continue
            buf += ch
            i += 1
        if buf:
            tokens.append(buf)
        if not tokens:
            return False

        cur: Any = root
        for pos, token in enumerate(tokens[:-1]):
            nxt = tokens[pos + 1]
            if isinstance(token, int):
                if not isinstance(cur, list):
                    return False
                while len(cur) <= token:
                    cur.append({} if not isinstance(nxt, int) else [])
                if cur[token] is None:
                    cur[token] = {} if not isinstance(nxt, int) else []
                cur = cur[token]
            else:
                if not isinstance(cur, dict):
                    return False
                if token not in cur or cur[token] is None:
                    cur[token] = {} if not isinstance(nxt, int) else []
                cur = cur[token]

        last = tokens[-1]
        if isinstance(last, int):
            if not isinstance(cur, list):
                return False
            while len(cur) <= last:
                cur.append(None)
            cur[last] = value
            return True
        if not isinstance(cur, dict):
            return False
        cur[last] = value
        return True
