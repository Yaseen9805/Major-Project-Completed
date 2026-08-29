"""Standalone cleanup job for expired cache entries (Module 2).

Deletes entries whose individual 24h TTL has passed. Freshness is already
enforced at lookup time (check_cache ignores stale entries), so this only
matters for storage hygiene -- run it periodically (cron / Task Scheduler),
not on every request.

Run: python cache_reaper.py
"""

from cache import purge_expired_cache_entries


def main() -> None:
    removed = purge_expired_cache_entries()
    print(f"Purged {removed} expired cache entr{'y' if removed == 1 else 'ies'}.")


if __name__ == "__main__":
    main()
