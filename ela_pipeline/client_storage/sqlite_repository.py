"""SQLite repository for client-local project/workspace persistence."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def build_sentence_hash(sentence_text: str, sentence_idx: int) -> str:
    """Stable sentence hash with index disambiguation for repeated text."""
    normalized = " ".join((sentence_text or "").strip().split()).lower()
    payload = f"{normalized}|{int(sentence_idx)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LocalSQLiteRepository:
    """Persist client-local state required by offline-first flows."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS media_files (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    duration_seconds INTEGER,
                    size_bytes INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_media_files_project_id ON media_files(project_id);

                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    media_file_id TEXT,
                    source_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    media_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    processing_duration_ms INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(media_file_id) REFERENCES media_files(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
                CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

                CREATE TABLE IF NOT EXISTS document_text (
                    document_id TEXT PRIMARY KEY,
                    full_text TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS media_sentences (
                    document_id TEXT NOT NULL,
                    sentence_idx INTEGER NOT NULL,
                    sentence_text TEXT NOT NULL,
                    text_ru TEXT,
                    start_ms INTEGER,
                    end_ms INTEGER,
                    page_no INTEGER,
                    char_start INTEGER,
                    char_end INTEGER,
                    sentence_hash TEXT NOT NULL,
                    PRIMARY KEY(document_id, sentence_idx),
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_media_sentences_document_hash ON media_sentences(document_id, sentence_hash);

                CREATE TABLE IF NOT EXISTS contract_sentences (
                    document_id TEXT NOT NULL,
                    sentence_hash TEXT NOT NULL,
                    sentence_node_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(document_id, sentence_hash),
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sentence_link (
                    document_id TEXT NOT NULL,
                    sentence_idx INTEGER NOT NULL,
                    sentence_hash TEXT NOT NULL,
                    PRIMARY KEY(document_id, sentence_idx),
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_sentence_link_document_hash ON sentence_link(document_id, sentence_hash);

                CREATE TABLE IF NOT EXISTS workspace_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS local_edits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sentence_key TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    field_path TEXT NOT NULL,
                    before_value TEXT,
                    after_value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_local_edits_sentence_key ON local_edits(sentence_key);

                CREATE TABLE IF NOT EXISTS backend_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    media_file_id TEXT,
                    status TEXT NOT NULL,
                    request_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_backend_jobs_status ON backend_jobs(status);

                CREATE TABLE IF NOT EXISTS sync_requests (
                    id TEXT PRIMARY KEY,
                    request_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sync_requests_status ON sync_requests(status);
                """
            )
            cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
            if "processing_duration_ms" not in cols:
                conn.execute("ALTER TABLE documents ADD COLUMN processing_duration_ms INTEGER")
            media_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(media_sentences)").fetchall()}
            if "text_ru" not in media_cols:
                conn.execute("ALTER TABLE media_sentences ADD COLUMN text_ru TEXT")
            conn.commit()
        # Keep DB consistent for legacy states: one media row per (project_id, path).
        self.cleanup_duplicate_media_files()

    def cleanup_duplicate_media_files(self) -> int:
        """Remove legacy duplicate media rows and keep the newest row per (project_id, path)."""
        deleted = 0
        with self._connect() as conn:
            dup_groups = conn.execute(
                """
                SELECT project_id, path
                FROM media_files
                GROUP BY project_id, path
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            for project_id, path in dup_groups:
                rows = conn.execute(
                    """
                    SELECT id
                    FROM media_files
                    WHERE project_id = ? AND path = ?
                    ORDER BY updated_at DESC, created_at DESC, id DESC
                    """,
                    (project_id, path),
                ).fetchall()
                if len(rows) <= 1:
                    continue
                keep_id = str(rows[0][0])
                drop_ids = [str(row[0]) for row in rows[1:]]
                for drop_id in drop_ids:
                    conn.execute(
                        "UPDATE documents SET media_file_id = ? WHERE media_file_id = ?",
                        (keep_id, drop_id),
                    )
                    conn.execute(
                        "UPDATE backend_jobs SET media_file_id = ? WHERE media_file_id = ?",
                        (keep_id, drop_id),
                    )
                    conn.execute("DELETE FROM media_files WHERE id = ?", (drop_id,))
                    deleted += 1
            conn.commit()
        return deleted

    def create_document(
        self,
        *,
        project_id: str,
        source_type: str,
        source_path: str,
        media_hash: str,
        media_file_id: str | None = None,
        status: str = "processing",
        document_id: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        doc_id = document_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    id, project_id, media_file_id, source_type, source_path, media_hash, status, processing_duration_ms, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, project_id, media_file_id, source_type, source_path, media_hash, status, None, now, now),
            )
            conn.commit()
        return {
            "id": doc_id,
            "project_id": project_id,
            "media_file_id": media_file_id,
            "source_type": source_type,
            "source_path": source_path,
            "media_hash": media_hash,
            "status": status,
            "processing_duration_ms": None,
            "created_at": now,
            "updated_at": now,
        }

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, media_file_id, source_type, source_path, media_hash, status, processing_duration_ms, created_at, updated_at
                FROM documents
                WHERE id = ?
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "project_id": row[1],
            "media_file_id": row[2],
            "source_type": row[3],
            "source_path": row[4],
            "media_hash": row[5],
            "status": row[6],
            "processing_duration_ms": row[7],
            "created_at": row[8],
            "updated_at": row[9],
        }

    def update_document_status(self, document_id: str, status: str, processing_duration_ms: int | None = None) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE documents
                SET status = ?, processing_duration_ms = COALESCE(?, processing_duration_ms), updated_at = ?
                WHERE id = ?
                """,
                (status, processing_duration_ms, now, document_id),
            )
            conn.commit()

    def upsert_document_text(
        self,
        *,
        document_id: str,
        full_text: str,
        text_hash: str,
        version: int = 1,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO document_text (document_id, full_text, text_hash, version, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(document_id)
                DO UPDATE SET
                    full_text = excluded.full_text,
                    text_hash = excluded.text_hash,
                    version = excluded.version,
                    updated_at = excluded.updated_at
                """,
                (document_id, full_text, text_hash, int(version), now),
            )
            conn.commit()

    def replace_media_sentences(self, *, document_id: str, sentences: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM media_sentences WHERE document_id = ?", (document_id,))
            for row in sentences:
                conn.execute(
                    """
                    INSERT INTO media_sentences (
                        document_id, sentence_idx, sentence_text, text_ru, start_ms, end_ms, page_no,
                        char_start, char_end, sentence_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        int(row["sentence_idx"]),
                        str(row["sentence_text"]),
                        str(row.get("text_ru") or ""),
                        row.get("start_ms"),
                        row.get("end_ms"),
                        row.get("page_no"),
                        row.get("char_start"),
                        row.get("char_end"),
                        str(row["sentence_hash"]),
                    ),
                )
            conn.commit()

    def upsert_contract_sentence(self, *, document_id: str, sentence_hash: str, sentence_node: dict[str, Any]) -> None:
        now = _utc_now()
        payload = json.dumps(sentence_node, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO contract_sentences (document_id, sentence_hash, sentence_node_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id, sentence_hash)
                DO UPDATE SET
                    sentence_node_json = excluded.sentence_node_json,
                    updated_at = excluded.updated_at
                """,
                (document_id, sentence_hash, payload, now),
            )
            conn.commit()

    def replace_sentence_links(self, *, document_id: str, links: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sentence_link WHERE document_id = ?", (document_id,))
            for row in links:
                conn.execute(
                    """
                    INSERT INTO sentence_link (document_id, sentence_idx, sentence_hash)
                    VALUES (?, ?, ?)
                    """,
                    (document_id, int(row["sentence_idx"]), str(row["sentence_hash"])),
                )
            conn.commit()

    def list_document_visualizer_rows(self, *, document_id: str) -> list[dict[str, Any]]:
        sql = """
            SELECT
                m.sentence_idx,
                m.sentence_text,
                m.sentence_hash,
                m.text_ru,
                c.sentence_node_json
            FROM media_sentences m
            JOIN sentence_link l
              ON l.document_id = m.document_id AND l.sentence_idx = m.sentence_idx
            JOIN contract_sentences c
              ON c.document_id = m.document_id AND c.sentence_hash = l.sentence_hash
            WHERE m.document_id = ?
            ORDER BY m.sentence_idx ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (document_id,)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "sentence_idx": int(row[0]),
                    "sentence_text": row[1],
                    "sentence_hash": row[2],
                    "text_ru": row[3],
                    "sentence_node": json.loads(row[4]),
                }
            )
        return out

    def get_document_processing_status(self, *, document_id: str) -> dict[str, Any] | None:
        sql = """
            SELECT
                d.id,
                d.status,
                d.source_type,
                d.source_path,
                d.media_file_id,
                d.updated_at,
                d.processing_duration_ms,
                (
                    SELECT COUNT(1)
                    FROM media_sentences ms
                    WHERE ms.document_id = d.id
                ) AS media_sentences_count,
                (
                    SELECT COUNT(1)
                    FROM contract_sentences cs
                    WHERE cs.document_id = d.id
                ) AS contract_sentences_count,
                (
                    SELECT COUNT(1)
                    FROM sentence_link sl
                    WHERE sl.document_id = d.id
                ) AS linked_sentences_count,
                (
                    SELECT dt.version
                    FROM document_text dt
                    WHERE dt.document_id = d.id
                    LIMIT 1
                ) AS text_version,
                (
                    SELECT LENGTH(dt.full_text)
                    FROM document_text dt
                    WHERE dt.document_id = d.id
                    LIMIT 1
                ) AS text_length
            FROM documents d
            WHERE d.id = ?
            LIMIT 1
        """
        with self._connect() as conn:
            row = conn.execute(sql, (document_id,)).fetchone()
            if row is None:
                return None

            media_file_id = row[4]
            job_row = None
            if media_file_id:
                job_row = conn.execute(
                    """
                    SELECT id, status, updated_at
                    FROM backend_jobs
                    WHERE media_file_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (media_file_id,),
                ).fetchone()

        return {
            "document_id": row[0],
            "status": row[1],
            "source_type": row[2],
            "source_path": row[3],
            "media_file_id": media_file_id,
            "updated_at": row[5],
            "processing_duration_ms": int(row[6] or 0),
            "media_sentences_count": int(row[7] or 0),
            "contract_sentences_count": int(row[8] or 0),
            "linked_sentences_count": int(row[9] or 0),
            "text_present": row[11] is not None and int(row[11]) > 0,
            "text_length": int(row[11] or 0),
            "text_version": int(row[10] or 0),
            "latest_backend_job": (
                {
                    "job_id": job_row[0],
                    "status": job_row[1],
                    "updated_at": job_row[2],
                }
                if job_row is not None
                else None
            ),
        }

    def create_project(self, name: str, project_id: str | None = None) -> dict[str, Any]:
        now = _utc_now()
        pid = project_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (pid, name, now, now),
            )
            conn.commit()
        return {"id": pid, "name": name, "created_at": now, "updated_at": now}

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, created_at, updated_at
                FROM projects
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [
            {"id": row[0], "name": row[1], "created_at": row[2], "updated_at": row[3]}
            for row in rows
        ]

    def create_media_file(
        self,
        *,
        project_id: str,
        name: str,
        path: str,
        duration_seconds: int | None = None,
        size_bytes: int | None = None,
        media_file_id: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id, created_at
                FROM media_files
                WHERE project_id = ? AND path = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (project_id, path),
            ).fetchone()
            if existing is not None:
                existing_id = str(existing[0])
                created_at = str(existing[1])
                conn.execute(
                    """
                    UPDATE media_files
                    SET name = ?, duration_seconds = ?, size_bytes = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, duration_seconds, size_bytes, now, existing_id),
                )
                conn.commit()
                return {
                    "id": existing_id,
                    "project_id": project_id,
                    "name": name,
                    "path": path,
                    "duration_seconds": duration_seconds,
                    "size_bytes": size_bytes,
                    "created_at": created_at,
                    "updated_at": now,
                }

        fid = media_file_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO media_files (
                    id, project_id, name, path, duration_seconds, size_bytes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (fid, project_id, name, path, duration_seconds, size_bytes, now, now),
            )
            conn.commit()
        return {
            "id": fid,
            "project_id": project_id,
            "name": name,
            "path": path,
            "duration_seconds": duration_seconds,
            "size_bytes": size_bytes,
            "created_at": now,
            "updated_at": now,
        }

    def list_media_files(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, name, path, duration_seconds, size_bytes, created_at, updated_at
                FROM media_files
                WHERE project_id = ?
                ORDER BY updated_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "project_id": row[1],
                "name": row[2],
                "path": row[3],
                "duration_seconds": row[4],
                "size_bytes": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def get_media_file(self, media_file_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, name, path, duration_seconds, size_bytes, created_at, updated_at
                FROM media_files
                WHERE id = ?
                LIMIT 1
                """,
                (media_file_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "project_id": row[1],
            "name": row[2],
            "path": row[3],
            "duration_seconds": row[4],
            "size_bytes": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }

    def delete_media_file(self, media_file_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM media_files WHERE id = ?", (media_file_id,))
            conn.commit()
        return int(cur.rowcount or 0) > 0

    def list_media_files_with_analysis(self, project_id: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where_sql = ""
        if project_id:
            where_sql = "WHERE mf.project_id = ?"
            params.append(project_id)
        sql = f"""
            SELECT
                mf.id,
                mf.project_id,
                mf.name,
                mf.path,
                mf.duration_seconds,
                mf.size_bytes,
                mf.created_at,
                mf.updated_at,
                d.id AS document_id
            FROM media_files mf
            LEFT JOIN documents d
              ON d.id = (
                  SELECT d2.id
                  FROM documents d2
                  WHERE d2.media_file_id = mf.id
                    AND d2.status = 'completed'
                  ORDER BY d2.updated_at DESC, d2.id DESC
                  LIMIT 1
              )
            {where_sql}
            ORDER BY mf.updated_at DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": row[0],
                    "project_id": row[1],
                    "name": row[2],
                    "path": row[3],
                    "duration_seconds": row[4],
                    "size_bytes": row[5],
                    "created_at": row[6],
                    "updated_at": row[7],
                    "analyzed": row[8] is not None,
                    "document_id": row[8],
                }
            )
        return out

    def list_analysis_history(self, project_id: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where_sql = "WHERE d.status = 'completed'"
        if project_id:
            where_sql += " AND d.project_id = ?"
            params.append(project_id)
        sql = f"""
            SELECT
                d.id,
                d.project_id,
                p.name,
                d.media_file_id,
                mf.name,
                COALESCE(mf.path, d.source_path),
                mf.duration_seconds,
                mf.size_bytes,
                d.source_path,
                d.created_at,
                d.updated_at
            FROM documents d
            LEFT JOIN projects p ON p.id = d.project_id
            LEFT JOIN media_files mf ON mf.id = d.media_file_id
            {where_sql}
            ORDER BY d.updated_at DESC, d.id DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "document_id": row[0],
                    "project_id": row[1],
                    "project_name": row[2],
                    "media_file_id": row[3],
                    "file_name": row[4],
                    "file_path": row[5],
                    "duration_seconds": row[6],
                    "size_bytes": row[7],
                    "source_path": row[8],
                    "created_at": row[9],
                    "updated_at": row[10],
                }
            )
        return out

    def set_workspace_state(self, state_key: str, state_value: dict[str, Any]) -> None:
        now = _utc_now()
        payload = json.dumps(state_value, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workspace_state (state_key, state_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key)
                DO UPDATE SET state_value = excluded.state_value, updated_at = excluded.updated_at
                """,
                (state_key, payload, now),
            )
            conn.commit()

    def get_workspace_state(self, state_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT state_value
                FROM workspace_state
                WHERE state_key = ?
                LIMIT 1
                """,
                (state_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def delete_workspace_state(self, state_key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM workspace_state WHERE state_key = ?", (state_key,))
            conn.commit()
        return int(cur.rowcount or 0) > 0

    def delete_document(self, document_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            conn.commit()
        return int(cur.rowcount or 0) > 0

    def add_local_edit(
        self,
        *,
        sentence_key: str,
        node_id: str,
        field_path: str,
        before_value: Any,
        after_value: Any,
    ) -> int:
        now = _utc_now()
        before_json = json.dumps(before_value, ensure_ascii=False, sort_keys=True)
        after_json = json.dumps(after_value, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO local_edits (sentence_key, node_id, field_path, before_value, after_value, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sentence_key, node_id, field_path, before_json, after_json, now),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_local_edits(self, *, sentence_key: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where_sql = ""
        if sentence_key:
            where_sql = "WHERE sentence_key = ?"
            params.append(sentence_key)
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT ?"
            params.append(limit)

        sql = f"""
            SELECT id, sentence_key, node_id, field_path, before_value, after_value, created_at
            FROM local_edits
            {where_sql}
            ORDER BY id DESC
            {limit_sql}
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": int(row[0]),
                    "sentence_key": row[1],
                    "node_id": row[2],
                    "field_path": row[3],
                    "before_value": json.loads(row[4]) if row[4] is not None else None,
                    "after_value": json.loads(row[5]),
                    "created_at": row[6],
                }
            )
        return out

    def enqueue_backend_job(
        self,
        *,
        request_payload: dict[str, Any],
        project_id: str | None = None,
        media_file_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        jid = job_id or str(uuid.uuid4())
        payload = json.dumps(request_payload, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO backend_jobs (
                    id, project_id, media_file_id, status, request_payload, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (jid, project_id, media_file_id, "queued", payload, now, now),
            )
            conn.commit()
        return {
            "id": jid,
            "project_id": project_id,
            "media_file_id": media_file_id,
            "status": "queued",
            "request_payload": request_payload,
            "created_at": now,
            "updated_at": now,
        }

    def update_backend_job_status(self, job_id: str, status: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE backend_jobs
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, now, job_id),
            )
            conn.commit()

    def list_backend_jobs(self, *, status: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where_sql = ""
        if status:
            where_sql = "WHERE status = ?"
            params.append(status)
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT ?"
            params.append(limit)
        sql = f"""
            SELECT id, project_id, media_file_id, status, request_payload, created_at, updated_at
            FROM backend_jobs
            {where_sql}
            ORDER BY created_at DESC
            {limit_sql}
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": row[0],
                    "project_id": row[1],
                    "media_file_id": row[2],
                    "status": row[3],
                    "request_payload": json.loads(row[4]),
                    "created_at": row[5],
                    "updated_at": row[6],
                }
            )
        return out

    def get_backend_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, media_file_id, status, request_payload, created_at, updated_at
                FROM backend_jobs
                WHERE id = ?
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "project_id": row[1],
            "media_file_id": row[2],
            "status": row[3],
            "request_payload": json.loads(row[4]),
            "created_at": row[5],
            "updated_at": row[6],
        }

    def retry_backend_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.get_backend_job(job_id)
        if row is None:
            return None
        if row["status"] not in {"failed", "error", "canceled"}:
            return row
        self.update_backend_job_status(job_id, "queued")
        return self.get_backend_job(job_id)

    def list_resumable_backend_jobs(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT ?"
            params.append(limit)
        sql = f"""
            SELECT id, project_id, media_file_id, status, request_payload, created_at, updated_at
            FROM backend_jobs
            WHERE status IN ('queued', 'processing')
            ORDER BY updated_at DESC
            {limit_sql}
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": row[0],
                    "project_id": row[1],
                    "media_file_id": row[2],
                    "status": row[3],
                    "request_payload": json.loads(row[4]),
                    "created_at": row[5],
                    "updated_at": row[6],
                }
            )
        return out

    def enqueue_sync_request(
        self,
        *,
        request_type: str,
        payload: dict[str, Any],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        rid = request_id or str(uuid.uuid4())
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_requests (id, request_type, status, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rid, request_type, "queued", encoded, now, now),
            )
            conn.commit()
        return {
            "id": rid,
            "request_type": request_type,
            "status": "queued",
            "payload": payload,
            "created_at": now,
            "updated_at": now,
        }

    def update_sync_request_status(self, request_id: str, status: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sync_requests
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, now, request_id),
            )
            conn.commit()

    def list_sync_requests(self, *, status: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where_sql = ""
        if status:
            where_sql = "WHERE status = ?"
            params.append(status)
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT ?"
            params.append(limit)
        sql = f"""
            SELECT id, request_type, status, payload, created_at, updated_at
            FROM sync_requests
            {where_sql}
            ORDER BY created_at DESC
            {limit_sql}
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": row[0],
                    "request_type": row[1],
                    "status": row[2],
                    "payload": json.loads(row[3]),
                    "created_at": row[4],
                    "updated_at": row[5],
                }
            )
        return out
