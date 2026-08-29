"""Replays test_queries.json through the live API to seed real usage logs
in Postgres -- bootstraps training data for the learned router (Module 4).

Requires the API running: uvicorn api:app --port 8000
Run: python seed_traffic.py
"""

import json

import requests

API_URL = "http://127.0.0.1:8000/query"
QUERIES_PATH = "test_queries.json"


def main() -> None:
    with open(QUERIES_PATH, encoding="utf-8") as f:
        queries = json.load(f)

    for i, q in enumerate(queries, start=1):
        response = requests.post(
            API_URL, json={"query": q["query"], "system": "adaptive"}, timeout=240
        )
        response.raise_for_status()
        result = response.json()
        print(
            f"[{i}/{len(queries)}] tier={result['tier_used']:<7} "
            f"cache_hit={result['cache_hit']!s:<5} {q['query'][:60]}"
        )


if __name__ == "__main__":
    main()
