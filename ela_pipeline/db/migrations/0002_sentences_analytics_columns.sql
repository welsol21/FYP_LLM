ALTER TABLE sentences
    ADD COLUMN IF NOT EXISTS language_pair TEXT,
    ADD COLUMN IF NOT EXISTS tam_construction TEXT,
    ADD COLUMN IF NOT EXISTS backoff_nodes_count INTEGER,
    ADD COLUMN IF NOT EXISTS backoff_leaf_nodes_count INTEGER,
    ADD COLUMN IF NOT EXISTS backoff_aggregate_nodes_count INTEGER,
    ADD COLUMN IF NOT EXISTS backoff_unique_spans_count INTEGER;

CREATE INDEX IF NOT EXISTS idx_sentences_language_pair ON sentences (language_pair);
CREATE INDEX IF NOT EXISTS idx_sentences_tam_construction ON sentences (tam_construction);
