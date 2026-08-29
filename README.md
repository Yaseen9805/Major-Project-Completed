# CostQual-Router

An adaptive LLM-serving system that combines a **persistent semantic cache** with
**complexity-based model routing** to cut serving cost and latency without sacrificing answer
quality — self-hosted end to end, no paid third-party API involved.

- **Setup A (baseline)** — every query goes to one fixed model, no cache, no routing.
- **Setup B (adaptive)** — a semantic cache catches duplicate/paraphrased questions instantly; a
  router (rule-based, or a trained classifier behind a flag) sends new questions to the smallest
  of three genuinely distinct model tiers that can handle them.

This started as a 5-day proof-of-concept (see `prototype_plan.md` for that original spec) and has
since been extended through 7 build modules into the system described here: persistent storage,
real model tiers, a learned router, quality/drift monitoring, API-key auth, CI/CD, and a
one-command Docker deployment. See `MODULES.md` for what each module added and `FINAL_REPORT.md`
for the full final results.

- New to this repo? Start with **`ARCHITECTURE.md`** for a file-by-file explanation.
- Want the module-by-module build history? See **`MODULES.md`**.
- Want the final results and comparison against the baseline/prototype? See **`FINAL_REPORT.md`**.
- Need the formal summary? See **`ABSTRACT.md`**.

## Requirements

- Docker Desktop
- Python 3.12+
- [Ollama](https://ollama.com) installed locally
- ~7 GB free disk space (three Ollama models: `qwen2.5:0.5b`, `phi3:mini`,
  `mistral:7b-instruct-q4_0`)

## Running it

**1. Pull the three models** (one-time):

```bash
ollama pull qwen2.5:0.5b
ollama pull phi3:mini
ollama pull mistral:7b-instruct-q4_0
```

**2. Start the full stack with one command:**

```bash
docker compose up -d
```

This brings up PostgreSQL, Qdrant, Ollama, the API, Prometheus, and Grafana. First run only, pull
the models into the container's volume too:

```bash
docker compose up ollama-pull
```

**3. For running scripts locally** (tests, `manage_keys.py`, the benchmark, etc. — not needed for
the API itself, which runs inside its container):

```bash
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

**4. Create an API key** (required for every `/query` call):

```bash
python manage_keys.py create your_name
```

**5. Ask it something:**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your key>" \
  -d '{"query": "What is the capital of France?"}'
```

**6. Look around:**

- API docs: `http://localhost:8000/docs`
- Grafana dashboard: `http://localhost:3000` (`admin`/`admin`)
- Prometheus: `http://localhost:9090`

## Other useful commands

```bash
pytest -q                    # run the test suite
python run_benchmark.py      # regenerate the baseline-vs-adaptive benchmark
python generate_report.py    # rebuild report.md + charts from that benchmark
python quality_check.py      # LLM-judge quality spot check
python quality_monitor.py    # BERTScore quality evaluation
python drift_monitor.py      # check for routing/traffic drift
python train_router.py       # retrain the learned router on logged usage
python load_test.py          # concurrent load test against the live API
python demo.py               # interactive CLI: type a question, see baseline vs adaptive
```

## Results (final system, from `FINAL_REPORT.md`)

Benchmarked on a fixed 60-query test set (duplicates, paraphrases, simple, complex, unique),
comparing the always-on baseline against the final adaptive system:

| Metric | Baseline | Adaptive | Change |
|---|---|---|---|
| Total estimated cost | 0.078584 | 0.032877 | **-58%** |
| Average latency | 4,526 ms | 8,153 ms | **+80%** |
| Cache hit rate | — | 23% | — |
| Answer quality (BERTScore F1) | — | 0.908 avg, 89% pass rate | — |

**Cost dropped substantially** — the adaptive system only pays the expensive tier's rate when a
question genuinely needs it. **Latency is an honest, disclosed tradeoff, not a hidden regression**:
the large tier (`mistral:7b`) is more capable but slower than the baseline's fixed model, so
questions routed there take longer even though routing is behaving correctly. **23% of queries hit
the cache**, driven mostly by duplicate (53%) and paraphrase (40%) categories — confirming the
semantic cache catches reworded repeats, not just exact ones. **Quality held up**: BERTScore
comparison against the baseline's answers averaged 0.908 F1 with an 89% pass rate.

Full breakdown, methodology, the concurrency bug found and fixed by load testing, and known
limitations: see `FINAL_REPORT.md`.

## Cost model

Since local inference is free, `estimated_cost` is a proxy that applies a fixed fake-USD-per-token
weight per tier (see `config.py`'s `COST_PER_TOKEN`), modeled loosely on what a naive team would
pay per token on hosted small/medium/large model tiers. It tells a *relative* cost story (routing +
caching vs. one fixed expensive model), not a real dollar prediction.

## Testing

```bash
pytest -q
```

28 tests cover cache persistence and TTL, routing logic (rule-based and learned), the API
(including auth), and a regression test for a real concurrency bug found during load testing. CI
(`.github/workflows/ci.yml`) runs this suite on every push against real Postgres/Qdrant containers
and freshly-pulled small/medium Ollama models; the one test requiring the large model is marked
`@pytest.mark.requires_large_model` and run locally instead, to keep CI fast.

## Troubleshooting: garbled or off-topic answers

If a model's answers suddenly turn into incoherent, unrelated text, that's not a bug in this code —
it means the Ollama server's in-memory model state got corrupted, typically after sustained heavy
system load. Fix:

```bash
ollama stop phi3:mini
ollama stop qwen2.5:0.5b
ollama stop mistral:7b-instruct-q4_0
# then restart the Ollama app/service -- it reloads models fresh on the next request.
```

## Sharing this project

Do **not** zip/copy the `venv/` folder — it's Windows/Python-version specific and huge. Ollama
models aren't part of this folder either; pull them fresh with `ollama pull` on each machine.
