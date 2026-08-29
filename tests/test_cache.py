"""These tests hit the real local Qdrant container (via docker-compose).
Each test uses its own throwaway collection so runs stay isolated
regardless of what's in the persistent default cache.
"""

import time
import uuid

from cache import SemanticCache


def fresh_cache(**kwargs) -> SemanticCache:
    return SemanticCache(collection_name=f"test_{uuid.uuid4().hex}", **kwargs)


def test_hit_for_near_duplicate_paraphrase():
    cache = fresh_cache(threshold=0.8)
    cache.add("What is the capital of France?", "Paris", "small")

    result = cache.check("Can you tell me France's capital city?")

    assert result is not None
    assert result["answer"] == "Paris"


def test_miss_for_unrelated_query():
    cache = fresh_cache(threshold=0.87)
    cache.add("What is the capital of France?", "Paris", "small")

    result = cache.check("What is the airspeed velocity of an unladen swallow?")

    assert result is None


def test_miss_on_empty_cache():
    cache = fresh_cache()
    assert cache.check("Anything at all?") is None


def test_add_increases_cache_size():
    cache = fresh_cache()
    assert len(cache) == 0
    cache.add("What is 2+2?", "4", "small")
    assert len(cache) == 1


def test_entry_survives_a_reconnect():
    """Persistence check: a second client pointed at the same collection
    name sees data written by the first -- proves this isn't in-memory."""
    name = f"test_{uuid.uuid4().hex}"
    writer = SemanticCache(collection_name=name)
    writer.add("What is the speed of light?", "About 300,000 km/s", "small")

    reader = SemanticCache(collection_name=name)
    result = reader.check("What is the speed of light?")

    assert result is not None
    assert result["answer"] == "About 300,000 km/s"


def test_concurrent_first_embed_calls_do_not_race():
    """Regression test for a real bug load_test.py found under concurrency
    (Module 6): concurrent first calls to embed() raced on lazy model init
    and crashed with 'Cannot copy out of meta tensor'."""
    import threading

    import cache

    cache._model = None  # force a cold lazy-init race
    errors = []

    def worker():
        try:
            cache.embed("some query text")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


def test_purge_expired_removes_only_stale_entries():
    cache = fresh_cache(ttl_seconds=1)
    cache.add("This entry will expire", "answer A", "small")
    time.sleep(1.5)
    cache.add("This entry is fresh", "answer B", "small")

    removed = cache.purge_expired()

    assert removed == 1
    assert len(cache) == 1
    assert cache.check("This entry is fresh") is not None
