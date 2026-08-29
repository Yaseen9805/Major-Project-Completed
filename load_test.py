"""Concurrent load test against the live API (Module 6).

Fires a batch of concurrent, randomly-ordered requests (a mix of repeats,
paraphrases, and unique queries from test_queries.json) at the API to
validate throughput and stability under real, unpredictable traffic --
unlike run_benchmark.py's fixed sequential pass.

Requires the API running: uvicorn api:app --port 8000
Run: python load_test.py [--workers N] [--requests N]
"""

import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import db

API_URL = "http://127.0.0.1:8000/query"
QUERIES_PATH = "test_queries.json"


def fire_one(query: str, headers: dict) -> dict:
    start = time.perf_counter()
    try:
        response = requests.post(API_URL, json={"query": query}, headers=headers, timeout=240)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": response.status_code == 200, "status": response.status_code, "elapsed_ms": elapsed_ms}
    except requests.exceptions.RequestException as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "status": None, "elapsed_ms": elapsed_ms, "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--requests", type=int, default=40)
    args = parser.parse_args()

    with open(QUERIES_PATH, encoding="utf-8") as f:
        pool = [q["query"] for q in json.load(f)]

    queries = [random.choice(pool) for _ in range(args.requests)]
    headers = {"X-API-Key": db.create_api_key("load_test")}

    print(f"Firing {args.requests} requests with {args.workers} concurrent workers...")
    start = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(fire_one, q, headers) for q in queries]
        for future in as_completed(futures):
            results.append(future.result())
    total_elapsed = time.perf_counter() - start

    successes = [r for r in results if r["ok"]]
    failures = [r for r in results if not r["ok"]]
    latencies = sorted(r["elapsed_ms"] for r in successes)

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        idx = min(int(len(latencies) * p), len(latencies) - 1)
        return latencies[idx]

    print(f"\nTotal wall time: {total_elapsed:.1f}s")
    print(f"Success: {len(successes)}/{len(results)} ({len(successes) / len(results):.0%})")
    print(f"Throughput: {len(results) / total_elapsed:.2f} req/s")
    if latencies:
        print(f"Latency (ms) -- p50: {pct(0.5):.0f}  p95: {pct(0.95):.0f}  max: {latencies[-1]:.0f}")
    if failures:
        print(f"\n{len(failures)} failures, sample errors:")
        for r in failures[:5]:
            print(f"  status={r['status']} error={r.get('error')}")


if __name__ == "__main__":
    main()
