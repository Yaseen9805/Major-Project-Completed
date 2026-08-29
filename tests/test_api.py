"""These tests call the real local Ollama models and the real Postgres
container (via docker-compose), same requirement as the rest of the
prototype -- no mocking of external services.
"""

from fastapi.testclient import TestClient

import db
from api import app
from cache import clear_cache

client = TestClient(app)


def _fresh_api_key() -> str:
    return db.create_api_key("pytest")


AUTH_HEADERS = {"X-API-Key": _fresh_api_key()}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_query_requires_api_key():
    response = client.post("/query", json={"query": "hello"})
    assert response.status_code == 422  # missing required header


def test_query_rejects_invalid_api_key():
    response = client.post(
        "/query", json={"query": "hello"}, headers={"X-API-Key": "not-a-real-key"}
    )
    assert response.status_code == 401


def test_query_rejects_empty_string():
    response = client.post("/query", json={"query": "   "}, headers=AUTH_HEADERS)
    assert response.status_code == 400


def test_query_rejects_unknown_system():
    response = client.post(
        "/query", json={"query": "hello", "system": "huge"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 400


def test_query_cache_hit_on_repeat():
    clear_cache()
    first = client.post(
        "/query", json={"query": "What is the capital of Japan?"}, headers=AUTH_HEADERS
    )
    second = client.post(
        "/query", json={"query": "What is the capital of Japan?"}, headers=AUTH_HEADERS
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is True
    assert second.json()["latency_ms"] < first.json()["latency_ms"]


def test_query_usage_is_attributed_to_the_key_owner():
    owner = "pytest-attribution-test"
    key = db.create_api_key(owner)

    response = client.post(
        "/query", json={"query": "What is the capital of Portugal?"}, headers={"X-API-Key": key}
    )
    assert response.status_code == 200

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT api_key_owner FROM query_log WHERE query_text = %s ORDER BY id DESC LIMIT 1",
                ("What is the capital of Portugal?",),
            )
            row = cur.fetchone()
    assert row is not None
    assert row[0] == owner
