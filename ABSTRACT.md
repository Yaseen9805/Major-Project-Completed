# Abstract

**CostQual-Router: Adaptive Semantic Caching and Complexity-Based Model Routing for
Cost-Efficient LLM Serving**

Large Language Models (LLMs) are increasingly deployed as the default interface for
question-answering and conversational systems, but naive deployment strategies typically route
every user query to a single, uniformly capable — and expensive — model regardless of the
query's actual complexity. This results in significant unnecessary computational cost and
latency, particularly for simple or repeated queries that do not require full model capacity.
This project proposes and prototypes CostQual-Router, an adaptive LLM-serving architecture that
combines semantic caching with complexity-aware model routing to reduce cost and latency without
compromising answer quality.

The system maintains an embedding-based semantic cache that identifies not only exact repeat
queries but also semantically equivalent paraphrases, returning a cached response instantly when
a sufficiently similar prior query exists. For cache misses, a lightweight rule-based classifier
estimates query complexity and routes the request to the smallest capable model tier from a set
of locally hosted, open-source models, reserving the most capable tier for genuinely complex
queries.

An initial controlled benchmark comparing this adaptive system against a naive single-model
baseline, using a curated 60-query test set spanning exact duplicates, paraphrases, simple factual
questions, complex reasoning questions, and unique one-off queries, demonstrated a 35% reduction in
estimated serving cost and a 23% semantic cache hit rate with two of three tiers aliased to the same
underlying model, validating the core hypothesis.

The system was subsequently extended across seven build modules into a production-shaped service:
a genuine three-tier model hierarchy, persistent vector-based caching (Qdrant) with per-entry
expiry, a supervised learned routing classifier trained on real logged traffic (deployed behind a
feature flag pending more training data), rigorous quality evaluation via BERTScore in place of the
initial LLM-judge spot check, drift detection, and production-oriented infrastructure —
authentication, Prometheus/Grafana monitoring, CI/CD, and a fully containerized one-command
deployment — implemented entirely with free and open-source, self-hosted tooling. Re-benchmarked
against the completed system, results improved to a 58% reduction in estimated serving cost (once
the three model tiers were made genuinely distinct) and an 89% BERTScore pass rate on routed
answers, at the honestly-disclosed cost of an 80% increase in average latency versus the baseline,
attributable to the large tier's greater capability. A concurrency defect surfaced by load testing
was identified and fixed, with a regression test added. Full reproducibility is preserved throughout:
no paid third-party API is used at any point in the system.

**Keywords:** Large Language Models, Semantic Caching, Model Routing, Cost Optimization, Local
Inference, Efficient AI Serving
