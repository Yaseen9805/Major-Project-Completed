"""These tests call the real local Ollama models and the real Postgres
container (via docker-compose), same requirement as the rest of the
prototype -- no mocking of external services.
"""

from fastapi.testclient import TestClient

from api import app
from cache import clear_cache

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_query_rejects_empty_string():
    response = client.post("/query", json={"query": "   "})
    assert response.status_code == 400


def test_query_rejects_unknown_system():
    response = client.post("/query", json={"query": "hello", "system": "huge"})
    assert response.status_code == 400


def test_query_cache_hit_on_repeat():
    clear_cache()
    first = client.post("/query", json={"query": "What is the capital of Japan?"})
    second = client.post("/query", json={"query": "What is the capital of Japan?"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is True
    assert second.json()["latency_ms"] < first.json()["latency_ms"]
