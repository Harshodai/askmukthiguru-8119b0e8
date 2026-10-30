#!/usr/bin/env python3
"""RAG experiment harness: measure retrieval variants on train/val splits (Phase 6 / Master Plan §B & Table K.5).

Evaluates:
- RAG-4.1: Fusion strategies (RRF k=2 default, DBSF, weighted RRF).
- RAG-4.2: Contextual headers (metadata header vs no header vs situating prose).
- RAG-4.3: Rerank depth and bypass on/off.
- RAG-4.4: Contextual compression (top-k 5 vs 10 vs off).

Emits structured reports with MRR@10, NDCG@10, and per-class breakdowns
to evals/reports/<date>-<variant>.json.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("measure_rag_variants")

DEFAULT_REPORTS_DIR = Path("evals/reports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure RAG configurations across train/val query splits."
    )
    parser.add_argument(
        "--variant", choices=["fusion", "headers", "rerank", "compression", "all"], default="fusion"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate execution without running full retrieval"
    )
    parser.add_argument(
        "--out-dir", type=str, default=str(DEFAULT_REPORTS_DIR), help="Output directory for reports"
    )
    parser.add_argument(
        "--train-ratio", type=float, default=0.5, help="Train/val split ratio (default: 0.5)"
    )
    return parser.parse_args()


def split_queries(
    queries: list[dict[str, Any]], train_ratio: float = 0.5
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministically split query dataset into train and validation sets."""
    split_idx = int(len(queries) * train_ratio)
    return queries[:split_idx], queries[split_idx:]


def run_experiment(
    variant: str, val_queries: list[dict[str, Any]], dry_run: bool = False
) -> dict[str, Any]:
    """Execute evaluation for the specified variant.

    Retrieval measurement is not wired to a held-out query set yet, so this never
    emits MRR/NDCG numbers: a dry run reports every metric as ``None``
    (unmeasured), and a live run refuses rather than writing an empty "result".
    """
    timestamp = datetime.datetime.now(datetime.UTC).isoformat()
    if not dry_run:
        raise SystemExit(
            "measure_rag_variants: live measurement is not implemented (no held-out query "
            "set is wired). Refusing to write a report; use --dry-run for the plan only."
        )
    logger.info("Dry run for variant %s: plan only, no metrics measured", variant)
    return {
        "timestamp": timestamp,
        "variant": variant,
        "dry_run": True,
        "queries_evaluated": len(val_queries),
        "metrics": {"mrr_10": None, "ndcg_10": None, "per_class": None},
        "status": "unmeasured",
        "recommendation": "keep_default_unless_verified",
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.date.today().isoformat()
    report = run_experiment(args.variant, val_queries=[], dry_run=args.dry_run)

    out_file = out_dir / f"{date_str}-{args.variant}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Experiment report written to: %s", out_file)


if __name__ == "__main__":
    main()
