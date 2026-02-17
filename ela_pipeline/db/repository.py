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
        path = schema_sql_path or self.default_schema_path()
        sql = Path(path).read_text(encoding="utf-8")
        with self._connect() as conn:
            with conn.cursor() as cur:
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
    ) -> None:
        ctx = json.dumps(pipeline_context, ensure_ascii=False, sort_keys=True)
        payload = json.dumps(contract_payload, ensure_ascii=False, sort_keys=True)
        sql = """
        INSERT INTO sentences (
            sentence_key, source_text, source_lang, target_lang, hash_version,
            last_run_id, pipeline_context, contract_payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (sentence_key)
        DO UPDATE SET
            source_text = EXCLUDED.source_text,
            source_lang = EXCLUDED.source_lang,
            target_lang = EXCLUDED.target_lang,
            hash_version = EXCLUDED.hash_version,
            last_run_id = EXCLUDED.last_run_id,
            pipeline_context = EXCLUDED.pipeline_context,
            contract_payload = EXCLUDED.contract_payload,
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
                    ),
                )
            conn.commit()

