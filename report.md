# CostQual-Router Prototype -- Comparison Report

## Latency

| System | Total (ms) | Average (ms) |
|---|---|---|
| Baseline | 271574.8 | 4526.2 |
| Adaptive | 489201.9 | 8153.4 |

## Estimated cost

| System | Total estimated cost |
|---|---|
| Baseline | 0.078584 |
| Adaptive | 0.032877 |

## Cache hit rate by category (adaptive only)

| Category | Hits | Total | Hit rate |
|---|---|---|---|
| complex | 0 | 10 | 0% |
| duplicate | 8 | 15 | 53% |
| paraphrase | 6 | 15 | 40% |
| simple | 0 | 10 | 0% |
| unique | 0 | 10 | 0% |

Overall cache hit rate: **23%**

## Tier usage distribution (adaptive, cache misses only)

| Tier | Share of cache-miss queries |
|---|---|
| large | 22% |
| medium | 35% |
| small | 43% |
## Quality sanity check

Of the queries where the adaptive router used a smaller model than the baseline **and** produced a different answer, 10 were sampled and judged (by the baseline model) for whether the smaller model's answer was still acceptable: **7/10 passed (70%)**. This is a lightweight sanity check, not a rigorous eval -- see `quality_check_results.csv` for the sampled question/answer pairs and `prototype_plan.md` Step 9 for scope.

## Charts

![Estimated cost comparison](cost_comparison.png)

![Average latency comparison](latency_comparison.png)

## Interpretation

The adaptive system (semantic cache + complexity-based model routing) reduced estimated cost by **58%**, while average latency increased by **80%** compared to the always-on baseline -- the large tier (mistral:7b) is genuinely more capable but slower than the baseline's phi3:mini, so latency is a real tradeoff for cost savings on the queries routed there. Cache hit rate was **23%** overall, driven mostly by the duplicate and paraphrase query categories -- confirming that semantic caching catches near-duplicate questions, not just exact repeats, without needing a larger model for queries that don't require one.
