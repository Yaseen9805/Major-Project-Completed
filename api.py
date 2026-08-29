"""CostQual-Router API (Module 1).

Wraps the existing adaptive/baseline handlers in a stateless HTTP service and
logs every request to Postgres. Run with:

    uvicorn api:app --reload

Cache persistence (Qdrant) and the learned router are later modules --
this module's job is only the service shell + real infrastructure.
"""

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from qdrant_client import QdrantClient

from adaptive import ask_adaptive
from baseline import ask_baseline
from config import QDRANT_URL
import db

app = FastAPI(title="CostQual-Router API", version="0.1.0")

QUERY_COUNT = Counter(
    "costqual_queries_total", "Total queries handled", ["system", "tier_used", "cache_hit"]
)
QUERY_LATENCY = Histogram(
    "costqual_query_latency_ms", "Query latency in milliseconds", ["system", "tier_used"]
)
QUERY_COST = Counter(
    "costqual_estimated_cost_total", "Cumulative estimated cost", ["system", "tier_used"]
)


class QueryRequest(BaseModel):
    query: str
    system: str = "adaptive"  # "adaptive" or "baseline"


class QueryResponse(BaseModel):
    answer: str
    tier_used: str
    cache_hit: bool
    latency_ms: float
    estimated_cost: float


@app.get("/health")
def health() -> dict:
    try:
        QdrantClient(url=QDRANT_URL).get_collections()
        qdrant_status = "up"
    except Exception:
        qdrant_status = "down"

    return {
        "status": "ok",
        "database": "up" if db.is_healthy() else "down",
        "vector_cache": qdrant_status,
    }


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    if request.system == "baseline":
        result = ask_baseline(request.query)
    elif request.system == "adaptive":
        result = ask_adaptive(request.query)
    else:
        raise HTTPException(status_code=400, detail="system must be 'adaptive' or 'baseline'")

    db.log_query(
        query_text=request.query,
        system=request.system,
        tier_used=result["tier_used"],
        cache_hit=result["cache_hit"],
        latency_ms=result["latency_ms"],
        estimated_cost=result["estimated_cost"],
        answer=result["answer"],
    )

    QUERY_COUNT.labels(
        system=request.system, tier_used=result["tier_used"], cache_hit=str(result["cache_hit"])
    ).inc()
    QUERY_LATENCY.labels(system=request.system, tier_used=result["tier_used"]).observe(
        result["latency_ms"]
    )
    QUERY_COST.labels(system=request.system, tier_used=result["tier_used"]).inc(
        result["estimated_cost"]
    )

    return QueryResponse(
        answer=result["answer"],
        tier_used=result["tier_used"],
        cache_hit=result["cache_hit"],
        latency_ms=result["latency_ms"],
        estimated_cost=result["estimated_cost"],
    )
