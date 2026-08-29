-- Telemetry log: every query handled by the service, one row per request.
-- This is both the audit trail and the future training data for the
-- learned router (Module 4).
CREATE TABLE IF NOT EXISTS query_log (
    id              BIGSERIAL PRIMARY KEY,
    query_text      TEXT NOT NULL,
    system          TEXT NOT NULL,             -- 'baseline' or 'adaptive'
    tier_used       TEXT NOT NULL,              -- 'small' | 'medium' | 'large' | 'baseline'
    cache_hit       BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms      DOUBLE PRECISION NOT NULL,
    estimated_cost  DOUBLE PRECISION NOT NULL,
    answer          TEXT NOT NULL,
    api_key_owner   TEXT,                       -- who made the request (Module 6)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_query_log_created_at ON query_log (created_at);
CREATE INDEX IF NOT EXISTS idx_query_log_tier_used ON query_log (tier_used);
CREATE INDEX IF NOT EXISTS idx_query_log_api_key_owner ON query_log (api_key_owner);

-- API keys (Module 6): who's allowed to call the service, and whose usage
-- a given request should be attributed to.
CREATE TABLE IF NOT EXISTS api_keys (
    key         TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
