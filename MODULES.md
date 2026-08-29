# CostQual-Router — System Modules

Seven implementation modules take CostQual-Router from proof-of-concept prototype to a
production-grade, adaptive LLM-serving system. Each module is scoped to depend only on artifacts
produced by prior modules — no forward dependencies.

## Modules

| # | Module | Status | Objective | Key Techniques |
|---|---|---|---|---|
| 1 | **Infrastructure Setup** | ✅ Done | Stand up the core services everything else runs on | Local models via Ollama (small/medium/large), PostgreSQL + Qdrant in Docker, database schema for logging, demo script turned into a proper API |
| 2 | **Persistent Semantic Cache** | ✅ Done | Replace the temporary in-memory cache with one that survives restarts and scales | Move cache into Qdrant, similarity search stays cosine-based, each entry auto-expires 24h after it's created, periodic cleanup of expired entries |
| 3 | **Real Model Tiers & Data Collection** | ✅ Done | Get all three model tiers genuinely working and start logging real usage | Fix the tier setup (currently medium/large share one model), log every query + routing decision, keep the rule-based router as a fallback |
| 4 | **Learned Router** | Not started | Replace hand-written routing rules with a trained model | Extract features from queries, train a classifier (scikit-learn) on logged data, roll it out gradually alongside the old router before fully switching |
| 5 | **Quality & Monitoring** | Not started | Confirm cost savings aren't hurting answer quality, and catch issues early | BERTScore checks comparing smaller-model answers to the large model, alerts if query patterns shift a lot, live dashboards via Prometheus + Grafana |
| 6 | **Security & Automated Deployment** | Not started | Make the system production-safe and remove manual deployment steps | API-key login with per-user usage tracking, automated testing/deployment via GitHub Actions, load testing under real, unpredictable traffic |
| 7 | **Final Testing & Report** | Not started | Wrap up with thorough evaluation and documentation | Fix issues found during testing, compare adaptive system vs. baseline vs. original prototype, one-command Docker setup, final written report |

### Module 1 — what was actually built
- `docker-compose.yml` — Postgres 16 + Qdrant, both provisioned and health-checked
- `db/init.sql` — `query_log` table (query, system, tier, cache hit, latency, cost, timestamp)
- `db.py` — connection + `log_query()` / `is_healthy()` helpers
- `api.py` — FastAPI service: `POST /query` (runs the existing adaptive/baseline handlers, logs every request to Postgres) and `GET /health`
- Verified live: containers healthy, `/health` reports DB up, a cold query round-trips through Ollama and logs a row, a repeat query hits the in-memory cache (93s → 24ms) and logs that too
- 4 new tests in `tests/test_api.py`, full suite (16 tests) passing

### Module 2 — what was actually built
- `cache.py` rewritten: `SemanticCache` now backed by Qdrant (was an in-memory Python list), same public API (`check_cache` / `add_to_cache` / `clear_cache`) so no caller changed
- Per-entry 24h TTL (`created_at` payload field, freshness filter applied at lookup time) — not a scheduled global wipe
- `cache_reaper.py` — standalone script to purge expired entries for storage hygiene (run periodically; freshness is already enforced at lookup time regardless)
- `/health` now also reports Qdrant status
- Verified live: wrote a cache entry in one Python process, read it back correctly from a **separate, freshly-started process** — proves persistence, not just correctness
- 2 new tests in `tests/test_cache.py` (reconnect-persistence test, TTL-purge test), full suite (18 tests) passing

### Module 3 — what was actually built
- `config.py` — `MODEL_TIERS["large"]` now `mistral:7b-instruct-q4_0` (real model, pulled via Ollama), resolving the prototype's medium/large aliasing to the same model
- Routing decisions were already being logged to Postgres by Module 1's `query_log` table (query text, tier, cache hit, cost, latency) — this is the labeled dataset Module 4's classifier will train on
- Rule-based `router.py` kept unchanged as the active router / future fallback baseline
- `tests/test_config.py` — regression guard asserting all three tiers are genuinely distinct models
- `tests/test_handlers.py` — new end-to-end test confirming a reasoning query actually reaches and gets answered by the large-tier model
- Full test suite (20 tests) passing against the real 3-tier setup

---

## Technology Stack

| Layer | Component | Role |
|---|---|---|
| **Inference runtime** | Ollama | Serves three locally-hosted, open-source LLM tiers (small/medium/large) |
| **Embedding model** | Sentence-Transformers (`all-MiniLM-L6-v2`) | Maps query text to a dense semantic vector space |
| **Vector store** | Qdrant | ANN-indexed persistence layer for the semantic cache; sub-linear similarity search at scale |
| **Relational store** | PostgreSQL | Structured persistence for telemetry, credentials, and aggregate usage statistics |
| **Routing classifier** | Scikit-learn | Supervised model for complexity-based tier assignment (Module 4) |
| **Quality evaluation** | BERTScore | Continuous semantic-similarity scoring between routed and reference-tier outputs |
| **API layer** | FastAPI | Stateless service interface exposing the routing/caching pipeline |
| **Observability** | Prometheus + Grafana | Metrics collection and real-time dashboarding |
| **CI/CD** | GitHub Actions | Automated testing and gated deployment on commit |
| **Containerization** | Docker / Docker Compose | Reproducible, single-command service orchestration |

Every component in the stack is free, open-source, and self-hosted — no paid third-party API
dependency exists anywhere in the architecture, preserving full reproducibility.
