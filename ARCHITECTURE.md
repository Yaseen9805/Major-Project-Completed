# Project Architecture — File by File

This doc explains what every file in this repo does, in plain language, so anyone new to the
project can get oriented in a few minutes. For results and how to run it, see `README.md`. For the
module-by-module build history, see `MODULES.md`. For the original 5-day prototype spec this system
grew out of, see `prototype_plan.md`.

## The big picture

We're comparing two ways of answering questions with locally-hosted LLMs:

- **Setup A (baseline)** — dumb and simple. Every question goes to the same model. No memory,
  no shortcuts.
- **Setup B (adaptive)** — smarter. It first checks "have I basically answered this before?" (the
  persistent cache), and if not, it picks the cheapest of three genuinely distinct model tiers that
  can actually handle the question (the router — rule-based by default, or a trained classifier
  behind a flag).

Everything else in the repo exists to run both systems, serve Setup B as a real API, and prove with
numbers that it's cheaper and just as accurate.

## Core serving logic

| File | What it does |
|---|---|
| `config.py` | Every setting in one place: model tiers, fake-cost-per-token assumptions, cache threshold/TTL, DB/Qdrant/Ollama connection URLs (env-overridable), the `ROUTER_MODE` flag. |
| `ollama_client.py` | The only place that talks to Ollama over HTTP. Retries on timeout. |
| `baseline.py` | Setup A. `ask_baseline(query)` — always calls the same fixed model. |
| `router.py` | Rule-based complexity classifier. Pure regex/keyword rules, no ML — e.g. "starts with 'what is' and is short" → small; "contains 'explain' or 'compare'" → large. |
| `learned_router.py` | A trained classifier (see `train_router.py`) with the same interface as `router.py`. Not active by default — `ROUTER_MODE` in `config.py` controls which one `adaptive.py` uses, so it can be A/B'd before a full cutover. |
| `cache.py` | The semantic cache. Turns each question into an embedding vector and checks Qdrant for a similar-meaning question asked before. Persistent across restarts; each entry expires 24h after its own creation time (not a scheduled global wipe). |
| `adaptive.py` | Setup B. `ask_adaptive(query)`: check cache → if miss, route to a tier and call the model → save the answer to the cache. |

## Service layer

| File | What it does |
|---|---|
| `api.py` | FastAPI service exposing the whole system over HTTP: `POST /query` (API-key gated, logs every request to Postgres, updates Prometheus metrics), `GET /health`, `GET /metrics`. |
| `db.py` | Postgres access: request logging (`query_log`), API-key management (`api_keys`). |
| `db/init.sql` | Schema for `query_log` and `api_keys`. |
| `manage_keys.py` | CLI to issue new API keys: `python manage_keys.py create <name>`. |

## Learned router training

| File | What it does |
|---|---|
| `seed_traffic.py` | Replays `test_queries.json` through the **live API** to produce genuine logged routing decisions — bootstraps real training data. |
| `train_router.py` | Trains a TF-IDF + Logistic Regression classifier on logged (query, tier) pairs from Postgres, reports held-out accuracy, saves `router_model.joblib`. |

## Quality & drift monitoring

| File | What it does |
|---|---|
| `quality_check.py` | Lightweight LLM-as-judge spot check: samples 10 cases where the router used a smaller model and got a different answer, asks the baseline model to judge if it's still acceptable. |
| `quality_monitor.py` | BERTScore-based evaluation — scores *every* case where routing selected a smaller model against the baseline's answer, by semantic similarity, not exact wording or an extra LLM call. |
| `drift_monitor.py` | Chi-squared test comparing the recent vs. reference tier-distribution of real routing decisions, to flag when traffic looks statistically different from what the router was built around. |
| `cache_reaper.py` | Standalone cleanup job that purges cache entries past their TTL, for storage hygiene (freshness is already enforced at lookup time regardless). |

## Test data & experiment runner

| File | What it does |
|---|---|
| `test_queries.json` | The fixed set of 60 questions used for benchmarking: exact repeats, paraphrases, easy questions, hard questions, and one-off unique questions. |
| `run_benchmark.py` | Runs all 60 questions through Setup A, then Setup B (cold cache), and logs every result to `benchmark_results.csv`. |
| `load_test.py` | Fires concurrent, randomly-ordered requests at the live API to validate throughput/stability under real, unpredictable traffic — unlike `run_benchmark.py`'s fixed sequential pass. |

## Reporting & demo

