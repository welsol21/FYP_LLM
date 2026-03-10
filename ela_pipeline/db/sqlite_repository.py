"""SQLite repository for inference contracts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _loads_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return default
    return default


class SQLiteContractRepository:
    """Persist runs and sentence contracts into SQLite."""

    def __init__(self, db_path: str) -> None:
        resolved = str(db_path or "").strip()
        if not resolved:
            raise ValueError("SQLite path is required.")
        self.db_path = resolved

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def ensure_schema(self, schema_sql_path: str | None = None) -> None:
        _ = schema_sql_path
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sentences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sentence_key TEXT NOT NULL UNIQUE,
                    source_text TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    hash_version TEXT NOT NULL,
                    last_run_id TEXT NOT NULL REFERENCES runs(run_id),
                    pipeline_context TEXT NOT NULL DEFAULT '{}',
                    contract_payload TEXT NOT NULL,
                    language_pair TEXT,
                    tam_construction TEXT,
                    backoff_nodes_count INTEGER,
                    backoff_leaf_nodes_count INTEGER,
                    backoff_aggregate_nodes_count INTEGER,
                    backoff_unique_spans_count INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_sentences_last_run_id ON sentences (last_run_id);
                CREATE INDEX IF NOT EXISTS idx_sentences_source_lang_target_lang ON sentences (source_lang, target_lang);
                CREATE INDEX IF NOT EXISTS idx_sentences_language_pair ON sentences (language_pair);
                CREATE INDEX IF NOT EXISTS idx_sentences_tam_construction ON sentences (tam_construction);

                CREATE TABLE IF NOT EXISTS review_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sentence_key TEXT NOT NULL REFERENCES sentences(sentence_key) ON DELETE CASCADE,
                    reviewed_by TEXT NOT NULL,
                    change_reason TEXT,
                    confidence REAL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_review_events_sentence_key ON review_events (sentence_key);
                CREATE INDEX IF NOT EXISTS idx_review_events_reviewed_by ON review_events (reviewed_by);

                CREATE TABLE IF NOT EXISTS node_edits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_event_id INTEGER NOT NULL REFERENCES review_events(id) ON DELETE CASCADE,
                    node_id TEXT NOT NULL,
                    field_path TEXT NOT NULL,
                    before_value TEXT,
                    after_value TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_node_edits_review_event_id ON node_edits (review_event_id);

                CREATE TABLE IF NOT EXISTS backend_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_backend_accounts_phone_hash ON backend_accounts (phone_hash);
                """
            )
            conn.commit()

    def upsert_run(self, run_id: str, metadata: dict[str, Any]) -> None:
        payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        sql = """
        INSERT INTO runs (run_id, metadata)
        VALUES (?, ?)
        ON CONFLICT(run_id)
        DO UPDATE SET metadata = excluded.metadata, updated_at = CURRENT_TIMESTAMP
        """
        with self._connect() as conn:
            conn.execute(sql, (run_id, payload))
            conn.commit()

    def upsert_sentence(
        self,
        *,
        sentence_key: str,
        source_text: str,
        source_lang: str,
        target_lang: str,
        hash_version: str,
        run_id: str,
        pipeline_context: dict[str, Any],
        contract_payload: dict[str, Any],
        analytics: dict[str, Any] | None = None,
    ) -> None:
        meta = analytics or {}
        ctx = json.dumps(pipeline_context, ensure_ascii=False, sort_keys=True)
        payload = json.dumps(contract_payload, ensure_ascii=False, sort_keys=True)
        sql = """
        INSERT INTO sentences (
            sentence_key, source_text, source_lang, target_lang, hash_version,
            last_run_id, pipeline_context, contract_payload,
            language_pair, tam_construction, backoff_nodes_count,
            backoff_leaf_nodes_count, backoff_aggregate_nodes_count, backoff_unique_spans_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sentence_key)
        DO UPDATE SET
            source_text = excluded.source_text,
            source_lang = excluded.source_lang,
            target_lang = excluded.target_lang,
            hash_version = excluded.hash_version,
            last_run_id = excluded.last_run_id,
            pipeline_context = excluded.pipeline_context,
            contract_payload = excluded.contract_payload,
            language_pair = excluded.language_pair,
            tam_construction = excluded.tam_construction,
            backoff_nodes_count = excluded.backoff_nodes_count,
            backoff_leaf_nodes_count = excluded.backoff_leaf_nodes_count,
            backoff_aggregate_nodes_count = excluded.backoff_aggregate_nodes_count,
            backoff_unique_spans_count = excluded.backoff_unique_spans_count,
            updated_at = CURRENT_TIMESTAMP
        """
        with self._connect() as conn:
            conn.execute(
                sql,
                (
                    sentence_key,
                    source_text,
                    source_lang,
                    target_lang,
                    hash_version,
                    run_id,
                    ctx,
                    payload,
                    f"{source_lang}->{target_lang}",
                    meta.get("tam_construction"),
                    meta.get("backoff_nodes_count"),
                    meta.get("backoff_leaf_nodes_count"),
                    meta.get("backoff_aggregate_nodes_count"),
                    meta.get("backoff_unique_spans_count"),
                ),
            )
            conn.commit()

    def get_sentence_by_key(self, sentence_key: str) -> dict[str, Any] | None:
        sql = """
        SELECT sentence_key, source_text, source_lang, target_lang, hash_version, last_run_id
        FROM sentences
        WHERE sentence_key = ?
        LIMIT 1
        """
        with self._connect() as conn:
            row = conn.execute(sql, (sentence_key,)).fetchone()
        if row is None:
            return None
        return {
            "sentence_key": row[0],
            "source_text": row[1],
            "source_lang": row[2],
            "target_lang": row[3],
            "hash_version": row[4],
            "last_run_id": row[5],
        }

    def count_sentences_by_language_pair(self, source_lang: str, target_lang: str) -> int:
        sql = """
        SELECT COUNT(*)
        FROM sentences
        WHERE source_lang = ? AND target_lang = ?
        """
        with self._connect() as conn:
            row = conn.execute(sql, (source_lang, target_lang)).fetchone()
        return int(row[0]) if row else 0

    def create_review_event(
        self,
        *,
        sentence_key: str,
        reviewed_by: str,
        change_reason: str | None = None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        payload = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        sql = """
        INSERT INTO review_events (sentence_key, reviewed_by, change_reason, confidence, metadata)
        VALUES (?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            cur = conn.execute(sql, (sentence_key, reviewed_by, change_reason, confidence, payload))
            conn.commit()
            review_id = int(cur.lastrowid or 0)
        if review_id <= 0:
            raise RuntimeError("Failed to create review event.")
        return review_id

    def add_node_edit(
        self,
        *,
        review_event_id: int,
        node_id: str,
        field_path: str,
        before_value: Any,
        after_value: Any,
    ) -> int:
        before_json = json.dumps(before_value, ensure_ascii=False, sort_keys=True)
        after_json = json.dumps(after_value, ensure_ascii=False, sort_keys=True)
        sql = """
        INSERT INTO node_edits (review_event_id, node_id, field_path, before_value, after_value)
        VALUES (?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            cur = conn.execute(sql, (review_event_id, node_id, field_path, before_json, after_json))
            conn.commit()
            edit_id = int(cur.lastrowid or 0)
        if edit_id <= 0:
            raise RuntimeError("Failed to create node edit.")
        return edit_id

    def list_node_edits(self, sentence_key: str) -> list[dict[str, Any]]:
        sql = """
        SELECT
            re.id AS review_event_id,
            re.sentence_key,
            re.reviewed_by,
            re.change_reason,
            re.confidence,
            ne.id AS node_edit_id,
            ne.node_id,
            ne.field_path,
            ne.before_value,
            ne.after_value,
            ne.created_at
        FROM review_events re
        JOIN node_edits ne ON ne.review_event_id = re.id
        WHERE re.sentence_key = ?
        ORDER BY re.id ASC, ne.id ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (sentence_key,)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "review_event_id": int(row[0]),
                    "sentence_key": row[1],
                    "reviewed_by": row[2],
                    "change_reason": row[3],
                    "confidence": row[4],
                    "node_edit_id": int(row[5]),
                    "node_id": row[6],
                    "field_path": row[7],
                    "before_value": _loads_json(row[8], row[8]),
                    "after_value": _loads_json(row[9], row[9]),
                    "created_at": str(row[10]),
                }
            )
        return result

    def export_feedback_rows(self, *, reviewed_by: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if reviewed_by:
            clauses.append("re.reviewed_by = ?")
            params.append(reviewed_by)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT ?"
            params.append(limit)

        sql = f"""
        SELECT
            re.sentence_key,
            re.reviewed_by,
            re.change_reason,
            re.confidence,
            re.metadata,
            ne.node_id,
            ne.field_path,
            ne.before_value,
            ne.after_value,
            ne.created_at
        FROM review_events re
        JOIN node_edits ne ON ne.review_event_id = re.id
        {where_sql}
        ORDER BY ne.id ASC
        {limit_sql}
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        exported: list[dict[str, Any]] = []
        for row in rows:
            exported.append(
                {
                    "sentence_key": row[0],
                    "reviewed_by": row[1],
                    "change_reason": row[2],
                    "confidence": row[3],
                    "review_metadata": _loads_json(row[4], {}),
                    "node_id": row[5],
                    "field_path": row[6],
                    "before_value": _loads_json(row[7], row[7]),
                    "after_value": _loads_json(row[8], row[8]),
                    "edited_at": str(row[9]),
                }
            )
        return exported

    def upsert_backend_account(self, *, phone_hash: str) -> int:
        sql = """
        INSERT INTO backend_accounts (phone_hash)
        VALUES (?)
        ON CONFLICT(phone_hash)
        DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        """
        with self._connect() as conn:
            conn.execute(sql, (phone_hash,))
            row = conn.execute("SELECT id FROM backend_accounts WHERE phone_hash = ? LIMIT 1", (phone_hash,)).fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("Failed to upsert backend account.")
        return int(row[0])

    def get_backend_account_by_phone_hash(self, *, phone_hash: str) -> dict[str, Any] | None:
        sql = """
        SELECT id, phone_hash, created_at, updated_at
        FROM backend_accounts
        WHERE phone_hash = ?
        LIMIT 1
        """
        with self._connect() as conn:
            row = conn.execute(sql, (phone_hash,)).fetchone()
        if row is None:
            return None
        return {
            "id": int(row[0]),
            "phone_hash": row[1],
            "created_at": str(row[2]),
            "updated_at": str(row[3]),
        }
