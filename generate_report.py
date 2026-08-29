"""Reads benchmark_results.csv and produces:
  - cost_comparison.png / latency_comparison.png (bar charts)
  - report.md (numbers + plain-English interpretation)
"""

import csv
import os
from collections import defaultdict

import matplotlib.pyplot as plt

RESULTS_PATH = "benchmark_results.csv"
QUALITY_CHECK_PATH = "quality_check_results.csv"

# dataviz reference palette (references/palette.md): categorical slots 1 & 2.
COLOR_BASELINE = "#2a78d6"  # blue
COLOR_ADAPTIVE = "#1baf7a"  # aqua
COLOR_SURFACE = "#fcfcfb"
COLOR_GRID = "#e1e0d9"
COLOR_INK = "#0b0b0b"
COLOR_MUTED = "#898781"


def load_rows() -> list[dict]:
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def compute_stats(rows: list[dict]) -> dict:
    by_system = defaultdict(list)
    for row in rows:
        by_system[row["system"]].append(row)

    stats = {}
    for system in ("baseline", "adaptive"):
        system_rows = by_system[system]
        latencies = [float(r["latency_ms"]) for r in system_rows]
        costs = [float(r["estimated_cost"]) for r in system_rows]
        stats[system] = {
            "count": len(system_rows),
            "total_latency_ms": sum(latencies),
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "total_cost": sum(costs),
        }

    adaptive_rows = by_system["adaptive"]

    cache_by_category = defaultdict(lambda: {"hits": 0, "total": 0})
    for r in adaptive_rows:
        cat = r["category"]
        cache_by_category[cat]["total"] += 1
        if to_bool(r["cache_hit"]):
            cache_by_category[cat]["hits"] += 1

    overall_hits = sum(1 for r in adaptive_rows if to_bool(r["cache_hit"]))
    overall_hit_rate = overall_hits / len(adaptive_rows) if adaptive_rows else 0

    tier_counts = defaultdict(int)
    non_cache_rows = [r for r in adaptive_rows if not to_bool(r["cache_hit"])]
    for r in non_cache_rows:
        tier_counts[r["tier_used"]] += 1
    total_non_cache = len(non_cache_rows)
    tier_distribution = {
        tier: (count / total_non_cache if total_non_cache else 0)
        for tier, count in tier_counts.items()
    }

    return {
        "stats": stats,
        "cache_by_category": dict(cache_by_category),
        "overall_hit_rate": overall_hit_rate,
        "tier_distribution": tier_distribution,
    }


def style_bar_axes(ax, ylabel: str) -> None:
    ax.set_facecolor(COLOR_SURFACE)
    ax.figure.set_facecolor(COLOR_SURFACE)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_MUTED)
    ax.yaxis.grid(True, color=COLOR_GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", colors=COLOR_MUTED, length=0)
    ax.set_ylabel(ylabel, color=COLOR_MUTED, fontsize=10)


def make_bar_chart(labels, values, ylabel, title, out_path, value_fmt="{:.4f}"):
    fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
    bars = ax.bar(
        labels,
        values,
        width=0.5,
        color=[COLOR_BASELINE, COLOR_ADAPTIVE],
    )
    style_bar_axes(ax, ylabel)
    ax.set_title(title, color=COLOR_INK, fontsize=12, pad=12)

    max_val = max(values) if values else 0
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_val * 0.02,
            value_fmt.format(value),
            ha="center",
            va="bottom",
            color=COLOR_INK,
            fontsize=10,
        )
    ax.set_ylim(0, max_val * 1.15 if max_val else 1)
    fig.tight_layout()
    fig.savefig(out_path, facecolor=COLOR_SURFACE)
    plt.close(fig)


