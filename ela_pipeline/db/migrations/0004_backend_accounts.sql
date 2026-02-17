CREATE TABLE IF NOT EXISTS backend_accounts (
    id BIGSERIAL PRIMARY KEY,
    phone_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backend_accounts_phone_hash ON backend_accounts (phone_hash);
