CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sentences (
    id BIGSERIAL PRIMARY KEY,
    sentence_key TEXT NOT NULL UNIQUE,
    source_text TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    hash_version TEXT NOT NULL,
    last_run_id TEXT NOT NULL REFERENCES runs(run_id),
    pipeline_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    contract_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sentences_last_run_id ON sentences (last_run_id);
CREATE INDEX IF NOT EXISTS idx_sentences_source_lang_target_lang ON sentences (source_lang, target_lang);

