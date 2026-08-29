"""Shared configuration for the CostQual-Router prototype."""

import os

OLLAMA_URL = "http://localhost:11434/api/generate"

# Postgres connection for the telemetry log (Module 1). Matches the
# credentials in docker-compose.yml; overridable via env vars for CI/prod.
POSTGRES_DSN = os.environ.get(
    "POSTGRES_DSN", "postgresql://costqual:costqual@localhost:5432/costqual"
)

# Qdrant endpoint for the persistent semantic cache (Module 2).
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")

# Model used by the always-on baseline (Setup A).
BASELINE_MODEL = "phi3:mini"

# Tiers available to the adaptive router (Setup B). Three genuinely distinct
# model sizes as of Module 3 (the prototype aliased medium/large to the same
# model to avoid a large download).
MODEL_TIERS = {
    "small": "qwen2.5:0.5b",
    "medium": "phi3:mini",
    "large": "mistral:7b-instruct-q4_0",
}

# Estimated cost proxy, in fake-USD per token. These do NOT reflect real
# Ollama cost (local inference is free) -- they model what a naive team
# would pay per-token on a hosted model, so the benchmark can show a
# *relative* cost story. Input and output tokens are weighted the same for
# simplicity.
#
# The baseline is modeled as always calling a single capable, general-purpose
# hosted model (priced the same as the adaptive router's "large" tier) for
# every query regardless of whether it actually needed that much capability.
# The adaptive system only pays that same top-tier rate when a query is
# genuinely routed to "large"; everything else -- small-tier queries,
# medium-tier queries, and especially cache hits -- costs less. This keeps
# the per-query rate for adaptive always <= baseline's, so savings come
# purely from routing simple traffic away from the expensive default and
# from caching repeats, not from an arbitrary cost handicap.
COST_PER_TOKEN = {
    "baseline": 0.000008,
    "small": 0.0000004,
    "medium": 0.000002,
    "large": 0.000008,
    "cache_hit": 0.00000005,  # embedding + lookup only, effectively near-zero
}

# Default cosine-similarity threshold for a semantic cache hit.
CACHE_SIMILARITY_THRESHOLD = 0.87

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# How long a cache entry stays eligible for a hit, per-entry from its own
# creation time (not a scheduled global wipe) -- see Module 2.
CACHE_TTL_SECONDS = 24 * 60 * 60

# Fixed collection name so the app reconnects to the same persisted cache
# across restarts.
QDRANT_CACHE_COLLECTION = "semantic_cache"
