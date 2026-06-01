"""Offline DSPy optimization entrypoint.

This command exports versioned candidate artifacts. It never mutates live
prompts or production routing by itself.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from optimization.dspy.dataset import (
    examples_from_benchmark_report,
    examples_from_question_bank,
    write_jsonl,
)

ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "dspy"


def build_artifact(
    limit: int | None, report: Path | None, artifact_dir: Path = ARTIFACT_DIR
) -> Path:
    examples = examples_from_question_bank(limit=limit)
    if report:
        examples.extend(examples_from_benchmark_report(report))

    run_id = time.strftime("%Y%m%d-%H%M%S")
    out_dir = artifact_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(examples, out_dir / "examples.jsonl")

    manifest = {
        "run_id": run_id,
        "created_at": time.time(),
        "example_count": len(examples),
        "status": "candidate",
        "gating": {
            "requires_make_eval": True,
            "requires_min_score": 0.95,
            "requires_min_category_score": 0.90,
            "auto_apply_to_production": False,
        },
        "programs": [
            "QueryRewrite",
            "CitationSupportedAnswer",
            "FaithfulnessGrade",
            "RoutingDecision",
        ],
        "notes": (
            "This artifact is an offline optimization candidate. Production prompts "
            "must only be changed manually after passing eval gates."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / "preview.json").write_text(
        json.dumps([asdict(x) for x in examples[:20]], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    out_dir = build_artifact(args.limit, args.report)
    print(f"DSPy candidate artifact written to {out_dir}")


if __name__ == "__main__":
    main()
