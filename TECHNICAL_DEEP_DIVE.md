# CostQual-Router — Technical Deep-Dive

This document exists so you can explain, defend, and extend this project as if you wrote every
line yourself — because you should understand every line, even though an AI assistant wrote the
first draft of each one. It covers: what each piece does, **how** it's implemented, **why** it
exists, what breaks if you remove it, every technology used and why it was chosen over the
alternatives, and an honest account of what's strong and what's weak — including for a research
paper.

Read it top to bottom once, then use it as a reference.

---

## Part 1 — The mental model

Forget the code for a second. The whole project is one idea, applied twice:

> **Don't do expensive work you don't have to.**

Applied to *repeated* questions → **semantic caching** (don't recompute an answer you already have).
Applied to *easy* questions → **complexity routing** (don't use an expensive model for a question a
cheap one can answer just as well).

Everything else in the repo — the database, the auth, the monitoring, the tests, the CI — exists to
make those two ideas trustworthy enough to run as a real service instead of a script you run once
and eyeball.

Two systems are built side by side so the idea can be *measured*, not just asserted:

- **Setup A / "baseline"** — the naive thing everyone does by default: one fixed model, every
  query, no memory. This is the thing we're claiming to beat.
- **Setup B / "adaptive"** — cache-first, routed-second. This is the actual product.

Every benchmark, chart, and report in this repo is baseline vs. adaptive on the *same* 60 questions,
because a claim like "58% cheaper" is meaningless without something concrete it's cheaper *than*.

---

## Part 2 — The problem and the idea, precisely

**The problem:** Large Language Models are expensive per call, and that cost is fixed by which
model answers, not by how hard the question was. A naive system routes "what's 2+2" and "write me
a business plan" to the exact same model, at the exact same cost. Separately, if two users ask
almost the same question minutes apart, most systems recompute the answer from scratch both times —
paying the model cost twice for information it already produced once.

**The idea, as two questions asked before every reply:**

1. *"Have I basically answered this before?"* — checked via **semantic similarity**, not exact text
   matching, so "What's the capital of Japan?" and "Which city is Japan's capital?" are recognized
   as the same question even though the words differ.
2. *"How hard is this question, really?"* — a lightweight classification (rule-based, or learned)
   that picks the cheapest model tier capable of answering it well.

Nothing here is a novel algorithm — semantic caching and model routing both exist in the literature
(see `ABSTRACT.md`'s citations context and `FINAL_REPORT.md`'s comparison). The contribution is
**building the combination as a real, running, measured system**, not the individual techniques.

---

## Part 3 — Technology stack: what each piece is and why it's here

### Ollama — the model server
**What it is:** a program that runs LLMs locally and exposes them over a simple HTTP API
(`POST /api/generate`), the same shape whether the model is 0.5B or 7B parameters.
**Why it's here:** it's what makes the whole "no paid API" claim true. Every model call in this
project (`ollama_client.py`) goes to `http://localhost:11434` (or the `ollama` container in
Docker), never to OpenAI/Anthropic/etc.
**Why Ollama and not, say, vLLM or raw Hugging Face `transformers`:** Ollama trades some inference
speed for enormous simplicity — one command (`ollama pull`) gets you a running model with no GPU
driver wrangling, no manual quantization setup. For a project where the *system design* is the
point, not squeezing out maximum tokens/sec, that trade is correct.
**The three models used and why these specific ones:**
- `qwen2.5:0.5b` (small) — extremely small and fast, good enough for trivial factual questions.
- `phi3:mini` (medium) — a solid mid-size general-purpose model; also used as the baseline's single
  fixed model, so the baseline is "a reasonable naive default," not a strawman.
- `mistral:7b-instruct-q4_0` (large) — genuinely more capable, genuinely slower. The `q4_0` suffix
  means 4-bit quantization: the model's weights are compressed to run on ordinary hardware at some
  quality cost, a standard trade for local inference.

### Sentence-Transformers (`all-MiniLM-L6-v2`) — the embedding model
**What it is:** a small, pretrained neural network whose only job is: read a sentence, output a
list of 384 numbers (a vector) that captures its *meaning*. Two sentences with similar meaning get
vectors that point in similar directions.
**Why it's here:** it's the mechanism that makes the cache "semantic" instead of exact-string. See
Part 6 for how the comparison itself (cosine similarity) works.
**Why this specific model:** `all-MiniLM-L6-v2` is the standard lightweight choice for this task —
small (~80MB), fast on CPU (no GPU needed), well-benchmarked. A larger embedding model would give
marginally better semantic matching at meaningfully higher latency and memory cost, not worth it at
this scale.

### Qdrant — the vector database
**What it is:** a database purpose-built for one query: *"of these N stored vectors, which is
closest to this new vector?"* — answered fast even at large N via an indexing structure (HNSW)
instead of comparing against every stored vector one by one.
**Why it's here:** it's what makes the cache **persistent** (Module 2) — Qdrant writes to disk, so
cache entries survive an app restart, unlike the original prototype's plain Python list that lived
only in RAM.
**Why Qdrant over the alternative (`pgvector`, a Postgres extension that adds vector search into
Postgres itself):** `pgvector` is a legitimate simpler choice (one database instead of two). Qdrant
was chosen here because it's purpose-built and more scalable — a defensible choice either way; see
`FINAL_REPORT.md`/`ARCHITECTURE.md` for the explicit acknowledgment of this trade-off.

### PostgreSQL — the relational database
**What it is:** a standard SQL database for structured, row-based data.
**Why it's here, separately from Qdrant:** Qdrant answers "what's similar to this?" — it's bad at
"give me all rows where X and average column Y," which is exactly what audit logs, user accounts,
and dashboards need. Two specialized databases, each doing only the job it's good at.
**What's stored here:** `query_log` (every request: text, tier, cache hit, latency, cost, who made
it) and `api_keys` (who's allowed to call the API). See `db/init.sql` for the exact schema.

### FastAPI — the web framework
**What it is:** a Python framework for building HTTP APIs, with automatic request validation
(via Pydantic) and automatic interactive docs (`/docs`).
**Why it's here:** Module 1 turned the original demo script into a real, stateless HTTP service —
FastAPI was chosen for being fast to write, fast to run, and self-documenting (the `/docs` page you
can open in a browser is generated automatically from `api.py`'s type hints, not hand-written).

### scikit-learn — the learned router's ML library
**What it is:** the standard Python machine learning library for classical (non-deep-learning) ML.
**Why it's here:** Module 4's learned router is a `TfidfVectorizer` (turns text into numeric
features) feeding a `LogisticRegression` classifier (predicts small/medium/large from those
features) — see Part 6 for how this actually works. scikit-learn was chosen because the routing
problem (three-way text classification on a small dataset) doesn't need a neural network — a
classical model is faster to train, easier to explain, and won't meaningfully underperform a deep
model at this data volume (46 examples as of Module 4/7).

### BERTScore — the quality metric
**What it is:** a published metric (Zhang et al.) that scores how semantically similar two pieces
of text are, using a pretrained BERT-family model's internal representations rather than
exact-word overlap (unlike, say, BLEU).
**Why it's here:** Module 5 replaced the original 10-example, one-off "ask a model to judge" check
with a defensible, repeatable, larger-sample metric. It answers "did the cheap model's answer mean
roughly the same thing as what the expensive model would've said?" without needing another LLM call
per comparison.

### Prometheus + Grafana — monitoring
**What they are:** Prometheus scrapes numeric metrics from an app on a timer and stores them as a
time series; Grafana queries Prometheus and draws dashboards from that data.
**Why they're here:** the de facto free/open-source standard for exactly this job — Module 5 added
custom metrics in `api.py` (`costqual_queries_total`, `costqual_query_latency_ms`,
`costqual_estimated_cost_total`) exposed at `/metrics`, which Prometheus scrapes every 15 seconds
(`monitoring/prometheus.yml`), and Grafana visualizes via an auto-provisioned dashboard.

### Docker / Docker Compose — packaging
**What it is:** Docker packages an application and everything it needs (OS libraries, Python
version, dependencies) into a single portable "container." Compose lets you define several
containers that work together (the whole stack here: Postgres, Qdrant, Ollama, the API, Prometheus,
Grafana) and start them all with one command.
**Why it's here:** reproducibility. `docker compose up -d` gets anyone — you, a professor, a future
you in six months — the exact same running system without manually installing six different
pieces of software correctly.

### GitHub Actions — CI/CD
**What it is:** GitHub's built-in automation — runs a defined script (`.github/workflows/ci.yml`)
every time code is pushed.
**Why it's here:** Module 6 — every push automatically spins up real Postgres/Qdrant containers,
pulls the small Ollama models, and runs the full test suite, so a broken change is caught
immediately rather than discovered later by a human.

### psycopg2, Pydantic, joblib, scipy — the supporting cast
- **psycopg2** — the Python library that actually speaks Postgres's wire protocol; `db.py` is a
  thin wrapper around it, no ORM (deliberately — the queries are simple enough that an ORM would
  add complexity without adding value).
- **Pydantic** — FastAPI's request/response validation; `QueryRequest`/`QueryResponse` in `api.py`
  are Pydantic models, so a malformed request is rejected automatically with a clear error, before
  your code ever sees it.
- **joblib** — serializes the trained scikit-learn pipeline to disk (`router_model.joblib`) so it
  doesn't need retraining on every process start.
- **scipy** — provides the chi-squared statistical test used by `drift_monitor.py`.

---

## Part 4 — One request, traced end to end

This is the single most important thing to understand — everything else in the repo supports this
path. Follow a `POST /query` call for `"What is the capital of Japan?"`:

1. **`api.py`** receives the HTTP request. FastAPI validates it against `QueryRequest` (must have a
   `query` string; `system` defaults to `"adaptive"`).
2. **`require_api_key`** (a FastAPI "dependency," in `api.py`) reads the `X-API-Key` header, calls
   `db.get_api_key_owner(key)` — a `SELECT` against the `api_keys` table in Postgres. No match →
   HTTP 401 immediately, request stops here.
3. **`adaptive.py`'s `ask_adaptive(query)`** is called.
4. It calls **`cache.py`'s `check_cache(query)`**:
   a. `embed(query)` runs the query through the Sentence-Transformers model → a 384-number vector.
   b. That vector is sent to **Qdrant** with a similarity search request, filtered to only consider
      entries whose `created_at` is within the last 24 hours (the TTL).
   c. Qdrant returns the closest match's cosine similarity score. If it's ≥ 0.87 (the configured
      threshold), that's a **hit** — return the stored answer immediately, done. If not, or if the
      cache is empty, it's a **miss** — continue.
5. On a miss, **the router decides a tier**. `adaptive._route(query)` checks `config.ROUTER_MODE`:
   - `"rule_based"` (default) → `router.route(query)` runs the regex/keyword checks in
     `router.py` and returns `"small"`, `"medium"`, or `"large"`.
   - `"learned"` → `learned_router.route(query)` runs the trained classifier instead.
6. **`ollama_client.py`'s `call_model(model, query)`** sends an HTTP POST to Ollama's
   `/api/generate` with the chosen model name and the query as the prompt, waits for the full
   response (not streamed), and returns the answer text plus token counts and latency.
7. Cost is computed: `(input_tokens + output_tokens) * COST_PER_TOKEN[tier]` — a synthetic
   fake-USD-per-token rate from `config.py`, not a real bill (see Part 8 for why).
8. **`cache.py`'s `add_to_cache(...)`** writes the new (query, answer, tier, timestamp) into
   Qdrant, so the *next* similar question hits step 4b instead of repeating steps 5-8.
9. Back in **`api.py`**: the result is logged to Postgres (`db.log_query`, including which API key
   made the request), three Prometheus metrics are updated (`.inc()` on counters, `.observe()` on
   the latency histogram), and a `QueryResponse` is returned to the client.

Every one of those numbered steps corresponds to a real, separate piece of infrastructure you can
inspect independently: Postgres for step 2 and 9, Qdrant for step 4 and 8, Ollama for step 6,
Prometheus/Grafana for step 9's metrics.

---

## Part 5 — File-by-file: what, how, why, impact

### Core serving logic

**`config.py`** — every tunable value in one place: which model backs each tier
(`MODEL_TIERS`), the fake cost-per-token table (`COST_PER_TOKEN`), the cache similarity threshold
(`CACHE_SIMILARITY_THRESHOLD = 0.87`) and TTL (`CACHE_TTL_SECONDS`, 24h), connection URLs for
Postgres/Qdrant/Ollama (each read from an environment variable with a sensible local default via
`os.environ.get(...)`), and `ROUTER_MODE`. *Why centralized:* so changing behavior means editing
one file, not hunting through the codebase. *Impact if misconfigured:* wrong `MODEL_TIERS` values
would silently route to the wrong (or a nonexistent) model; wrong DSN/URL values mean the whole app
fails to start.

**`ollama_client.py`** — the *only* file that talks to Ollama directly (`call_model`). It retries
up to twice on request failure (a slow/stalled response under load isn't a real error, so retrying
is safer than crashing the whole benchmark run over one flaky call). *Why centralized:* if you ever
swapped Ollama for something else, this is the only file that would need to change.

**`baseline.py`** — Setup A. One function, `ask_baseline(query)`: always calls
`config.BASELINE_MODEL` (`phi3:mini`), no cache, no routing. Deliberately the simplest possible
implementation — it exists specifically to be the thing the adaptive system is measured against.

**`router.py`** — the rule-based classifier. Three checks, in order (see the actual patterns in
the file): short + matches a "simple question" pattern (starts with "what is," "define," etc.) →
`small`; contains a reasoning keyword ("explain," "compare," "why," etc.) or is long → `large`;
otherwise → `medium`. *Why rules and not ML from the start:* transparency — you can read every
decision boundary in 30 lines, no training data needed, and it's the honest baseline the learned
router (Module 4) is measured against.

**`learned_router.py`** — same `route(query) -> str` interface as `router.py`, but backed by
`router_model.joblib` (loaded lazily, once, on first use). If the model file doesn't exist yet, it
**falls back to the rule-based router** rather than crashing — the learned router is never allowed
to hard-fail a request. *Why it exists separately from `router.py` rather than replacing it:*
`config.ROUTER_MODE` picks between them, so the (currently weak, 58% accurate) learned router can
be A/B tested without risking the whole system's routing quality on it.

**`cache.py`** — the persistent semantic cache. Key implementation details worth understanding:
- `_get_model()` is a **thread-safe lazy singleton**: the embedding model is only loaded on first
  use (saves startup time when the cache is never touched), and it uses **double-checked
  locking** (`if _model is None: with _model_lock: if _model is None: ...`) — this exists because
  load testing (Module 6) found a real race condition here (see Part 7).
- `SemanticCache` is a class, not just module functions, so it can point at any Qdrant collection —
  the module-level default instance (`_default_cache`) always uses the fixed collection name
  `"semantic_cache"` so it reconnects to the same persisted data across restarts, while tests create
  their own uniquely-named instances for isolation.
- `check()` does a Qdrant similarity search with **two filters at once**: `score_threshold` (must
  be similar enough) and a `Filter` on `created_at` (must be fresh enough) — both conditions have to
  pass for a hit.
- `purge_expired()` and `cache_reaper.py` exist because freshness is already enforced at *lookup*
  time (stale entries are simply never matched), so purging is purely storage hygiene, safe to run
  on a schedule rather than every request.

**`adaptive.py`** — Setup B. `ask_adaptive(query)` wires `cache.py` and the router together: check
cache → on miss, route → call model → write to cache → return. `_route()` is the one function that
reads `ROUTER_MODE` and picks which router implementation to call.

### Service layer

**`api.py`** — the FastAPI app. `require_api_key` is a *dependency* (FastAPI's term for a function
that runs before the route handler and can inject a value into it, here the key's owner) — this is
why `/health` and `/metrics` are exempt from auth (they don't declare the dependency) while
`/query` requires it. The three `Counter`/`Histogram` objects at module level are created *once* at
import time — Prometheus client objects are meant to be long-lived singletons, not recreated per
request.

**`db.py`** — thin Postgres wrapper. Every function opens its own connection (`get_connection()`)
rather than holding a pool — simple and correct at this traffic volume; a real production system
handling significant concurrent load would want connection pooling (e.g. `psycopg2.pool` or
PgBouncer) instead, a known simplification.

**`db/init.sql`** — the schema, applied automatically by Postgres's Docker image on first
container start (via the `docker-entrypoint-initdb.d` convention) — this is *why* it only runs
once per fresh volume, and why Module 6's auth columns had to also be applied as a live migration
against the already-running container, not just added to this file.

**`manage_keys.py`** — a minimal CLI (`python manage_keys.py create <name>`) rather than a
self-service signup flow — deliberately out of scope; issuing keys is an operator action here, not
a user-facing feature.

### Learned router training

**`seed_traffic.py`** — replays `test_queries.json` through the **live API** (not a direct Python
call) specifically so the resulting `query_log` rows are genuine, auth-attributed, Prometheus-
tracked requests — training data collected the same way real production traffic would be.

**`train_router.py`** — pulls `(query_text, tier_used)` pairs from `query_log` **where
`cache_hit = false`** (a cache hit isn't a routing decision, it's a cache reuse — including it would
teach the classifier "sometimes the answer is just whatever the cache said," which is meaningless).
Does a stratified 75/25 train/test split to report an honest held-out accuracy number, *then*
refits on 100% of the data for the actual deployed model (standard practice: evaluate on held-out
data, deploy the model trained on everything).

### Quality & drift monitoring

**`quality_check.py`** — the original (Module 0) approach: LLM-as-judge. Finds cases where the
router used a smaller model *and* got a different answer than baseline, samples 10, asks the
baseline model itself to grade PASS/FAIL. Cheap and fast, but small-sample and dependent on the
judge model's own competence.

**`quality_monitor.py`** — the Module 5 upgrade: **BERTScore** across every eligible case (36, not
10), no extra LLM call needed. Excludes `tier_used == "large"` rows because there's nothing to
compare — the large tier *is* the reference model.

**`drift_monitor.py`** — compares the tier-distribution of the most recent N logged decisions
against an earlier reference window using a **chi-squared goodness-of-fit test**, which answers
"does this recent distribution look statistically different from that reference distribution?" A
low p-value (< 0.05) means yes, flag it. Correctly reports "not enough data" rather than a
misleading result when there isn't enough logged history yet.

### Test data & experiment runner

**`test_queries.json`** — 60 hand-curated questions in five categories (15 exact duplicates, 15
paraphrases, 10 simple, 10 complex, 10 unique) — the categories exist specifically so the report
can show *why* the cache hit rate is what it is (duplicates and paraphrases should hit; simple/
complex/unique shouldn't, by design).

**`run_benchmark.py`** — runs the fixed query set through both systems and logs every result to
`benchmark_results.csv`. Both systems get an **unwarmed start** (no pre-populated cache) for
fairness, but models are warmed up (one throwaway call each) *before* either pass, so first-call
model-load time doesn't unfairly penalize whichever system runs first.

**`load_test.py`** — the one script that doesn't run through `run_benchmark.py`'s sequential logic
at all; it fires genuinely **concurrent** requests via `ThreadPoolExecutor` and reports
success rate, throughput, and latency percentiles — this is the script that found the real
concurrency bug (Part 7).

### Reporting & demo

**`generate_report.py`** — reads `benchmark_results.csv`, computes stats, draws two matplotlib bar
charts, and writes `report.md`. Reads `quality_check_results.csv` if present to append the quality
section. The `latency_verb` logic (`"reduced" if latency_reduction_pct >= 0 else "increased"`)
exists because a naive template would have printed "reduced latency by -80%" when latency actually
got worse — a real clarity bug found and fixed in Module 7.

**`demo.py`** — an interactive CLI loop, the only file meant to be *watched* rather than measured;
useful for showing someone the cache-hit-on-paraphrase moment live.

### Infrastructure

**`Dockerfile`** — a standard `python:3.12-slim` base, installs `requirements.txt`, copies the
code, runs `uvicorn`. Nothing unusual.

**`docker-compose.yml`** — defines all 6 services. Two details worth understanding:
- `ollama-pull` is a *one-shot* service (not long-running) — it pulls the three models into the
  named `ollama_data` volume and exits; you run it once after a fresh volume, not on every startup.
- Prometheus scrapes the `api` service by its **Docker Compose service name** (`api:8000`), which
  works because Compose gives every service DNS resolution to every other service's name on the
  same network — no IP addresses anywhere in the config.

**`monitoring/`** — `prometheus.yml` (scrape config) and `grafana/` (auto-provisioned datasource +
the dashboard JSON) — "auto-provisioned" means Grafana reads these files on container start and
sets itself up with no manual clicking required, which is what makes `docker compose up -d` a
genuine one-command deployment rather than "mostly automated, plus five manual dashboard clicks."

**`.github/workflows/ci.yml`** — runs on every push. Two non-obvious details: it frees ~10GB of
disk space at the start (removing preinstalled toolchains the project never uses) because the first
real CI run failed with "no space left on device" once torch (a `sentence-transformers` dependency)
and the Ollama models were both installed; and it deliberately **doesn't** pull `mistral:7b`,
skipping the one test that needs it (`@pytest.mark.requires_large_model`) to keep every push fast.

---

## Part 6 — The algorithms, explained properly

### Cosine similarity (the cache's core comparison)
Every embedding is a point in 384-dimensional space. Cosine similarity measures the **angle**
between two vectors, not the distance between them — it asks "do these two vectors point in
roughly the same direction?" rather than "are these two points close together?" This matters
because it makes the comparison insensitive to vector *magnitude*, which for text embeddings tends
to correlate with things like sentence length rather than meaning — two ways of asking the same
short question should score as similar even if their raw vector lengths differ slightly. The score
ranges from -1 (opposite) to 1 (identical direction); the 0.87 threshold in `config.py` was chosen
empirically as "similar enough to be the same underlying question, not so loose that unrelated
questions match."

### TF-IDF + Logistic Regression (the learned router)
**TF-IDF** ("term frequency-inverse document frequency") turns a sentence into a vector of numbers,
one per word (or word-pair, since `train_router.py` uses `ngram_range=(1, 2)`), where the number is
high if that word appears often in *this* query but rarely across *all* queries — i.e., it
up-weights distinctive words and down-weights common ones like "the" or "is" automatically, with no
manual stop-word list needed. **Logistic Regression** then learns a weight for each of those word
features that best predicts the tier label, from the 46 real examples in `query_log`.
`class_weight="balanced"` compensates for the tiers not being equally common in the training data
(there were more "small" examples than "large" in the seeded data), so the model isn't just biased
toward predicting whichever tier was most common. This is a genuinely simple model — no neural
network, no attention mechanism — which is appropriate at 46 training examples (a neural network
would badly overfit that little data) and is exactly why the held-out accuracy (58%) is honest
rather than inflated.

### BERTScore
Instead of comparing two answers word-for-word (which fails when a correct answer is phrased
differently), BERTScore runs both texts through a pretrained BERT-family model to get a contextual
embedding *for each token*, then finds the best-matching token pairs between the two texts and
computes precision (do the candidate's tokens find good matches in the reference?), recall (does
the reference's meaning show up in the candidate?), and F1 (their harmonic mean) from those
matches. The F1 score is what `quality_monitor.py` reports and thresholds against (0.85).

### The chi-squared goodness-of-fit test (drift detection)
Given two distributions — "how often was small/medium/large used recently" vs. "how often
historically" — the chi-squared statistic measures how far the *observed* recent counts are from
what you'd *expect* if the recent traffic followed the same distribution as before. A large
statistic (→ small p-value) means the recent pattern is unlikely to be random noise around the old
pattern — i.e., something about incoming traffic has genuinely shifted.

### Double-checked locking (the concurrency fix)
The bug: `if _model is None: _model = SentenceTransformer(...)` looks safe in single-threaded code,
but under concurrency, two threads can both read `_model is None` as `True` *before either has
finished constructing the model*, so both proceed to construct it simultaneously — which corrupted
PyTorch's internal lazy device-initialization state and crashed. The fix acquires a lock **only
when construction might be needed**, then re-checks `_model is None` *inside* the lock (hence
"double-checked") — the second check is what prevents a second thread, which was waiting on the
lock while the first thread already finished constructing, from constructing it again. This pattern
is standard for making a lazy singleton thread-safe without paying the cost of locking on every
call after the first.

---

## Part 7 — The 7-module journey: why each module was necessary, in order

| # | What was wrong before | What the module fixed | Why it had to come at this point |
|---|---|---|---|
| 1 | It was a script (`demo.py`), not a service; nothing persisted | Docker infra (Postgres+Qdrant), a real FastAPI service, request logging | Everything downstream needs a running service and somewhere to log to |
| 2 | Cache was a Python list — wiped on every restart | Qdrant-backed cache with per-entry TTL | Needed the infra from Module 1 (Qdrant) already running |
| 3 | "Large" tier silently aliased to the same model as "medium" | Genuinely distinct 3rd model; real usage logging | Needed the logging (Module 1) to be worth collecting data with |
| 4 | Router was fixed rules only | Trained classifier, behind a flag | Needed *real* routing decisions logged (Module 3) as training data — could not have been built first |
| 5 | Quality checked once via 10-sample LLM-judge; no visibility into live behavior | BERTScore (continuous, larger sample), drift detection, Prometheus/Grafana | Needed real traffic (Module 3) and a real router (Module 4) worth monitoring |
| 6 | Anyone could call the API; no automated testing; never tested under concurrency | API-key auth, CI/CD, load testing — which found a real bug | Needed a stable feature set (Modules 1-5) before locking it down and automating its testing |
| 7 | Numbers were from the old 2-tier prototype; no one-command deployment | Fresh benchmark on the real system, full Docker deployment, final report | Could only be done once every other module was actually finished |

Notice the dependency chain is real, not cosmetic: Module 4 could not have come before Module 3
(no real data to train on), Module 5's drift detection is only meaningful with Module 3's real
traffic, and Module 7's benchmark had to be last because it measures everything that came before it.

---

## Part 8 — Design decisions and trade-offs (the "why not X instead" list)

- **Why a fake-cost proxy instead of real API pricing?** Local inference is free — there's no real
  bill to measure. The proxy exists to tell a *relative* story (routing away from the expensive
  tier saves money) using per-token weights modeled loosely on real hosted-model pricing tiers. This
  is clearly labeled throughout the docs specifically so it's never mistaken for a real dollar
  claim.
- **Why API keys instead of OAuth/JWT?** Simplicity matched to actual need — this is a single-tenant
  research project, not a multi-org SaaS product. An API key with a `db.get_api_key_owner` lookup
  gives real per-user attribution and access control without the complexity of a token-issuing auth
  server.
- **Why TF-IDF+LogisticRegression instead of a neural classifier for the learned router?** At 46
  training examples, a neural network would overfit badly. A classical model is the *correct*
  choice at this data volume, not a corner cut — see Part 6.
- **Why does `ROUTER_MODE` default to `"rule_based"` even though Module 4 is "done"?** Because
  "done" means "built, tested, and integrated," not "better than the alternative." The honest
  held-out accuracy (58%) doesn't yet justify replacing the rule-based router in production traffic
  — the flag exists specifically so that judgment call is explicit and reversible, not hidden.
- **Why a flat 24h cache TTL instead of content-aware expiry** (e.g., "boiling point of water"
  never needs to expire, but "today's weather" should expire in an hour)? Detecting which category
  a query falls into is itself a hard classification problem — solving it well would mean building
  essentially a second router. A flat TTL is a deliberately simple, defensible default; content-aware
  expiry is called out as future work, not silently ignored.
- **Why skip the large-tier model in CI?** A 4GB download on every single push would make CI slow
  and expensive for a marginal benefit (the large-tier test is still run, just locally before a
  release, not on every commit).
- **Why is latency *worse* on average, and why wasn't that "fixed"?** Because it's not a bug — the
  large tier is a genuinely more capable, genuinely slower model than the baseline's fixed model.
  "Fixing" it would mean either picking a faster large model (reducing capability) or adding
  latency-aware routing (real future work, not yet built). Reporting it honestly, rather than
  picking a benchmark that hides it, is a deliberate choice.

---

## Part 9 — Honest self-assessment: what's strong, what's weak

**Strong, and defensible under scrutiny:**
- The core hypothesis (cache + routing beats naive serving) held up under the *harder*, more honest
  version of the system (real 3 tiers, real persistence) with an even better cost result (58% vs.
  the prototype's 35%) once the tier-aliasing bug was fixed.
- Every claimed number was verified live, not just asserted — the Module 6 concurrency bug is a
  concrete example of the testing actually catching something real.
- Full reproducibility: no paid API, `docker compose up -d` gets anyone the same running system.

**Weak, and you should be able to say so unprompted:**
- **Learned router: 58% held-out accuracy on 46 examples.** This is not a strong result. It's
  honestly reported and deliberately not deployed by default, but if a paper cites "we built a
  learned router," the accuracy number needs to be in the same sentence.
- **Single benchmark run, no variance reporting.** Every number is from one pass. Latency
  especially has real run-to-run variance on local hardware; there's no mean±std across multiple
  runs anywhere in the repo yet.
- **Custom, non-standard test set.** `test_queries.json`'s 60 questions aren't a published
  benchmark (unlike MMLU, MT-Bench). Great for reproducing *this project's* numbers; not directly
  comparable to numbers from other papers unless they also use this exact dataset.
- **No comparison against published routing systems** (FrugalGPT, RouteLLM, etc.) — only against an
  internal naive baseline.
- **Drift detection has never been tested against real drift** — only that the mechanism runs
  without crashing on one seeding batch.
- **CI never exercises the large-tier model** — a real coverage gap, mitigated but not closed by
  running it locally.

---

## Part 10 — Questions you should be able to answer cold

**"What's the actual novel contribution here, since none of the individual techniques are new?"**
The system design and its verification: combining semantic caching with complexity-aware routing
into one measured pipeline, then building the production infrastructure (persistence, auth,
monitoring, CI/CD) around it and re-measuring under real conditions — including honestly reporting
where the results got *worse* (latency) alongside where they got better (cost).

**"Why does the adaptive system cost less but take longer on average?"** Because cost and speed
aren't the same axis. Routing to a cheaper model saves money on every query it touches; the large
tier being a genuinely more capable (and slower) model than the baseline's fixed model means the
subset of queries that need it take longer than they would have under the baseline. Averaged across
all queries, cost improves because most queries don't need the large tier; latency worsens because
the ones that do take longer than baseline's uniform speed.

**"How do you know the cache isn't giving wrong answers for different questions (a false hit)?"**
The similarity threshold (0.87) is the control — raise it for stricter matching (fewer false hits,
more cache misses) or lower it for looser matching (more hits, higher false-hit risk). It's a
tunable knob, empirically set, not a guarantee.

**"What happens if Ollama, Postgres, or Qdrant goes down mid-request?"** Not gracefully handled
today — `ollama_client.py` retries transient failures, but a hard outage of any dependency will
surface as a 500 error to the caller. Health checks exist (`/health`) to *detect* this, not to
recover from it automatically; that's a real, acknowledged gap.

**"Why keep the rule-based router as the default when you built a learned one?"** Because "we built
a learned router" and "the learned router is better" are different claims, and only the first one
is currently true. The flag exists to make that distinction operationally real, not just
theoretical.

**"If everything here (Ollama, Qdrant, Postgres, scikit-learn, FastAPI) already exists, what did
you actually build?"** The system that connects them into one coherent pipeline, with the design
decisions (why Qdrant, why this TTL scheme, why this auth model, why this CI approach) made and
justified, verified end-to-end with real traffic, and honestly reported — including the parts that
didn't work as well as hoped.

---

## Part 11 — For the research paper specifically

What to lead with: the **58% cost reduction** with the **89% BERTScore pass rate** is your strongest
paired result — cost went down *and* quality was independently verified to have held up, on a
larger sample than the original prototype's 10-example spot check.

What a reviewer will push on, and how to answer without over-claiming:
- *"Is 58% cost reduction statistically significant?"* → Currently: no significance test has been
  run; this is a real, stated limitation (Part 9). If asked to strengthen this before submission,
  run `run_benchmark.py` multiple times and report a confidence interval.
- *"Why isn't the learned router deployed?"* → Answer directly: 58% held-out accuracy on 46
  examples isn't yet better than the rule-based baseline it's meant to replace; it's flagged off by
  design, and the honest number is the point, not a weakness to hide.
- *"How does this compare to [FrugalGPT/RouteLLM/other published system]?"* → Currently doesn't;
  only compared against an internal naive baseline. State this as a limitation and future work, not
  something implied to have been done.

What's genuinely citable as-is: the system architecture, the concurrency bug found by load testing
(a legitimate finding about testing methodology, not just the system itself), the honest
latency/cost trade-off, and the full reproducibility story (open-source, self-hosted, no paid API).
