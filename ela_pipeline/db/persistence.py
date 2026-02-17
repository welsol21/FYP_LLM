"""Helpers to persist inference output into PostgreSQL."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from .keys import HASH_VERSION, build_sentence_key, canonicalize_text
from .repository import PostgresContractRepository


def persist_inference_result(
    *,
    result: dict[str, Any],
    db_url: str,
    source_lang: str,
    target_lang: str,
    pipeline_context: dict[str, Any],
    run_id: str | None = None,
    connect_fn=None,
) -> dict[str, str]:
    repo = PostgresContractRepository(db_url=db_url, connect_fn=connect_fn)
    repo.ensure_schema()

    rid = run_id or str(uuid.uuid4())
    run_meta = {
        "created_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "sentence_count": len(result),
        "pipeline_context": pipeline_context,
        "hash_version": HASH_VERSION,
    }
    repo.upsert_run(run_id=rid, metadata=run_meta)

    mapping: dict[str, str] = {}
    for sentence_text, sentence_node in result.items():
        if not isinstance(sentence_node, dict):
            continue
        key = build_sentence_key(
            sentence_text=sentence_text,
            source_lang=source_lang,
            target_lang=target_lang,
            pipeline_context=pipeline_context,
            hash_version=HASH_VERSION,
        )
        mapping[canonicalize_text(sentence_text)] = key
        repo.upsert_sentence(
            sentence_key=key,
            source_text=canonicalize_text(sentence_text),
            source_lang=source_lang,
            target_lang=target_lang,
            hash_version=HASH_VERSION,
            run_id=rid,
            pipeline_context=pipeline_context,
            contract_payload=sentence_node,
        )

    return mapping

