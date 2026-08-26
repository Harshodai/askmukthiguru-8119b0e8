"""Plot merged cache-free question-bank latency summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    tiers = data["by_query_tier"]
    strata = data["by_stratum"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5), constrained_layout=True)
    fig.suptitle("AskMukthiGuru cache-disabled question-bank benchmark", fontsize=15, fontweight="bold")

    tier_items = [(key, value) for key, value in tiers.items() if value.get("backend_mean_ms") is not None]
    tier_items.sort(key=lambda item: item[1]["backend_mean_ms"])
    axes[0].barh([item[0] for item in tier_items], [item[1]["backend_mean_ms"] / 1000 for item in tier_items], color="#2f6f9f")
    axes[0].set_title("Observed query-tier backend mean")
    axes[0].set_xlabel("Seconds; cache disabled")
    for index, (_, value) in enumerate(tier_items):
        axes[0].text(value["backend_mean_ms"] / 1000 + 0.1, index, f"n={value['n_included_cache_free']}", va="center", fontsize=9)

    stratum_items = [(key, value) for key, value in strata.items() if value.get("backend_mean_ms") is not None]
    stratum_items.sort(key=lambda item: item[1]["backend_mean_ms"])
    axes[1].barh([item[0] for item in stratum_items], [item[1]["backend_mean_ms"] / 1000 for item in stratum_items], color="#7c4d9e")
    axes[1].set_title("Benchmark-stratum backend mean")
    axes[1].set_xlabel("Seconds; cache disabled")
    for index, (_, value) in enumerate(stratum_items):
        axes[1].text(value["backend_mean_ms"] / 1000 + 0.1, index, f"n={value['n_included_cache_free']}", va="center", fontsize=9)

    for axis in axes:
        axis.grid(axis="x", alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, bbox_inches="tight")
    print(args.output)


if __name__ == "__main__":
    main()
