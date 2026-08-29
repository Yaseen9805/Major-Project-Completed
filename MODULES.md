# CostQual-Router — System Modules

Seven implementation modules take CostQual-Router from proof-of-concept prototype to a
production-grade, adaptive LLM-serving system. Each module is scoped to depend only on artifacts
produced by prior modules — no forward dependencies.

## Modules

| # | Module | Objective | Key Techniques |
|---|---|---|---|
| 1 | **Infrastructure Setup** | Stand up the core services everything else runs on | Local models via Ollama (small/medium/large), PostgreSQL + Qdrant in Docker, database schema for logging, demo script turned into a proper API |
| 2 | **Persistent Semantic Cache** | Replace the temporary in-memory cache with one that survives restarts and scales | Move cache into Qdrant, similarity search stays cosine-based, each entry auto-expires 24h after it's created, periodic cleanup of expired entries |
| 3 | **Real Model Tiers & Data Collection** | Get all three model tiers genuinely working and start logging real usage | Fix the tier setup (currently medium/large share one model), log every query + routing decision, keep the rule-based router as a fallback |
| 4 | **Learned Router** | Replace hand-written routing rules with a trained model | Extract features from queries, train a classifier (scikit-learn) on logged data, roll it out gradually alongside the old router before fully switching |
| 5 | **Quality & Monitoring** | Confirm cost savings aren't hurting answer quality, and catch issues early | BERTScore checks comparing smaller-model answers to the large model, alerts if query patterns shift a lot, live dashboards via Prometheus + Grafana |
| 6 | **Security & Automated Deployment** | Make the system production-safe and remove manual deployment steps | API-key login with per-user usage tracking, automated testing/deployment via GitHub Actions, load testing under real, unpredictable traffic |
| 7 | **Final Testing & Report** | Wrap up with thorough evaluation and documentation | Fix issues found during testing, compare adaptive system vs. baseline vs. original prototype, one-command Docker setup, final written report |

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
