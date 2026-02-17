CREATE TABLE IF NOT EXISTS review_events (
    id BIGSERIAL PRIMARY KEY,
    sentence_key TEXT NOT NULL REFERENCES sentences(sentence_key) ON DELETE CASCADE,
    reviewed_by TEXT NOT NULL,
    change_reason TEXT,
    confidence DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_events_sentence_key ON review_events (sentence_key);
CREATE INDEX IF NOT EXISTS idx_review_events_reviewed_by ON review_events (reviewed_by);

CREATE TABLE IF NOT EXISTS node_edits (
    id BIGSERIAL PRIMARY KEY,
    review_event_id BIGINT NOT NULL REFERENCES review_events(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    field_path TEXT NOT NULL,
    before_value JSONB,
    after_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_node_edits_review_event_id ON node_edits (review_event_id);
