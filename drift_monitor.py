"""Detects drift in incoming query patterns / router decisions (Module 5).

Compares the tier-assignment distribution of a recent window of logged
queries against an earlier reference window using a chi-squared test --
flags when current traffic looks statistically different from what the
router (or its training data) was built around, so the team knows to
consider retraining (train_router.py) before quality quietly degrades.

Run: python drift_monitor.py
"""

from collections import Counter

from scipy.stats import chisquare

import db

WINDOW_SIZE = 20
SIGNIFICANCE_LEVEL = 0.05
TIERS = ("small", "medium", "large")


def load_recent_tiers(limit: int) -> list[str]:
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tier_used FROM query_log
                WHERE cache_hit = false AND system = 'adaptive'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [r[0] for r in cur.fetchall()]


def main() -> None:
    recent = load_recent_tiers(WINDOW_SIZE)
    older = load_recent_tiers(WINDOW_SIZE * 2)[WINDOW_SIZE:]

    if len(recent) < WINDOW_SIZE or len(older) < WINDOW_SIZE // 2:
        print(
            f"Not enough logged history yet for a reliable drift check "
            f"(have {len(recent)} recent + {len(older)} reference rows). "
            f"This becomes meaningful once more real traffic accrues."
        )
        return

    recent_counts = Counter(recent)
    reference_counts = Counter(older)

    observed = [recent_counts.get(t, 0) for t in TIERS]
    reference_freq = [reference_counts.get(t, 0) for t in TIERS]
    reference_total = sum(reference_freq)

    if reference_total == 0:
        print("Reference window is empty. Skipping.")
        return

    expected = [max(f / reference_total * sum(observed), 1e-6) for f in reference_freq]
    stat, p_value = chisquare(observed, f_exp=expected)

    print(f"Recent tier distribution:    {dict(recent_counts)}")
    print(f"Reference tier distribution: {dict(reference_counts)}")
    print(f"Chi-squared statistic: {stat:.3f}, p-value: {p_value:.3f}")

    if p_value < SIGNIFICANCE_LEVEL:
        print(
            "DRIFT DETECTED: recent traffic looks statistically different from the "
            "reference window. Consider retraining the router (train_router.py)."
        )
    else:
        print("No significant drift detected.")


if __name__ == "__main__":
    main()
