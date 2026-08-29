# CostQual-Router — Q&A Prep Sheet

Prep sheet for defending the project (viva, hackathon judges, demo Q&A). Every answer is short,
simple, and matches what's actually in the code/docs — no answer here claims something we haven't
built. Where we genuinely don't use something, the answer says **"None — here's why."**

---

## 1. Tech stack questions

**Q: What's your tech stack, top to bottom?**
A: Ollama (runs local models) → Sentence-Transformers for embeddings → Qdrant (vector cache) +
PostgreSQL (structured logs) → a router (rule-based today, learned classifier in the full project)
→ FastAPI/Flask as the API layer → Prometheus/Grafana for monitoring → Docker + GitHub Actions for
packaging and deployment. Every piece is free and open-source.

**Q: Why Ollama instead of OpenAI/GPT APIs?**
A: Two reasons: (1) cost — the whole project is about cost efficiency, so paying per-token to a
third party undermines the pitch; (2) reproducibility and data privacy — nothing leaves our own
machine, so anyone can run it without an API key or sending data to an external company.

**Q: What embedding model do you use, and why that one?**
A: `all-MiniLM-L6-v2` from Sentence-Transformers. It's small (~80MB), runs fast on CPU with no GPU
needed, and is a standard, well-benchmarked choice for semantic similarity tasks like ours.

**Q: Why two databases (Postgres + Qdrant) instead of one?**
A: They do different jobs. Qdrant is built for one thing — "find the most similar vector to this
one" — which is what the semantic cache needs. Postgres is built for structured records you filter,
join, and aggregate — query logs, user accounts, usage stats for dashboards. Qdrant can't do
reporting well; Postgres can't do fast similarity search well. Two specialized tools beat one
general-purpose one here.

**Q: Could you have used just one database?**
A: Yes — `pgvector` is a Postgres extension that adds vector search into Postgres itself, so one
database could do both jobs. It's simpler to run (one moving part instead of two) but less scalable
and less purpose-built than Qdrant. Both are legitimate choices; we chose Qdrant for a more serious,
purpose-built cache.

**Q: What database will hold user accounts / API keys?**
A: PostgreSQL — same database as the query logs, since accounts are exactly the kind of structured,
relational data Postgres is designed for.

**Q: Is any part of this cloud-hosted?**
A: No — everything is self-hosted (Docker containers on our own machine/server). That's a deliberate
requirement, not a limitation: full reproducibility without needing anyone to pay for cloud infra.

**Q: What monitoring tools do you use and why those specifically?**
A: Prometheus (collects metrics over time) + Grafana (visualizes them on dashboards). Both are the
de facto free/open-source standard for this — widely used, well-documented, and self-hostable.

---

## 2. Algorithm questions

**Q: What machine learning algorithm powers the router?**
A: **Today: none.** The current router is hand-written rules (regex patterns + keyword lists in
`router.py`) — "if it's short and starts with 'what is', it's easy." No training, no ML involved.
**In the full 7-month project:** yes — a trained classifier (a small model like scikit-learn's
random forest or logistic regression) learns from logged (query, correct tier) examples instead of
hand-written rules.

**Q: What algorithm does the semantic cache use to find matches?**
A: Cosine similarity — a standard, well-known math formula for comparing how close two vectors
point in the same direction. It's not something we invented; it's the standard technique for
comparing embeddings. We didn't train anything here — we compare pretrained embeddings using this
formula, then take the closest match if it's above a similarity threshold (0.87 in the demo).

**Q: Did you train any model yourselves?**
A: **Not yet, in the demo.** All models used today (the 3 LLM tiers, the embedding model) are
pretrained and used as-is — we didn't fine-tune or train anything. The one thing we *will* train
ourselves, in the full project, is the router classifier — trained on our own logged usage data,
not a pretrained model.

**Q: Is there any deep learning / neural network involved?**
A: Indirectly, yes — the LLMs themselves (Ollama models) and the sentence-transformer embedding
model are both neural networks, but they're pretrained ones we call, not ones we built or trained.
The router we train ourselves (Month 4) is a lightweight classifier, not a deep neural network — it
doesn't need to be, since it's solving a much simpler classification problem than language
generation.

**Q: What's BERTScore and is it an algorithm you built?**
A: No — it's an existing, published metric (uses a pretrained BERT-style model to compare two texts
by meaning). We use it as an evaluation tool, not something we built ourselves.

**Q: Any algorithm for drift detection?**
A: A statistical comparison (planned for Month 5) that checks whether the distribution of incoming
queries or router decisions is changing significantly over time compared to a baseline period — a
standard drift-detection technique, not a custom-built one.

---

## 3. Final objective / final product questions

**Q: In one sentence, what does this project do?**
A: It sits between users and AI models, answers repeat questions instantly from memory, and sends
new questions to the cheapest model that can actually handle them — cutting AI serving cost and
latency without hurting answer quality.

