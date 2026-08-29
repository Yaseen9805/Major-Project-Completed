"""Continuous quality monitoring via BERTScore (Module 5).

Replaces quality_check.py's ad hoc LLM-as-judge spot check (10 examples,
one-off) with a proper automated metric: BERTScore compares each adaptive
answer against the baseline (large-model) answer by semantic similarity,
not exact wording or an extra LLM call. Run this periodically -- like
cache_reaper.py -- instead of a one-off audit.

Run: python quality_monitor.py
"""

import csv

from bert_score import score

RESULTS_PATH = "benchmark_results.csv"
OUTPUT_PATH = "quality_monitor_results.csv"
F1_PASS_THRESHOLD = 0.85


def load_pairs() -> list[dict]:
    with open(RESULTS_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_id = {}
    for row in rows:
        by_id.setdefault(row["query_id"], {})[row["system"]] = row

    pairs = []
    for query_id, systems in by_id.items():
        baseline = systems.get("baseline")
        adaptive = systems.get("adaptive")
        if not baseline or not adaptive:
            continue
        if adaptive["cache_hit"].strip().lower() == "true":
            continue
        if adaptive["tier_used"] == "large":
            continue  # nothing to compare -- large tier IS the reference
        pairs.append(
            {
                "query_id": query_id,
                "query": baseline["query"],
                "tier_used": adaptive["tier_used"],
                "reference_answer": baseline["answer"],
                "candidate_answer": adaptive["answer"],
            }
        )
    return pairs


def main() -> None:
    pairs = load_pairs()
    print(f"Scoring {len(pairs)} adaptive answers against baseline via BERTScore...")

    if not pairs:
        print("Nothing to score.")
        return

    candidates = [p["candidate_answer"] for p in pairs]
    references = [p["reference_answer"] for p in pairs]
    _, _, f1_scores = score(candidates, references, lang="en", verbose=False)

    results = []
    for pair, f1 in zip(pairs, f1_scores.tolist()):
        results.append(
            {
                "query_id": pair["query_id"],
                "query": pair["query"],
                "tier_used": pair["tier_used"],
                "bertscore_f1": round(f1, 4),
                "pass": f1 >= F1_PASS_THRESHOLD,
            }
        )

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["query_id", "query", "tier_used", "bertscore_f1", "pass"]
        )
        writer.writeheader()
        writer.writerows(results)

    avg_f1 = sum(r["bertscore_f1"] for r in results) / len(results)
    pass_rate = sum(r["pass"] for r in results) / len(results)
    print(f"Average BERTScore F1: {avg_f1:.3f}")
    print(f"Pass rate (F1 >= {F1_PASS_THRESHOLD}): {pass_rate:.0%} ({len(results)} scored)")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
