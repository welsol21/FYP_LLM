"""PostgreSQL repository for inference contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable


class PostgresContractRepository:
    """Persist runs and sentence contracts into PostgreSQL."""

    def __init__(self, db_url: str, connect_fn: Callable[[str], Any] | None = None) -> None:
        resolved = (db_url or "").strip() or os.getenv("ELA_DATABASE_URL", "").strip() or os.getenv(
            "DATABASE_URL", ""
        ).strip()
        if not resolved:
            raise ValueError("PostgreSQL URL is required (pass db_url or set ELA_DATABASE_URL/DATABASE_URL).")
        self.db_url = resolved
        self._connect_fn = connect_fn

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self.db_url)
        try:
            import psycopg
        except Exception as exc:  # pragma: no cover - dependency/environment dependent
            raise ImportError("psycopg is required for PostgreSQL persistence") from exc
        return psycopg.connect(self.db_url)

    @staticmethod
    def default_schema_path() -> str:
        return str(Path(__file__).with_name("migrations").joinpath("0001_init.sql"))

    def ensure_schema(self, schema_sql_path: str | None = None) -> None:
        if schema_sql_path:
            paths = [Path(schema_sql_path)]
        else:
            paths = sorted(Path(__file__).with_name("migrations").glob("*.sql"))
        with self._connect() as conn:
            with conn.cursor() as cur:
                for path in paths:
                    sql = path.read_text(encoding="utf-8")
                    cur.execute(sql)
            conn.commit()

    def upsert_run(self, run_id: str, metadata: dict[str, Any]) -> None:
        payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        sql = """
        INSERT INTO runs (run_id, metadata)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (run_id)
        DO UPDATE SET metadata = EXCLUDED.metadata, updated_at = NOW()
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (run_id, payload))
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
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (sentence_key)
        DO UPDATE SET
            source_text = EXCLUDED.source_text,
            source_lang = EXCLUDED.source_lang,
            target_lang = EXCLUDED.target_lang,
            hash_version = EXCLUDED.hash_version,
            last_run_id = EXCLUDED.last_run_id,
            pipeline_context = EXCLUDED.pipeline_context,
            contract_payload = EXCLUDED.contract_payload,
            language_pair = EXCLUDED.language_pair,
            tam_construction = EXCLUDED.tam_construction,
            backoff_nodes_count = EXCLUDED.backoff_nodes_count,
            backoff_leaf_nodes_count = EXCLUDED.backoff_leaf_nodes_count,
            backoff_aggregate_nodes_count = EXCLUDED.backoff_aggregate_nodes_count,
            backoff_unique_spans_count = EXCLUDED.backoff_unique_spans_count,
            updated_at = NOW()
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
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
        WHERE sentence_key = %s
        LIMIT 1
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (sentence_key,))
                row = cur.fetchone()
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
        WHERE source_lang = %s AND target_lang = %s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (source_lang, target_lang))
                row = cur.fetchone()
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
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING id
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (sentence_key, reviewed_by, change_reason, confidence, payload))
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("Failed to create review event.")
        return int(row[0])

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
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
        RETURNING id
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (review_event_id, node_id, field_path, before_json, after_json))
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("Failed to create node edit.")
        return int(row[0])

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
        WHERE re.sentence_key = %s
        ORDER BY re.id ASC, ne.id ASC
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (sentence_key,))
                rows = cur.fetchall()
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
                    "before_value": row[8],
                    "after_value": row[9],
                    "created_at": str(row[10]),
                }
            )
        return result

    def export_feedback_rows(self, *, reviewed_by: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if reviewed_by:
            clauses.append("re.reviewed_by = %s")
            params.append(reviewed_by)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT %s"
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
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()

        exported: list[dict[str, Any]] = []
        for row in rows:
            exported.append(
                {
                    "sentence_key": row[0],
                    "reviewed_by": row[1],
                    "change_reason": row[2],
                    "confidence": row[3],
                    "review_metadata": row[4],
                    "node_id": row[5],
                    "field_path": row[6],
                    "before_value": row[7],
                    "after_value": row[8],
                    "edited_at": str(row[9]),
                }
            )
        return exported
