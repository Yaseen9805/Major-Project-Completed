"""CostQual-Router API.

Wraps the adaptive/baseline handlers in a stateless HTTP service, with
API-key auth, per-request logging to Postgres, and Prometheus metrics.

Run with: uvicorn api:app --reload
"""

from fastapi import Depends, FastAPI, Header, HTTPException, Response
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


def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Auth dependency for /query (Module 6). /health and /metrics stay
    open, matching normal practice for infra/monitoring endpoints."""
    owner = db.get_api_key_owner(x_api_key)
    if owner is None:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return owner


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
def query(request: QueryRequest, owner: str = Depends(require_api_key)) -> QueryResponse:
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
        api_key_owner=owner,
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

    return QueryResponse(**result)
