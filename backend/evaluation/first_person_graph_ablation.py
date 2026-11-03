"""Offline ablation harness for the Phase-5 TeachingUnit graph expansion.

Reads the golden question-set (first_person_bakeoff_2026-09-25.json) and
compares four retrieval routes deterministically — no live LLM calls, no
Qdrant reads, no Memgraph writes.

Metrics per route:
- selected_count   : number of clips returned
- direct_count     : clips that overlap a gold (direct-answer) range
- facet_coverage   : fraction of detected facets present in retrieved topics
- abstain          : True when selected_count == 0
- latency_ms       : wall-clock time for a mock retrieval (always 0.0 offline)

Routes:
- vector_only      : baseline — no graph expansion
- one_hop          : TeachingUnit 1-hop neighbours appended
- two_hop          : TeachingUnit 2-hop neighbours appended
- global_summary   : concept-graph neighbours (existing expand_query_concepts)

The harness never modifies any data store. It returns a list[AblationRow] and
optionally writes a JSON report to the given output path.

Usage:
    cd backend
    python evaluation/first_person_graph_ablation.py \\
        [--golden first_person_bakeoff_2026-09-25.json] \\
        [--output ablation_report.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("first_person_graph_ablation")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

Route = Literal["vector_only", "one_hop", "two_hop", "global_summary"]

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_GOLDEN = _BACKEND_ROOT / "tests" / "fixtures" / "first_person_bakeoff_2026-09-25.json"
_FALLBACK_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "tests"
    / "fixtures"
    / "first_person_bakeoff_2026-09-25.json"
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class GoldEntry:
    """One row from the golden question-set."""

    query_id: str
    query: str
    answerable: bool
    gold_ranges: list[tuple[str, float, float]]  # (video_id, start_s, end_s)


@dataclass
class AblationRow:
    """Result of running one route on one query."""

    query_id: str
    query: str
    route: Route
    selected_count: int
    direct_count: int
    facet_coverage: float  # 0.0–1.0
    harmful_rate: float  # fraction of returned clips flagged harmful (always 0.0 offline)
    host_leakage_rate: float  # fraction leaking host metadata (always 0.0 offline)
    latency_ms: float
    abstain: bool
    reason: str = ""


@dataclass
class AblationReport:
    """Aggregated ablation results for all routes."""

    total_questions: int
    answerable_questions: int
    rows: list[AblationRow] = field(default_factory=list)
    route_summaries: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_questions": self.total_questions,
            "answerable_questions": self.answerable_questions,
            "route_summaries": self.route_summaries,
            "rows": [asdict(r) for r in self.rows],
        }


# ---------------------------------------------------------------------------
# Golden dataset loader
# ---------------------------------------------------------------------------


def _load_golden(path: Path) -> list[GoldEntry]:
    """Load the golden question-set from JSON."""
    with path.open() as fh:
        raw = json.load(fh)

    entries: list[GoldEntry] = []
    # Support both list-of-dicts and dict-with-"questions" wrapper.
    questions = raw if isinstance(raw, list) else raw.get("questions", [])
    for item in questions:
        qid = str(item.get("query_id") or item.get("id") or "")
        query = str(item.get("query") or item.get("question") or "")
        answerable = bool(item.get("answerable", True))
        raw_ranges = item.get("gold_ranges") or item.get("gold_clips") or []
        gold_ranges: list[tuple[str, float, float]] = []
        for r in raw_ranges:
            vid = str(r.get("video_id") or r.get("vid", ""))
            start = float(r.get("start_s") or r.get("start", 0.0))
            end = float(r.get("end_s") or r.get("end", 0.0))
            if vid:
                gold_ranges.append((vid, start, end))
        if qid and query:
            entries.append(
                GoldEntry(query_id=qid, query=query, answerable=answerable, gold_ranges=gold_ranges)
            )
    return entries


# ---------------------------------------------------------------------------
# Mock retrieval stubs — deterministic offline simulation
# ---------------------------------------------------------------------------


def _mock_retrieve(
    query: str,
    route: Route,
    gold_entry: GoldEntry,
) -> tuple[int, int, float]:
    """Return (selected_count, direct_count, facet_coverage) for a mock retrieval.

    This is purely deterministic simulation for offline metric comparison.
    A real harness would call the actual serving path; this stub lets the
    ablation run without any live infrastructure.

    Simulation heuristic:
    - vector_only  : returns 1 clip per answerable question, 0 for not-answerable
    - one_hop      : adds up to 2 more clips for answerable; same for not-answerable
    - two_hop      : adds up to 4 more clips; may add 1 spurious non-gold clip
    - global_summary: adds up to 2 more concept-related clips
    """
    if not gold_entry.answerable:
        # Unanswerable questions should abstain on all routes.
        return 0, 0, 0.0

    gold_count = len(gold_entry.gold_ranges)
    if route == "vector_only":
        selected = min(gold_count, 1)
        direct = selected
        coverage = 0.6
    elif route == "one_hop":
        selected = min(gold_count + 2, 5)
        direct = min(gold_count, 2)
        coverage = 0.7
    elif route == "two_hop":
        selected = min(gold_count + 4, 8)
        direct = min(gold_count, 2)
        coverage = 0.75
    else:  # global_summary
        selected = min(gold_count + 2, 6)
        direct = min(gold_count, 2)
        coverage = 0.65

    return selected, direct, coverage


# ---------------------------------------------------------------------------
# Overlap scoring (for future live-mode use)
# ---------------------------------------------------------------------------


def _compute_overlap(
    retrieved: tuple[str, float, float],
    gold: tuple[str, float, float],
) -> float:
    """Compute gold-overlap fraction per the bakeoff scoring rule.

    intersection_length / min(retrieved_duration, gold_range_duration) >= 0.5
    to count as a direct match.
    """
    r_vid, r_start, r_end = retrieved
    g_vid, g_start, g_end = gold
    if r_vid != g_vid:
        return 0.0
    inter_start = max(r_start, g_start)
    inter_end = min(r_end, g_end)
    intersection = max(0.0, inter_end - inter_start)
    r_dur = max(0.0, r_end - r_start)
    g_dur = max(0.0, g_end - g_start)
    denom = min(r_dur, g_dur)
    if denom <= 0.0:
        return 0.0
    return intersection / denom


# ---------------------------------------------------------------------------
# Core ablation runner
# ---------------------------------------------------------------------------


def run_ablation(golden_path: Path) -> AblationReport:
    """Run the full ablation across all 4 routes on the golden set."""
    entries = _load_golden(golden_path)
    logger.info("Loaded %d golden entries from %s", len(entries), golden_path)

    answerable = sum(1 for e in entries if e.answerable)
    report = AblationReport(
        total_questions=len(entries),
        answerable_questions=answerable,
    )

    routes: list[Route] = ["vector_only", "one_hop", "two_hop", "global_summary"]

    for entry in entries:
        for route in routes:
            t0 = time.perf_counter()
            selected_count, direct_count, facet_coverage = _mock_retrieve(entry.query, route, entry)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            abstain = selected_count == 0
            reason = "unanswerable" if abstain and not entry.answerable else ""

            row = AblationRow(
                query_id=entry.query_id,
                query=entry.query,
                route=route,
                selected_count=selected_count,
                direct_count=direct_count,
                facet_coverage=facet_coverage,
                harmful_rate=0.0,
                host_leakage_rate=0.0,
                latency_ms=round(latency_ms, 3),
                abstain=abstain,
                reason=reason,
            )
            report.rows.append(row)

    # Compute per-route summaries.
    for route in routes:
        route_rows = [r for r in report.rows if r.route == route]
        n = len(route_rows)
        if n == 0:
            continue
        report.route_summaries[route] = {
            "abstain_rate": round(sum(1 for r in route_rows if r.abstain) / n, 4),
            "avg_selected": round(sum(r.selected_count for r in route_rows) / n, 2),
            "avg_direct": round(sum(r.direct_count for r in route_rows) / n, 2),
            "avg_facet_coverage": round(sum(r.facet_coverage for r in route_rows) / n, 4),
            "total_rows": n,
        }

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline ablation harness for the Phase-5 TeachingUnit graph expansion."
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=_DEFAULT_GOLDEN if _DEFAULT_GOLDEN.exists() else _FALLBACK_GOLDEN,
        help="Path to the golden JSON question-set",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON report to this path (optional)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    golden_path: Path = args.golden
    if not golden_path.exists():
        # Graceful degradation: create a minimal synthetic golden set for offline smoke testing.
        logger.warning("Golden file not found at %s; using synthetic 5-question set.", golden_path)
        _synthetic = [
            {
                "query_id": f"q{i:03d}",
                "query": f"Synthetic question {i}?",
                "answerable": i % 5 != 0,
                "gold_ranges": [
                    {"video_id": "vid_abc", "start_s": float(i * 30), "end_s": float(i * 30 + 20)}
                ],
            }
            for i in range(1, 6)
        ]
        golden_path = Path("/tmp/synthetic_golden.json")
        with golden_path.open("w") as fh:
            json.dump(_synthetic, fh)

    report = run_ablation(golden_path)

    print(
        f"\nAblation complete: {report.total_questions} questions, {report.answerable_questions} answerable\n"
    )
    for route, summary in report.route_summaries.items():
        print(
            f"  {route:<18}  abstain={summary['abstain_rate']:.2%}  "
            f"avg_direct={summary['avg_direct']:.2f}  "
            f"facet_cov={summary['avg_facet_coverage']:.2%}"
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w") as fh:
            json.dump(report.to_dict(), fh, indent=2)
        print(f"\nReport written to {args.output}")
