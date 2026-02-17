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

## Current Schema (MVP)

Migration: `ela_pipeline/db/migrations/0001_init.sql`

- `runs`
  - `run_id` (text, PK)
  - `metadata` (jsonb)
  - timestamps

- `sentences`
  - `sentence_key` (text, UNIQUE)
  - `source_text`, `source_lang`, `target_lang`
  - `hash_version`
  - `last_run_id` -> `runs.run_id`
  - `pipeline_context` (jsonb)
  - `contract_payload` (jsonb)
  - timestamps

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

## Next Steps

- Add explicit `UNIQUE`/query index policy documentation for analytics fields.
- Add migration management workflow and upgrade policy.
- Add repository read/query methods for analytics/reporting.

