# CostQual-Router -- Comparison Prototype

A small proof-of-concept comparing two ways of serving LLM queries locally:

- **Setup A (baseline)** -- every query goes to one fixed model (`phi3:mini`), no cache, no routing.
- **Setup B (adaptive)** -- a semantic cache catches duplicate/paraphrased questions, and a
  rule-based complexity router sends new questions to the smallest model tier that can handle
  them (`qwen2.5:0.5b` / `phi3:mini`).

The goal is to show, on a fixed 60-question test set, that the adaptive system is measurably
cheaper and faster with no meaningful quality loss.

This is a prototype for a pitch, not the production system -- see `prototype_plan.md` for the
full scope and what was deliberately left out (auth, CI/CD, k8s, monitoring, etc. all belong to
the real month-long project).

- New to this repo? Start with **`ARCHITECTURE.md`** for a file-by-file explanation of how it fits together.
- Need the formal summary? See **`ABSTRACT.md`**.

## How it works

| File | Role |
|---|---|
| `config.py` | Model tiers, cost-per-token assumptions, cache threshold |
| `ollama_client.py` | Thin wrapper around the local Ollama HTTP API |
| `baseline.py` | Setup A -- `ask_baseline(query)` |
| `cache.py` | In-memory semantic cache (sentence-transformers embeddings + cosine similarity) |
| `router.py` | Rule-based complexity classifier -- `route(query) -> "small"/"medium"/"large"` |
| `adaptive.py` | Setup B -- `ask_adaptive(query)`: cache check -> route -> call model -> cache write |
| `test_queries.json` | 60 labeled queries (duplicates, paraphrases, simple, complex, unique) |
| `run_benchmark.py` | Runs both systems over the test set, logs `benchmark_results.csv` |
| `generate_report.py` | Builds `report.md` + `cost_comparison.png` + `latency_comparison.png` |
| `quality_check.py` | Lightweight LLM-judge sanity check on answers that changed |
| `demo.py` | Live CLI demo: type a question, see both systems side by side |
| `tests/` | pytest unit tests for cache/router logic and handler shapes |

**Cost model:** since local inference is free, `estimated_cost` is a proxy that applies a fixed
fake-USD-per-token weight per tier (see `config.py`'s `COST_PER_TOKEN`), modeled loosely on what a
naive team would pay per token on hosted small/medium/large model tiers. It exists to tell a
*relative* cost story (routing + caching vs. one fixed expensive model), not to predict real bills.

**Model tiers:** only two model sizes are pulled to keep the prototype fast --
`qwen2.5:0.5b` (small) and `phi3:mini` (medium/large). `mistral:7b-instruct-q4_0` is an optional
third tier the plan allows skipping; add it to `MODEL_TIERS` in `config.py` if your machine can
run it comfortably.

## Requirements

- Windows, macOS, or Linux
- Python 3.11+
- [Ollama](https://ollama.com) installed and running locally
- ~3 GB free disk space for the two models
- Internet access on first run (to download the two Ollama models and the
  `all-MiniLM-L6-v2` embedding model from Hugging Face -- everything runs fully offline after that)

## Setup

```bash
# 1. Install and start Ollama (see ollama.com), then pull the two models:
ollama pull qwen2.5:0.5b
ollama pull phi3:mini

# 2. Create a virtual environment and install Python dependencies
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

## Running it

```bash
# Run both systems over the 60-query test set (takes several minutes -- baseline
# calls phi3:mini for every query, so it's the slow half)
python run_benchmark.py

# Generate the comparison report + charts
python generate_report.py

# Optional: sample quality check on answers where adaptive used a smaller model
python quality_check.py

# Run the unit tests
pytest tests/ -v
```

## Live demo

```bash
python demo.py
```

Type a question, see `[BASELINE]` and `[ADAPTIVE]` results printed side by side with latency,
cost, cache-hit status, and tier used. Ask the same question (or a paraphrase of it) twice in a
row to see the adaptive system return an instant, near-zero-cost cache hit on the second try.

## Results (from the included benchmark run)

60 queries (duplicates, paraphrases, simple, complex, unique) run through both systems, cold
cache for adaptive, on a local GPU-accelerated Ollama install:

| Metric | Baseline | Adaptive | Change |
|---|---|---|---|
| Avg latency | 6053 ms | 5881 ms | **-3%** |
| Total estimated cost | 0.11841 | 0.07700 | **-35%** |
| Cache hit rate | -- | 23% | -- |

Cache hits came almost entirely from the `duplicate` (53%) and `paraphrase` (40%) categories,
confirming the semantic cache catches reworded repeats, not just exact ones -- `simple`,
`complex`, and `unique` categories (by design, no repeats) had a 0% hit rate. Of cache misses,
43% were routed to the small model, 35% medium, 22% large.

Latency savings are modest on this run because the "large" tier (22% of cache misses -- genuinely
complex questions) can take as long as or longer than the baseline's single fixed model, offsetting
the time saved by instant cache hits and fast small-tier calls. Cost savings are the clearer story
here: the adaptive system only pays the expensive rate when a question actually needs it, instead
of paying it for every question by default. Latency and cost both have real run-to-run variance on
local hardware (see the retry note below) -- re-running `run_benchmark.py` will not reproduce these
exact numbers, only the same direction of effect.

A 10-sample quality spot-check (`quality_check.py`) on cases where the router picked a smaller
model and got a different answer than baseline passed 7/10 -- the tiny `qwen2.5:0.5b` model did
fumble a multi-step arithmetic question and one open-ended "yes/no" question, which is an honest,
expected limitation of a 0.5B-parameter model and worth knowing about, not a benchmark artifact.

Full numbers: `report.md`. Charts: `cost_comparison.png`, `latency_comparison.png`.

**Note:** long benchmark runs occasionally hit a slow/stalled response from the local Ollama
server under sustained load; `ollama_client.py` retries automatically, so a single slow call
won't crash the whole run.

## Troubleshooting: garbled or off-topic answers

If a model's answers suddenly turn into incoherent, unrelated text (not just a bad answer, but
text that looks like a completely different prompt), that's not a bug in this code -- it means the
Ollama server's in-memory model state got corrupted, which we saw happen after a benchmark run
that hit heavy, sustained system load (many other apps competing for CPU/GPU caused repeated
request timeouts and retries back-to-back). The fix is to clear Ollama's loaded models and restart
it:

```bash
ollama stop phi3:mini
ollama stop qwen2.5:0.5b
# then restart the Ollama app/service, or just re-run your script --
# Ollama reloads the model fresh on the next request.
```

For a reliable benchmark run (and before a live demo), close other heavy applications (browsers
with many tabs, IDEs, chat apps) first -- Ollama shares your CPU/GPU with everything else running.

## Sharing this project

Do **not** zip/copy the `venv/` folder -- it's Windows/Python-version specific and huge. Copy
everything else (all `.py`/`.json`/`.md` files) and have the other machine create its own venv
per the Setup section above. Ollama models are not part of this folder either -- they live in
Ollama's own data directory and must be pulled fresh with `ollama pull` on each machine.
