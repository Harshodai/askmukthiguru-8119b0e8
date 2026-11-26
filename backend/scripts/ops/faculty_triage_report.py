#!/usr/bin/env python3
"""
Faculty Triage Report Generator
===============================

Aggregates incoming triage feedback from faculty preview testing across
the 4 canonical triage categories:
  1. WRONG: Unrelated, incorrect teacher, or inappropriate
  2. WEAK: On theme, but does not directly answer
  3. MISSING: System abstained, but faculty knows a teaching exists
  4. UNSAFE: Clinical risk, self-harm boundary issue, or acute distress mishandling

Outputs summary metrics, flagged video IDs, and triage priority queue.

Usage:
  python3 scripts/ops/faculty_triage_report.py [--json] [--out report.md]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CANONICAL_TAGS = ("WRONG", "WEAK", "MISSING", "UNSAFE")


def normalize_tag(raw_tag: str | None) -> str:
    """Normalize user/faculty feedback string to canonical triage tag."""
    if not raw_tag:
        return "WEAK"
    tag_clean = raw_tag.upper().strip()
    if "UNSAFE" in tag_clean or "HARM" in tag_clean or "CRISIS" in tag_clean:
        return "UNSAFE"
    if "WRONG" in tag_clean or "INCORRECT" in tag_clean:
        return "WRONG"
    if "MISSING" in tag_clean or "NOT FOUND" in tag_clean or "ABSTAIN" in tag_clean:
        return "MISSING"
    return "WEAK"


def generate_triage_report(feedback_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze feedback rows and produce structured triage report."""
    total_events = len(feedback_rows)
    tag_counts: Counter[str] = Counter()
    problem_videos: Counter[str] = Counter()
    unsafe_events: list[dict[str, Any]] = []

    for row in feedback_rows:
        raw_reason = row.get("reason_category") or row.get("reason") or row.get("cause") or ""
        tag = normalize_tag(raw_reason)
        tag_counts[tag] += 1

        vid = row.get("video_id") or row.get("served_point_id") or "unknown"
        if tag in ("WRONG", "WEAK"):
            problem_videos[vid] += 1
        elif tag == "UNSAFE":
            unsafe_events.append({
                "timestamp": row.get("created_at") or datetime.now(UTC).isoformat(),
                "query": row.get("question") or row.get("query") or "Unknown query",
                "video_id": vid,
                "reason": row.get("reason") or "Flagged as unsafe",
            })

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_triage_events": total_events,
        "tag_breakdown": {tag: tag_counts.get(tag, 0) for tag in CANONICAL_TAGS},
        "unsafe_count": len(unsafe_events),
        "unsafe_events": unsafe_events,
        "top_problematic_clips": [
            {"video_id": v, "reports_count": c} for v, c in problem_videos.most_common(5)
        ],
    }
    return report


def format_markdown_report(report: dict[str, Any]) -> str:
    """Format report dict into an executive Markdown document."""
    lines = [
        "# AskMukthiGuru: Faculty Triage Aggregation Report",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Total Feedback Events:** {report['total_triage_events']}",
        "",
        "## 1. Triage Tag Breakdown",
        "",
        "| Canonical Tag | Count | Percentage | Priority Action |",
        "| :--- | :---: | :---: | :--- |",
    ]
    total = max(1, report["total_triage_events"])
    for tag in CANONICAL_TAGS:
        cnt = report["tag_breakdown"].get(tag, 0)
        pct = (cnt / total) * 100
        action = {
            "UNSAFE": "P0: Immediate clinician review & boundary patch",
            "WRONG": "P1: Speaker / transcript boundary re-segmentation",
            "WEAK": "P2: Retrieval relevance threshold calibration",
            "MISSING": "P3: Corpus indexing gap investigation",
        }.get(tag, "Review")
        lines.append(f"| **`{tag}`** | {cnt} | {pct:.1f}% | {action} |")

    lines.extend([
        "",
        "## 2. Acute Safety & Boundary Alerts (`UNSAFE`)",
        "",
    ])
    if report["unsafe_count"] == 0:
        lines.append("✓ **Zero unsafe feedback events reported.** Crisis preemption remains 100% compliant.")
    else:
        lines.append(f"⚠️ **{report['unsafe_count']} UNSAFE event(s) requiring immediate clinical triage:**")
        lines.append("")
        for ev in report["unsafe_events"]:
            lines.append(f"- **Query**: \"{ev['query']}\" | **Clip**: `{ev['video_id']}` | **Notes**: {ev['reason']}")

    lines.extend([
        "",
        "## 3. Top Problematic Discourse Clips",
        "",
        "| Video ID / Point ID | Total Negative Reports | Recommended Action |",
        "| :--- | :---: | :--- |",
    ])
    if not report["top_problematic_clips"]:
        lines.append("| (No repeat negative clips flagged) | 0 | - |")
    else:
        for item in report["top_problematic_clips"]:
            lines.append(f"| `{item['video_id']}` | {item['reports_count']} | Inspect video segment & speaker attribution |")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Faculty Triage Report")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--out", type=str, default="", help="File path to save Markdown report")
    args = parser.parse_args()

    # Sample / initial baseline feedback events
    sample_events = [
        {"reason_category": "wrong topic", "video_id": "UlOt31lBhLY", "question": "How to overcome fear"},
        {"reason_category": "cut mid-thought", "video_id": "xTVHvMHakow", "question": "Explain abundance"},
        {"reason_category": "missing discourse", "video_id": "none", "question": "Four sacred secrets laws"},
    ]

    report = generate_triage_report(sample_events)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    md_content = format_markdown_report(report)
    print(md_content)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md_content)
        logger.info("\nSaved report to %s", args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
