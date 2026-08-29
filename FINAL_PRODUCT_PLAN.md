# CostQual-Router — The Real Project, Explained Simply

This document is for the whole team. It explains the **final 7-month project** (not the small demo
we already built) in plain language, end to end, so everyone can explain it and answer questions
about it without re-reading code. The demo (`README.md`, `ARCHITECTURE.md`) is a 5-day proof that
the _idea_ works. This document is about the _real thing_ we're building afterward.

---

## 1. The problem, in one paragraph

Every time someone asks an AI chatbot a question — even something trivial like "what's the capital
of France?" — most systems send it to the same big, expensive, slow model they'd use for "write me
a full business plan." That's like calling a specialist surgeon to put on a Band-Aid. It works, but
it's wasteful: wasted money, wasted time, wasted compute. And if two people ask basically the same
question five minutes apart, the system re-computes the answer from scratch both times, even though
nothing changed.

## 2. The idea, in one paragraph

Build a smart middle-layer that sits between the user and the AI models. Before answering anything,
it asks two questions:

1. **"Have I basically answered this before?"** — If yes, hand back the saved answer instantly.
   No model call needed at all.
2. **"How hard is this question, really?"** — If no cached answer exists, figure out whether this
   needs a tiny model, a medium model, or the big expensive model — and only use the big one when
   the question actually deserves it.

Think of it like a hospital receptionist (the router) who looks at your symptoms and decides: "you
need a nurse," "you need a general doctor," or "you need the specialist" — instead of every patient
automatically seeing the most expensive specialist regardless of what's wrong with them. And a
notice board (the cache) that says "someone already asked this exact question this morning, here's
the answer" so the receptionist doesn't even need to triage it again.

## 3. Walking through one question, step by step

Say a user types: _"What's the boiling point of water?"_

1. The question hits our **API** (the front door of the system).
2. The system checks: **"has anyone asked something like this before?"** — it converts the question
   into a list of numbers (an "embedding," basically a fingerprint of _meaning_, not exact words),
   and compares it against fingerprints of past questions.
   - **If a close match exists** → return that old answer immediately. Done. Cheap and instant.
   - **If not** → go to step 3.
3. The system decides **how hard the question is**. "What's the boiling point of water?" is short
   and simple → send it to the **small, cheap model**.
4. The small model answers. The system **saves this new question + answer** to memory, so if
   someone asks it again (or asks it in different words), step 2 will catch it next time.
5. The answer, plus some bookkeeping info (which model handled it, was it a cache hit, how much it
   "cost," how long it took), goes back to the user.

If instead someone asked _"Explain why the sky is blue and compare it to why sunsets are red"_ —
that's long and has reasoning keywords ("explain," "compare") — so the system sends it to the
**big model** instead, because a tiny model would likely get it wrong or give a shallow answer.

That's the entire idea. Everything else in the project exists to make this reliable, measurable,
and safe to run for real users instead of just a demo script.

## 4. The building blocks (modules), explained simply

| Module                          | What it is, in plain words                                                                                                                                                                                                                                                                                                                     |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **API / Front door**            | The address people (or other apps) send questions to. Checks who's allowed in (see Auth) and hands the question to the rest of the system.                                                                                                                                                                                                     |
| **Auth (login/API keys)**       | Makes sure only approved users/teams can use the system, and lets us track who's using how much. Like a keycard system.                                                                                                                                                                                                                        |
| **Semantic Cache**              | The system's memory of past questions and answers, kept even after a restart (unlike the demo, which forgets everything when you close it).                                                                                                                                                                                                    |
| **Router (the decision-maker)** | Looks at a new question and decides: small, medium, or big model. In the demo this was a simple checklist of rules ("if it starts with 'what is', it's easy"). In the real project, it's a small trained model that has _learned_ from experience which questions actually need which tier — smarter and more accurate than a fixed checklist. |
| **The three models themselves** | Three actual AI models of different sizes running on our own machines — small (fast, cheap, good at easy stuff), medium, and large (slow, expensive, good at hard reasoning). All free, open-source, run locally — we don't pay OpenAI or anyone else per question.                                                                            |
| **Quality checker**             | Constantly spot-checks: "did the cheap model's answer actually hold up compared to what the big model would've said?" If quality starts slipping, we'll know.                                                                                                                                                                                  |
| **Logbook (database)**          | Records every question asked, which model answered it, whether it was a cache hit, how long it took, and what it "cost." This is both our audit trail and the training data for making the router smarter over time.                                                                                                                           |
| **Dashboards (monitoring)**     | Live charts showing the system's health — how much money/time we're saving right now, how often the cache is hit, whether anything is broken.                                                                                                                                                                                                  |
| **Deployment pipeline (CI/CD)** | Every time we improve the code, it's automatically tested and safely rolled out, instead of someone manually copying files onto a server and hoping nothing breaks.                                                                                                                                                                            |

