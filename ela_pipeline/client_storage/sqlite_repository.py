"""SQLite repository for client-local project/workspace persistence."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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
                """
            )

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
