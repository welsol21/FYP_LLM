# DB Persistence (PostgreSQL)

Last updated: 2026-02-17

## Decision

- Primary storage: PostgreSQL.
- MongoDB is not used in current architecture.

## Sentence Identity

- `canonical_text` normalization:
  - Unicode NFC
  - trim
  - whitespace collapse to single spaces
- `hash_version`: `v1`
- `sentence_key` formula:
  - `sha256(hash_version | canonical_text | source_lang | target_lang | canonical_pipeline_context_json)`

## Current Schema (MVP+)

Migrations:
- `ela_pipeline/db/migrations/0001_init.sql`
- `ela_pipeline/db/migrations/0002_sentences_analytics_columns.sql`
- `ela_pipeline/db/migrations/0003_hil_review_tables.sql`

- `runs`
  - `run_id` (text, PK)
  - `metadata` (jsonb)
  - timestamps

- `sentences`
  - `sentence_key` (text, UNIQUE)
  - `source_text`, `source_lang`, `target_lang`
  - `language_pair` (`source_lang->target_lang`)
  - `hash_version`
  - `last_run_id` -> `runs.run_id`
  - `tam_construction`
  - `backoff_nodes_count`, `backoff_leaf_nodes_count`, `backoff_aggregate_nodes_count`, `backoff_unique_spans_count`
  - `pipeline_context` (jsonb)
  - `contract_payload` (jsonb)
  - timestamps

- `review_events` (Human-in-the-Loop)
  - `id` (bigserial, PK)
  - `sentence_key` -> `sentences.sentence_key`
  - `reviewed_by`, `change_reason`, `confidence`
  - `metadata` (jsonb)
  - `created_at`

- `node_edits` (Human-in-the-Loop)
  - `id` (bigserial, PK)
  - `review_event_id` -> `review_events.id`
  - `node_id`, `field_path`
  - `before_value` (jsonb), `after_value` (jsonb)
  - `created_at`

## Runtime Integration

Inference CLI supports optional DB persistence:

```bash
.venv/bin/python -m ela_pipeline.inference.run \
  --text "She should have trusted her instincts before making the decision." \
  --persist-db \
  --db-url "postgresql://user:pass@localhost:5432/ela"
```

Optional flags:
- `--db-run-id`
- `--db-source-lang`
- `--db-target-lang`

Schema migration command:

```bash
.venv/bin/python -m ela_pipeline.db.migrate --db-url "postgresql://user:pass@localhost:5432/ela"
```

In Docker Compose, default DSN is:
- `postgresql://ela_user:ela_pass@postgres:5432/ela`

## Next Steps

- Add migration management workflow and upgrade policy.
- Optional later: Redis cache for translation hot-path.

## Tests

Unit + integration DB tests:

```bash
docker compose exec -T app python -m unittest \
  tests/test_db_persistence.py \
  tests/test_db_keys.py \
  tests/test_db_integration_postgres.py
```

HIL tests (unit + integration):

```bash
docker compose exec -T app python -m unittest \
  tests/test_hil_repository.py \
  tests/test_hil_integration_postgres.py
```

HIL feedback export quality gates (current):
- allow only whitelisted editable `field_path` values
- validate `cefr_level` labels (`A1|A2|B1|B2|C1|C2`)
- deduplicate by (`sentence_key`, `node_id`, `field_path`, `after_value`)
