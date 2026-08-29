"""Postgres-backed telemetry log (Module 1).

Thin wrapper around psycopg2 -- no ORM, matching the rest of the prototype's
style. One row is written per handled query; this is both the audit trail
and the future training data for the learned router (Module 4).
"""

import secrets

import psycopg2

from config import POSTGRES_DSN


def get_connection():
    return psycopg2.connect(POSTGRES_DSN)


def log_query(
    query_text: str,
    system: str,
    tier_used: str,
    cache_hit: bool,
    latency_ms: float,
    estimated_cost: float,
    answer: str,
    api_key_owner: str | None = None,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_log
                    (query_text, system, tier_used, cache_hit, latency_ms, estimated_cost,
                     answer, api_key_owner)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    query_text,
                    system,
                    tier_used,
                    cache_hit,
                    latency_ms,
                    estimated_cost,
                    answer,
                    api_key_owner,
                ),
            )
        conn.commit()


def create_api_key(owner: str) -> str:
    key = secrets.token_urlsafe(24)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO api_keys (key, owner) VALUES (%s, %s)", (key, owner))
        conn.commit()
    return key


def get_api_key_owner(key: str) -> str | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT owner FROM api_keys WHERE key = %s", (key,))
            row = cur.fetchone()
    return row[0] if row else None


def is_healthy() -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except psycopg2.OperationalError:
        return False
