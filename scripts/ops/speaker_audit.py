#!/usr/bin/env python3
"""Random listen audit of auto-verified spans: draw a sample, then gate on the answers (P6).

Read-only. Never writes to Qdrant. The listening itself happens in the admin Video Approval
screen (plan I4); this script only decides *which* spans to listen to and whether the
answers allow promotion. The rules live in ``backend/domain/speaker_audit.py``.

    # 1. draw the sample for a batch (reads the collection, writes a JSON file)
    python scripts/ops/speaker_audit.py sample --collection first_person_v10_candidate \\
        --batch-id 2026-11-03-batch-1 --seed <fixed string> --out audit_sample.json

    # 2. after listening: reviews.jsonl has one {"source_span_id", "review_choice"} per line
    python scripts/ops/speaker_audit.py gate --sample audit_sample.json \\
        --reviews reviews.jsonl --out audit_gate.json

Exit codes: 0 sample drawn / gate passed; 1 gate blocked; 2 invalid input.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.append(str(_BACKEND))

from domain.speaker_audit import (  # noqa: E402
    AUDIT_FRACTION,
    AUDIT_MIN_SPANS,
    audit_gate,
    draw_audit_sample,
)

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INVALID_INPUT = 2


def _scroll(qdrant_url: str, collection: str, page: int = 512):
    """Yield every point payload (vectors are never requested)."""
    import requests

    offset = None
    while True:
        body: dict[str, Any] = {"limit": page, "with_payload": True, "with_vector": False}
        if offset:
            body["offset"] = offset
        resp = requests.post(
            f"{qdrant_url}/collections/{collection}/points/scroll", json=body, timeout=60
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        for point in result.get("points") or []:
            yield point.get("payload") or {}
        offset = result.get("next_page_offset")
        if not offset:
            return


def load_reviews(path: Path) -> dict[str, dict[str, Any]]:
    """Latest answer per span from a JSONL file; a malformed line is fatal."""
    reviews: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {number} is not valid JSON: {exc}") from exc
        span_id = str(row.get("source_span_id") or "") if isinstance(row, dict) else ""
        if not span_id:
            raise ValueError(f"{path}: line {number} has no source_span_id")
        reviews[span_id] = row  # later lines win: the file is append-only
    return reviews


def _write(path: str | None, payload: Any) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
    print(text, end="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="Draw the audit sample for one batch.")
    sample.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    sample.add_argument("--collection", required=True)
    sample.add_argument("--batch-id", required=True)
    sample.add_argument(
        "--seed", required=True, help="Fixed string; the same seed redraws the same spans."
    )
    sample.add_argument("--min-spans", type=int, default=AUDIT_MIN_SPANS)
    sample.add_argument("--fraction", type=float, default=AUDIT_FRACTION)
    sample.add_argument("--out", default=None)

    gate = sub.add_parser("gate", help="Decide promotion from the sample and the answers.")
    gate.add_argument("--sample", required=True)
    gate.add_argument("--reviews", required=True)
    gate.add_argument("--out", default=None)

    args = parser.parse_args(argv)
    try:
        if args.command == "sample":
            drawn = draw_audit_sample(
                _scroll(args.qdrant_url, args.collection),
                batch_id=args.batch_id,
                seed=args.seed,
                minimum=args.min_spans,
                fraction=args.fraction,
            )
            drawn["collection"] = args.collection
            _write(args.out, drawn)
            return EXIT_OK
        sample_doc = json.loads(Path(args.sample).read_text(encoding="utf-8"))
        result = audit_gate(sample_doc, load_reviews(Path(args.reviews)))
        _write(args.out, result)
        return EXIT_OK if result["ok"] else EXIT_BLOCKED
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "invalid_input", "error": str(exc)}), file=sys.stderr)
        return EXIT_INVALID_INPUT


if __name__ == "__main__":
    sys.exit(main())