| File | What it does |
|---|---|
| `generate_report.py` | Reads `benchmark_results.csv`, computes latency/cost/cache-hit/tier-distribution stats, and writes `report.md` plus two chart images. |
| `demo.py` | Interactive CLI: type a question, see both systems answer it side by side with timing/cost/cache-hit info. |

## Infrastructure

| File | What it does |
|---|---|
| `Dockerfile` | Builds the API service image. |
| `docker-compose.yml` | The full stack: PostgreSQL, Qdrant, Ollama (+ a one-shot `ollama-pull` job), the API, Prometheus, Grafana. `docker compose up -d` starts everything. |
| `.dockerignore` | Keeps `venv/`, generated artifacts, and docs out of the built image. |
| `monitoring/prometheus.yml` | Scrape config pointing at the API's `/metrics` endpoint. |
| `monitoring/grafana/` | Auto-provisioned Prometheus datasource + the "CostQual-Router" dashboard (cache hit rate, cost, query volume by tier, p95 latency by tier). |
| `.github/workflows/ci.yml` | Runs the test suite on every push against real Postgres/Qdrant service containers and freshly-pulled small/medium Ollama models. |
| `pytest.ini` | Registers the `requires_large_model` marker used to skip the large-tier test in CI. |

## Generated output (not hand-written — overwritten each run)

| File | What it is |
|---|---|
| `benchmark_results.csv` | Raw log: every question, which system answered it, latency, cache-hit, tier, estimated cost, and the answer text. |
| `quality_check_results.csv` | The LLM-judge sample with PASS/FAIL verdicts. |
| `quality_monitor_results.csv` | The BERTScore evaluation results. |
| `report.md` | Human-readable summary: tables + a plain-English interpretation. |
| `cost_comparison.png`, `latency_comparison.png` | The two bar charts referenced in `report.md`. |
| `router_model.joblib` | The trained learned-router classifier. |

## Tests

| File | What it does |
|---|---|
| `tests/test_router.py` | Rule-based router classifies example questions correctly. |
| `tests/test_config.py` | Regression guard: all three model tiers must be genuinely distinct models. |
| `tests/test_cache.py` | Cache hits/misses, persistence across a reconnect, TTL purge, and a regression test for a real concurrency race found by load testing. |
| `tests/test_learned_router.py` | The trained classifier loads, returns valid tiers, and falls back to the rule-based router if no model file exists. |
| `tests/test_handlers.py` | `ask_baseline`/`ask_adaptive` shapes, cache-hit-on-repeat, the large tier is genuinely reachable, and the `ROUTER_MODE` flag actually switches routers. |
| `tests/test_api.py` | The live API: health, auth (missing/invalid/valid key), validation, cache hits, and usage attribution. |
| `conftest.py` | Housekeeping so pytest can find the project's modules when run from the `tests/` folder. |

## Everything else

| File | What it does |
|---|---|
| `requirements.txt` | Python dependencies (`pip install -r requirements.txt`). |
| `README.md` | What this is, how to run it, and the final results. |
| `TECHNICAL_DEEP_DIVE.md` | Every technology, every file, every algorithm, and every design decision explained in depth — read this to understand the project at the level of someone who built it. |
| `MODULES.md` | The 7-module build history — what each module added and what was verified. |
| `FINAL_REPORT.md` | The final written comparison: baseline vs. adaptive vs. original prototype. |
| `ABSTRACT.md` | The formal project summary. |
| `prototype_plan.md` | The original spec the 5-day prototype was built from. |
| `.gitignore` | Ignores the virtual environment and Python cache folders. |

## How a single question flows through Setup B (adaptive), end to end

1. A client sends `POST /query` with an `X-API-Key` header (`api.py`).
2. The key is checked against Postgres (`db.get_api_key_owner`); invalid/missing → 401.
3. `adaptive.py` asks `cache.py`: "have I seen something like this before?" (a Qdrant similarity
   search, filtered to entries still inside their 24h TTL).
   - **Hit** → return the saved answer immediately. Near-zero cost, near-zero latency.
   - **Miss** → continue.
4. `adaptive.py` asks the active router (`router.py` or `learned_router.py`, per `ROUTER_MODE`):
   "how hard is this question?" → `small`/`medium`/`large`.
5. `adaptive.py` calls that tier's model via `ollama_client.py`.
6. The new question + answer is written back into the cache.
7. The request is logged to Postgres (`query_log`) and recorded in Prometheus metrics.
8. The answer, tier used, cache-hit status, latency, and cost are returned to the client.

Setup A (`baseline.py`) skips all of that and just calls one fixed model every time.