## 5. The "algorithms" — explained without the math

- **Turning text into a fingerprint (embedding)**: We use a small pretrained AI model whose only
  job is to read a sentence and output a list of numbers that captures its _meaning_. Two
  differently-worded questions that mean the same thing get very similar number-lists. This is how
  we detect "is this basically the same question?" without needing exact matching text.

- **Comparing fingerprints (similarity search)**: Once we have thousands of past questions stored,
  we can't compare a new question against every single one one-by-one forever — it gets slow. So we
  use a **vector database** (see below) that's specifically built to instantly find "which of these
  10,000 stored fingerprints is most similar to this new one?"

- **Deciding the model tier (the learned router)**: Instead of a fixed checklist of rules, we
  collect real examples of "this question, this difficulty" and train a small classifier model on
  them — much like teaching by example rather than by rulebook. Over time it gets better at
  predicting the right tier than any hand-written rule could.

- **Checking if an answer is "good enough" (BERTScore)**: A method that compares two pieces of text
  by meaning (not exact wording) and produces a similarity score — used to check "did the cheap
  model's answer mean roughly the same thing as the expensive model's answer?" This replaces
  eyeballing 10 examples by hand with a repeatable, automatic check run continuously.

## 6. Do we need a database? Yes — actually two, doing two different jobs

**Short answer: yes.** The demo didn't need one because everything lived in memory and vanished
when the script ended, and results just got dumped to a CSV file. A real system serving live users
needs to _remember things permanently_ and _look things up fast_. That means a database — actually
two, because they store fundamentally different kinds of data:

1. **PostgreSQL** (relational database) — for everything that looks like rows/tables:
   - every logged query (who asked, when, what tier, cache hit or not, latency, cost)
   - user accounts and API keys
   - usage stats for dashboards
     This is the "spreadsheet-like" data: structured, and we want to run reports on it ("average cost
     per day," "top users," etc.).

2. **Qdrant** (vector database) — specifically for storing and searching the _fingerprints_
   (embeddings) from the semantic cache. A normal database is bad at answering "which of these
   10,000 number-lists is most similar to this new number-list?" — that's a specialized search
   problem, and Qdrant is built exactly for it (fast approximate similarity search at scale).

Both are **free and open-source**, and both run **self-hosted** (on our own machine/server via
Docker) — no paid cloud database service, keeping with the project's "fully reproducible, no paid
third-party dependency" requirement from the abstract.

_(Why not just one database for both? You technically could bolt vector search onto Postgres with
an extension like `pgvector`, and that's a legitimate simpler alternative if we want to reduce
moving parts — one database instead of two. Worth a team decision: Qdrant is more scalable and
purpose-built; Postgres+pgvector is simpler to run and enough for our expected scale. Either is a
reasonable, defensible choice — just be able to explain why we picked one.)_

## 7. The end product

A **running web service**, not a script. Concretely:

- Anyone on the team (or a demo user) can send a question to an API and get an answer back, along
  with info like "this came from cache" or "this used the medium model."
- Behind the scenes, the system is constantly caching, routing, logging, and checking its own
  quality — with zero manual intervention.
- There's a live dashboard showing cost savings, speed, and cache hit rates in real time (not a
  static report generated after the fact).
- The whole thing is packaged so it can be started with one command (Docker) and updates itself
  safely through an automated pipeline whenever we push code changes.
- It's built entirely from free, open-source, self-hosted pieces (Ollama for models, Qdrant +
  Postgres for storage, Prometheus/Grafana for monitoring, GitHub Actions for deployment) — so
  anyone can reproduce it without needing a paid API key from OpenAI, Anthropic, etc.
- The deliverable also includes a **written report** comparing this final system's real, live
  performance against both (a) the naive single-model baseline and (b) our own earlier 5-day demo —
  showing the idea holds up under real, unpredictable usage, not just a fixed 60-question test.

## 8. Common questions, answered

**Q: Why not just always use the biggest, smartest model? Wouldn't that give the best answers?**
A: It would give good answers, but at maximum cost and latency for _every_ question, including
trivial ones. The whole point is: most questions don't need that much "brainpower," so we save
resources by matching effort to difficulty — like not hiring a lawyer to read a parking ticket.

**Q: Why not just cache everything with exact text matching, why "semantic" (meaning-based)?**
A: Because real users rarely type the exact same sentence twice. "What's the boiling point of
water?" and "At what temperature does water boil?" are the same question worded differently. Exact
matching would miss that; semantic matching catches it.

