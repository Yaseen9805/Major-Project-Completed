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
| 4 | **Learned Router** | ✅ Done | Replace hand-written routing rules with a trained model | Extract features from queries, train a classifier (scikit-learn) on logged data, roll it out gradually alongside the old router before fully switching |
| 5 | **Quality & Monitoring** | ✅ Done | Confirm cost savings aren't hurting answer quality, and catch issues early | BERTScore checks comparing smaller-model answers to the large model, alerts if query patterns shift a lot, live dashboards via Prometheus + Grafana |
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

### Module 4 — what was actually built
- `seed_traffic.py` — replays `test_queries.json` through the **live API** (not a side channel) to produce genuine logged routing decisions, matching Module 3's "real usage" logging
- `train_router.py` — pulls (query, tier) pairs from `query_log` where `cache_hit=false`, trains a TF-IDF + Logistic Regression classifier (`scikit-learn`), reports held-out accuracy, then refits on the full dataset and saves `router_model.joblib`
- `learned_router.py` — same `route(query)` interface as `router.py`, backed by the trained model; falls back to the rule-based router if no model file is on disk yet (never hard-fails)
- `config.py` — new `ROUTER_MODE` flag (`"rule_based"` default / `"learned"`); `adaptive.py` picks the router based on it, enabling an A/B rollout instead of a hard cutover
- **Honest result, not hidden:** on the 46 real routing decisions collected so far, held-out accuracy is **58%** (weak on the "large" class, 0% recall on only 3 held-out examples) — expected with a dataset this small. `ROUTER_MODE` defaults to `rule_based` precisely because of this, so the weak model is available for testing but not live. Accuracy is expected to improve as more real traffic accumulates and `train_router.py` is rerun.
- Verified live: `ROUTER_MODE=learned` end-to-end call correctly routes and answers through the trained model
- 4 new tests (`test_learned_router.py` + a router-mode-switch test in `test_handlers.py`), full suite (24 tests) passing

### Module 5 — what was actually built
- `quality_monitor.py` — replaces `quality_check.py`'s LLM-as-judge spot check with real BERTScore F1 comparing adaptive answers against baseline. Verified live: **81% pass rate, average F1 0.873** across 36 scored answers
- `drift_monitor.py` — chi-squared test comparing the recent vs. reference tier-distribution of real routing decisions from `query_log`; flags when traffic looks statistically different from what the router was built around. Verified live (currently reports no drift, as expected on one seeding batch)
- `api.py` — instrumented with `prometheus-client` (`costqual_queries_total`, `costqual_query_latency_ms`, `costqual_estimated_cost_total`), new `GET /metrics` endpoint
- `docker-compose.yml` — added Prometheus + Grafana services; `monitoring/prometheus.yml` scrapes the host API via `host.docker.internal`; Grafana auto-provisions the Prometheus datasource and a "CostQual-Router" dashboard (cache hit rate, total cost, query volume by tier, p95 latency by tier)
- Verified live end-to-end: a real query round-tripped through the API → showed up correctly labeled in `/metrics` → Prometheus scraped it (target `up`) → Grafana's provisioned dashboard and datasource both confirmed via its API
- Full test suite (24 tests) still passing after instrumentation; `quality_monitor.py`/`drift_monitor.py` verified via live runs rather than unit tests, consistent with the project's existing convention of not unit-testing standalone report scripts (e.g. `quality_check.py`, `generate_report.py`)

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
