#!/usr/bin/env python3
"""audit_lineage_completeness.py — Corpus Lineage Completeness Auditor.

DE-6.2: Audits Qdrant vector points for provenance & lineage completeness:
  - release: source_release_version or source_release_id
  - encoder: embedding_model
  - chunker: chunker_version (excluding "unknown_legacy")
  - gate_verdict: quality gate verdict
  - asr_method: ASR pipeline or transcription method

Updates Prometheus gauge CORPUS_LINEAGE_COMPLETENESS_RATIO with ratios [0.0, 1.0].
Supports --dry-run to audit without setting Prometheus metrics.

Usage:
    python -m scripts.ops.audit_lineage_completeness
    python -m scripts.ops.audit_lineage_completeness --collection spiritual_wisdom_contextual
    python -m scripts.ops.audit_lineage_completeness --dry-run
    python -m scripts.ops.audit_lineage_completeness --json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
if (_HERE.parents[2] / "backend").is_dir():
    _BACKEND = _HERE.parents[2] / "backend"
else:
    _BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from qdrant_client import QdrantClient

from app.config import settings
from app.metrics import CORPUS_LINEAGE_COMPLETENESS_RATIO

logger = logging.getLogger("audit_lineage_completeness")

LINEAGE_FIELDS = ("release", "encoder", "chunker", "gate_verdict", "asr_method")


def _get_qdrant_client(
    qdrant_url: Optional[str] = None, api_key: Optional[str] = None
) -> tuple[QdrantClient, str]:
    """Build QdrantClient with automatic container/host URL fallback."""
    url = (
        qdrant_url
        or os.environ.get("QDRANT_URL")
        or getattr(settings, "qdrant_url", "http://localhost:6333")
    )
    if "://qdrant:" in url:
        import socket

        try:
            socket.gethostbyname("qdrant")
        except socket.gaierror:
            url = url.replace("://qdrant:", "://localhost:")

    key = (
        api_key
        or os.environ.get("QDRANT_API_KEY")
        or getattr(settings, "qdrant_api_key", None)
        or None
    )
    return QdrantClient(url=url, api_key=key, timeout=60), url


def check_point_lineage(payload: Optional[dict[str, Any]]) -> dict[str, bool]:
    """Evaluate whether required lineage fields are present on a point payload."""
    if not payload:
        return {f: False for f in LINEAGE_FIELDS}

    # Release check: non-null, non-zero release version or release id
    rel_ver = (
        payload.get("source_release_version")
        or payload.get("source_release_id")
        or payload.get("release_version")
    )
    has_release = bool(rel_ver is not None and str(rel_ver).strip() not in {"", "0", "None"})

    # Encoder check: embedding model specified
    enc = (
        payload.get("embedding_model")
        or payload.get("encoder_model")
        or payload.get("dense_encoder")
    )
    has_encoder = bool(enc is not None and str(enc).strip())

    # Chunker check: chunker version recorded and not 'unknown_legacy'
    chk = payload.get("chunker_version")
    has_chunker = bool(
        chk is not None and str(chk).strip() and str(chk).strip() != "unknown_legacy"
    )

    # Gate verdict check
    gate = payload.get("gate_verdict") or payload.get("quality_gate_verdict")
    has_gate = bool(gate is not None and str(gate).strip())

    # ASR method check. ``audio_format`` is a container/codec property, not
    # evidence of how the transcript was produced, so it must not count.
    asr = payload.get("asr_method") or payload.get("transcription_method")
    has_asr = bool(asr is not None and str(asr).strip())

    return {
        "release": has_release,
        "encoder": has_encoder,
        "chunker": has_chunker,
        "gate_verdict": has_gate,
        "asr_method": has_asr,
    }


def audit_collection_lineage(
    client: QdrantClient,
    collection_name: str,
    limit: Optional[int] = None,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scroll points in collection and compute completeness ratios for lineage fields."""
    now = datetime.now(tz=UTC)
    field_counts = {f: 0 for f in LINEAGE_FIELDS}
    all_complete_count = 0
    total_points = 0

    next_offset = None

    while True:
        scroll_limit = batch_size
        if limit is not None:
            remaining = limit - total_points
            if remaining <= 0:
                break
            scroll_limit = min(batch_size, remaining)

        res, next_offset = client.scroll(
            collection_name=collection_name,
            limit=scroll_limit,
            offset=next_offset,
            with_payload=True,
            with_vectors=False,
        )

        if not res:
            break

        for pt in res:
            total_points += 1
            payload = getattr(pt, "payload", {}) or {}
            verdicts = check_point_lineage(payload)

            for f in LINEAGE_FIELDS:
                if verdicts[f]:
                    field_counts[f] += 1

            if all(verdicts.values()):
                all_complete_count += 1

        if next_offset is None:
            break

    # Compute ratios
    ratios: dict[str, float] = {}
    for f in LINEAGE_FIELDS:
        r = (field_counts[f] / total_points) if total_points > 0 else 0.0
        ratios[f] = round(r, 4)

    all_ratio = (all_complete_count / total_points) if total_points > 0 else 0.0
    ratios["all_fields"] = round(all_ratio, 4)

    if not dry_run and total_points > 0:
        for f in LINEAGE_FIELDS:
            CORPUS_LINEAGE_COMPLETENESS_RATIO.labels(field=f).set(ratios[f])
        CORPUS_LINEAGE_COMPLETENESS_RATIO.labels(field="all_fields").set(ratios["all_fields"])

    return {
        "timestamp": now.isoformat(),
        "collection": collection_name,
        "total_points_audited": total_points,
        "counts": field_counts,
        "all_complete_count": all_complete_count,
        "completeness_ratios": ratios,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit corpus points for lineage completeness")
    parser.add_argument(
        "--collection",
        default=getattr(settings, "qdrant_collection", "spiritual_wisdom_contextual"),
        help="Collection to audit (default: spiritual_wisdom_contextual)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Max points to sample (default: all)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=500, help="Scroll batch size (default: 500)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print audit without setting Prometheus metrics"
    )
    parser.add_argument("--json", action="store_true", help="Output report in JSON format")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    client, url = _get_qdrant_client()
    report = audit_collection_lineage(
        client=client,
        collection_name=args.collection,
        limit=args.limit,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        tot = report["total_points_audited"]
        print(f"=== Lineage Completeness Audit: {report['collection']} ({url}) ===")
        print(f"Total points evaluated: {tot} | Dry-run: {report['dry_run']}\n")
        print(f"{'Field':<16} {'Count Present':<16} {'Completeness Ratio':<20} {'Status'}")
        print("-" * 65)

        for f in LINEAGE_FIELDS:
            cnt = report["counts"][f]
            ratio = report["completeness_ratios"][f]
            pct = f"{ratio * 100:.1f}%"
            status = "GOOD" if ratio >= 0.9 else ("FAIR" if ratio >= 0.5 else "LOW")
            print(f"{f:<16} {cnt:<16} {pct:<20} {status}")

        print("-" * 65)
        all_pct = f"{report['completeness_ratios']['all_fields'] * 100:.1f}%"
        print(f"{'ALL FIELDS':<16} {report['all_complete_count']:<16} {all_pct:<20}")
        print("\nAudit complete.\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