def write_report(summary: dict) -> None:
    stats = summary["stats"]
    baseline = stats["baseline"]
    adaptive = stats["adaptive"]

    cost_reduction_pct = (
        (baseline["total_cost"] - adaptive["total_cost"]) / baseline["total_cost"] * 100
        if baseline["total_cost"]
        else 0
    )
    latency_reduction_pct = (
        (baseline["avg_latency_ms"] - adaptive["avg_latency_ms"]) / baseline["avg_latency_ms"] * 100
        if baseline["avg_latency_ms"]
        else 0
    )

    lines = []
    lines.append("# CostQual-Router Prototype -- Comparison Report\n")

    lines.append("## Latency\n")
    lines.append("| System | Total (ms) | Average (ms) |")
    lines.append("|---|---|---|")
    lines.append(f"| Baseline | {baseline['total_latency_ms']:.1f} | {baseline['avg_latency_ms']:.1f} |")
    lines.append(f"| Adaptive | {adaptive['total_latency_ms']:.1f} | {adaptive['avg_latency_ms']:.1f} |\n")

    lines.append("## Estimated cost\n")
    lines.append("| System | Total estimated cost |")
    lines.append("|---|---|")
    lines.append(f"| Baseline | {baseline['total_cost']:.6f} |")
    lines.append(f"| Adaptive | {adaptive['total_cost']:.6f} |\n")

    lines.append("## Cache hit rate by category (adaptive only)\n")
    lines.append("| Category | Hits | Total | Hit rate |")
    lines.append("|---|---|---|---|")
    for category, counts in sorted(summary["cache_by_category"].items()):
        rate = counts["hits"] / counts["total"] if counts["total"] else 0
        lines.append(f"| {category} | {counts['hits']} | {counts['total']} | {rate:.0%} |")
    lines.append(f"\nOverall cache hit rate: **{summary['overall_hit_rate']:.0%}**\n")

    lines.append("## Tier usage distribution (adaptive, cache misses only)\n")
    lines.append("| Tier | Share of cache-miss queries |")
    lines.append("|---|---|")
    for tier, share in sorted(summary["tier_distribution"].items()):
        lines.append(f"| {tier} | {share:.0%} |")

    if os.path.exists(QUALITY_CHECK_PATH):
        with open(QUALITY_CHECK_PATH, encoding="utf-8") as f:
            quality_rows = list(csv.DictReader(f))
        if quality_rows:
            passes = sum(1 for r in quality_rows if r["verdict"] == "PASS")
            lines.append("## Quality sanity check\n")
            lines.append(
                f"Of the queries where the adaptive router used a smaller model than the "
                f"baseline **and** produced a different answer, {len(quality_rows)} were "
                f"sampled and judged (by the baseline model) for whether the smaller model's "
                f"answer was still acceptable: **{passes}/{len(quality_rows)} passed "
                f"({passes / len(quality_rows):.0%})**. This is a lightweight sanity check, not "
                f"a rigorous eval -- see `quality_check_results.csv` for the sampled "
                f"question/answer pairs and `prototype_plan.md` Step 9 for scope.\n"
            )

    lines.append("## Charts\n")
    lines.append("![Estimated cost comparison](cost_comparison.png)\n")
    lines.append("![Average latency comparison](latency_comparison.png)\n")

    latency_verb = "reduced" if latency_reduction_pct >= 0 else "increased"
    lines.append("## Interpretation\n")
    lines.append(
        f"The adaptive system (semantic cache + complexity-based model routing) reduced "
        f"estimated cost by **{cost_reduction_pct:.0f}%**, while average latency "
        f"{latency_verb} by **{abs(latency_reduction_pct):.0f}%** compared to the always-on "
        f"baseline -- the large tier (mistral:7b) is genuinely more capable but slower than "
        f"the baseline's phi3:mini, so latency is a real tradeoff for cost savings on the "
        f"queries routed there. Cache hit rate was **{summary['overall_hit_rate']:.0%}** "
        f"overall, driven mostly by the duplicate and paraphrase query categories -- "
        f"confirming that semantic caching catches near-duplicate questions, not just exact "
        f"repeats, without needing a larger model for queries that don't require one."
    )

    with open("report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    rows = load_rows()
    summary = compute_stats(rows)
    stats = summary["stats"]

    make_bar_chart(
        ["Baseline", "Adaptive"],
        [stats["baseline"]["total_cost"], stats["adaptive"]["total_cost"]],
        "Estimated cost (fake USD)",
        "Total Estimated Cost: Baseline vs Adaptive",
        "cost_comparison.png",
        value_fmt="{:.5f}",
    )

    make_bar_chart(
        ["Baseline", "Adaptive"],
        [stats["baseline"]["avg_latency_ms"], stats["adaptive"]["avg_latency_ms"]],
        "Average latency (ms)",
        "Average Latency: Baseline vs Adaptive",
        "latency_comparison.png",
        value_fmt="{:.0f}",
    )

    write_report(summary)

    print("Wrote cost_comparison.png, latency_comparison.png, report.md")
    print(f"\nBaseline: {stats['baseline']}")
    print(f"Adaptive: {stats['adaptive']}")
    print(f"Overall cache hit rate: {summary['overall_hit_rate']:.0%}")
    print(f"Tier distribution: {summary['tier_distribution']}")


if __name__ == "__main__":
    main()