**Q: What's the final deliverable at the end of 7 months?**
A: A running, always-on web service (not a script) — with a real API, persistent memory, a learned
router, live monitoring dashboards, login/security, and automated deployment — plus a written report
comparing it against a naive single-model baseline and our own earlier prototype.

**Q: What problem does this actually solve, in business terms?**
A: Wasted spend. Most systems send every question — trivial or complex — to the same expensive
model. This project routes effort to match difficulty and reuses answers instead of recomputing
them, which directly cuts inference cost and response time.

**Q: What are your current results (from the prototype)?**
A: On a 60-query benchmark: 35% reduction in estimated serving cost and a 23% semantic cache hit
rate, with answer quality preserved in most cases where a smaller model was used (verified via
LLM-based judging).

**Q: How is this different from just using a smaller model for everything?**
A: A smaller model for everything would be cheap but would fail on genuinely hard questions. This
system is adaptive — it uses the small model *only* when the question is actually simple, and
escalates to a bigger model when the question needs it, so you get savings without sacrificing
quality on hard queries.

**Q: Who is the end user of this system?**
A: Any team or application that wants to serve AI-generated answers cheaply and reliably — e.g., an
internal support chatbot, an FAQ assistant, or any product embedding an LLM where most queries are
simple/repetitive but a few genuinely need a stronger model.

**Q: Is this a product or a research project?**
A: Both, sequentially — it started as a research prototype (Month 0, proving the idea works), and
the 7-month plan turns it into a real, deployable product (persistent storage, security, monitoring,
CI/CD).

---

## 4. "Weird" / curveball questions

**Q: What happens if the router sends a hard question to the small model by mistake?**
A: That's expected occasionally — it's exactly what the quality checker is for. It continuously
compares small/medium-tier answers against what the large model would've said, so if the small tier
is underperforming on certain question types, we'll see it in the data and can retrain the router or
raise its threshold for that pattern.

**Q: What if two completely different questions accidentally get treated as the same cached
answer (a false cache hit)?**
A: This is controlled by the similarity threshold (0.87 cosine similarity in the demo) — high enough
that only genuinely close-meaning questions match. If false hits show up in practice, the fix is
raising the threshold (stricter matching) or improving the embedding model; it's a tunable knob, not
a fundamental flaw.

**Q: What if the system's local models produce a wrong or hallucinated answer?**
A: Same failure mode any LLM system has — this project doesn't eliminate hallucination, it optimizes
*cost and routing*. The quality checker catches cases where a smaller model's answer diverges
significantly from the larger model's, which is a proxy for catching this, but it's not a full
hallucination-detection system.

**Q: Why does the cache expire after 24 hours instead of keeping answers forever?**
A: Because some answers go stale (e.g., "find me a job," anything time-sensitive), while others
never change (e.g., "boiling point of water"). Rather than trying to classify which is which — a
much harder problem — we apply one flat, simple rule: every cached answer expires 24 hours after it
was created, individually (not a scheduled wipe of the whole cache). It's a deliberately simple,
defensible tradeoff: slightly more re-computation on stable facts, in exchange for guaranteed
freshness on volatile ones.

**Q: Does clearing an entry after 24 hours mean you wipe the whole database every day?**
A: No — each entry has its own timestamp from when it was created, and expires independently on its
own 24-hour clock. A question cached this morning and one cached last week don't expire at the same
moment; they each expire 24 hours after *their own* creation time.

**Q: What happens if Ollama or the vector database goes down?**
A: Not handled in the current prototype — this is exactly the kind of production-readiness gap the
7-month plan closes (health checks, monitoring, and CI/CD in Months 5–6 are meant to catch and
surface failures like this rather than fail silently).

**Q: Could someone abuse the cache to get another user's cached answer?**
A: Not in the current design if the cache is scoped per-deployment rather than per-user; this
becomes a real question once auth (Month 6) is added — cache scoping/isolation per user or team
would need to be a deliberate design decision at that point, not an afterthought.

**Q: How do you know your 7-month timeline is realistic?**
A: It's sequenced so each month only depends on what's already been built — infrastructure first
(Month 1), then persistence (Month 2), then real routing and data collection (Month 3) *before* the
learned router (Month 4) needs that data, then quality/monitoring (Month 5), then security/CI-CD
(Month 6), leaving Month 7 purely for evaluation and the report — no month depends on something from
a later month.

**Q: What's the single biggest risk to this project?**
A: Probably the learned router underperforming the simple rule-based one — if there isn't enough
real usage data collected by Month 3–4, the trained classifier could end up worse than the rules it's
replacing. That's why the plan keeps the rule-based router as a fallback/comparison baseline rather
than deleting it.

**Q: If everything is free and open-source, what exactly is "your" contribution?**
A: Not the individual pieces (Ollama, Qdrant, Postgres all exist already) — the contribution is the
*system design*: combining semantic caching with complexity-aware routing into one adaptive pipeline,
proving it actually saves cost without hurting quality, and building the production infrastructure
(learned routing, monitoring, quality assurance) around that idea.
