"""Postgres-backed telemetry log (Module 1).

Thin wrapper around psycopg2 -- no ORM, matching the rest of the prototype's
style. One row is written per handled query; this is both the audit trail
and the future training data for the learned router (Module 4).
"""

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
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_log
                    (query_text, system, tier_used, cache_hit, latency_ms, estimated_cost, answer)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (query_text, system, tier_used, cache_hit, latency_ms, estimated_cost, answer),
            )
        conn.commit()


def is_healthy() -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except psycopg2.OperationalError:
        return False