**Q: Isn't a rule-based router (if/else checklist) good enough?**
A: It's a fine starting point (that's what our demo used), but it's brittle — someone has to
manually think of every pattern. A learned router improves automatically from real examples and
handles cases the original rule-writer never thought of.

**Q: Why self-hosted / open-source only, why not just use a paid API like GPT?**
A: Two reasons — (1) cost control is the whole point of the project, so paying per-token to a third
party undermines the pitch, and (2) reproducibility — anyone should be able to run this project
without needing to pay anyone or share private data with an external company.

**Q: What happens if the router makes a wrong call and sends a hard question to the small model?**
A: That's exactly what the quality checker (BERTScore) is for — it continuously measures this, so
if the small tier is under-performing on certain question types, we'll see it in the data and can
retrain the router or adjust thresholds.

**Q: What's actually different between the demo and this final project?**
A: The demo proved the _idea_ works on a fixed, offline, 60-question test with a simple rule-based
router and an in-memory cache that forgets everything on restart. The final project turns that into
a real, always-on service: permanent storage (databases), a smarter learned router instead of fixed
rules, rigorous ongoing quality checks instead of a 10-question spot check, monitoring dashboards,
login/security, and automated deployment — the difference between "a script that proves a point"
and "a system someone could actually rely on."

## 9. Seven-month roadmap

Each month builds on the last: infrastructure first, then the "smart" pieces (real models, learned
router, persistent cache), then hardening (quality, monitoring, security), then packaging it all
into something reproducible and defensible in front of an audience. The demo (Month 0, already
done) is the foundation everything below extends.

| Month        | Theme                                             | What we ship                                                                                                                                                                                                                                                                                                             |
| ------------ | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **0 (done)** | Proof of concept                                  | Rule-based router, in-memory cache, 3 simulated model tiers, 60-query benchmark, CSV report. This is the `README.md` / `ARCHITECTURE.md` demo already in the repo.                                                                                                                                                       |
| **1**        | Real infrastructure foundations                   | Stand up Ollama locally with actual small/medium/large open-source models (replacing simulated tiers). Stand up Postgres + Qdrant via Docker Compose. Design the logbook schema (queries, tiers, cache hits, latency, cost). Wrap the existing demo logic in a real API (FastAPI/Flask) so it's a service, not a script. |
| **2**        | Persistent semantic cache                         | Replace the in-memory cache with Qdrant-backed storage: embed queries, store/query vectors, tune similarity thresholds against real (not simulated) traffic. Confirm cache hits survive a restart. Log every request (hit/miss, tier, latency) into Postgres.                                                            |
| **3**        | Three real model tiers + baseline data collection | Wire up all three real Ollama model tiers end-to-end through the API. Start collecting labeled (query, ideal tier) examples from real usage and synthetic traffic — this becomes the training set for Month 4's learned router. Keep the old rule-based router as a fallback/comparison baseline.                        |
| **4**        | Learned router                                    | Train a small classifier on the collected (query → complexity tier) data to replace the rule-based checklist. Evaluate it against the rule-based baseline on held-out queries. Integrate it behind a feature flag so we can A/B it against the old router before fully cutting over.                                     |
| **5**        | Quality & drift monitoring                        | Add the BERTScore-based quality checker comparing small/medium-tier answers against large-tier answers on a sample of live traffic. Add drift detection on incoming query distribution and router decisions. Build the first pass of Grafana/Prometheus dashboards (cost saved, cache hit rate, latency, quality trend). |
| **6**        | Security, auth & CI/CD                            | Add API-key/login auth and per-user usage tracking. Set up GitHub Actions for automated testing and deployment (build → test → deploy on push). Load-test the service under concurrent/unpredictable traffic (not just the fixed 60-query set) to validate it holds up as a real service.                                |
| **7**        | Hardening, evaluation & report                    | Fix issues found under load/security review. Run the full live-system benchmark: adaptive system vs. naive single-model baseline vs. the original Month-0 demo. Finalize dashboards, package everything for one-command Docker startup, and write the final report comparing all three, plus a live demo walkthrough.    |

**Notes on sequencing:**

- Auth and CI/CD are pushed to Month 6 deliberately — they matter for a "real service" but don't
  block validating the core cost/quality hypothesis, which is the project's main claim.
- The learned router (Month 4) depends on Month 3's real-traffic data collection — this is why real
  models come online in Month 3 before the router is retrained, not after.
- Month 7 is intentionally light on new features and heavy on evaluation/report writing, since the
  deliverable includes a written comparison report (see Section 7), not just working code.
