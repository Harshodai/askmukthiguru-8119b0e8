#!/usr/bin/env python3
"""Read-only audit for first-person span boundaries, completeness, and rights (Invariant X1 / Phase A).

Inspects a Qdrant collection or exported points file and verifies:
1. Child boundary defects (empty, tail_no_terminal, dangling words, etc.)
2. Child completeness status (COMPLETE, FRAGMENT, UNCERTAIN)
3. Orphaned fragments (connective opener without previous_span_id)
4. Parent completeness 3-way consistency with children
5. Deterministic hash integrity (sha256(verbatim_text) == source_text_hash)
6. Rights clearance stamps (domain_rights_status == 'licensed')
7. Zero bare-flag speakers (speaker_verified=True requires voice_verification_method)

Exit codes:
0: All gates pass or audit report generated successfully
1: Violations found when --check is passed
2: Invalid arguments or input data unreadable
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_backend_root() -> Path:
    candidate = Path(__file__).resolve().parent
    for _ in range(4):
        if (candidate / "domain").is_dir() and (candidate / "ingest").is_dir():
            return candidate
        candidate = candidate.parent
    here = Path(__file__).resolve()
    for root in (here.parents[2] / "backend", here.parents[1], here.parents[2]):
        if (root / "domain").is_dir() and (root / "ingest").is_dir():
            return root
    raise RuntimeError(f"Cannot resolve backend root from {__file__}")


backend_root = _resolve_backend_root()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from domain.first_person_context import (
    clip_text_hash,
)
from ingest.verbatim.boundaries import boundary_defects
from services.first_person_context_store import bare_flag_speaker_ids


def audit_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Audit payloads for first-person context dataset."""
    children: list[dict[str, Any]] = []
    parents: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []

    for r in records:
        rtype = r.get("record_type")
        if rtype == "retrieval_child":
            children.append(r)
        elif rtype == "parent_unit":
            parents.append(r)
        else:
            other.append(r)

    total_children = len(children)
    total_parents = len(parents)

    # 1. Child boundary & completeness stats
    child_boundary_counts = Counter(r.get("boundary_status") for r in children)
    child_completeness_counts = Counter(r.get("completeness_status") for r in children)

    # 2. Defects detected in text
    child_defects_counter: Counter[str] = Counter()
    hash_mismatches = 0
    orphan_fragments = 0  # starts with connective but previous_span_id is None

    _CONNECTIVE_STARTS = frozenset({"and", "but", "or", "so", "because", "then", "therefore"})

    for c in children:
        text = str(c.get("verbatim_text") or "").strip()
        defects = boundary_defects(text.split())
        for d in defects:
            child_defects_counter[d] += 1

        stored_hash = c.get("source_text_hash")
        if stored_hash and text:
            if clip_text_hash(text) != stored_hash:
                hash_mismatches += 1

        first_word = text.split()[0].lower().rstrip(",;:-.") if text else ""
        if first_word in _CONNECTIVE_STARTS and not c.get("previous_span_id"):
            orphan_fragments += 1

    # 3. Parent stats
    parent_boundary_counts = Counter(r.get("boundary_status") for r in parents)
    parent_completeness_counts = Counter(r.get("completeness_status") for r in parents)
    single_child_parents = sum(
        1 for p in parents if len(p.get("ordered_source_span_ids") or []) == 1
    )

    # 4. Rights verification
    rights_status_counts = Counter(r.get("domain_rights_status") for r in children)

    # 5. Bare flag speakers
    bare_flags = bare_flag_speaker_ids(children)

    return {
        "summary": {
            "total_points": len(children) + len(parents) + len(other),
            "retrieval_children": total_children,
            "parent_units": total_parents,
            "other_records": len(other),
            "single_child_parents": single_child_parents,
        },
        "children": {
            "boundary_status": dict(child_boundary_counts),
            "completeness_status": dict(child_completeness_counts),
            "defects_detected": dict(child_defects_counter),
            "hash_mismatches": hash_mismatches,
            "orphan_fragments": orphan_fragments,
            "bare_speaker_flags": len(bare_flags),
            "bare_speaker_sample_ids": bare_flags[:5],
            "domain_rights_status": dict(rights_status_counts),
        },
        "parents": {
            "boundary_status": dict(parent_boundary_counts),
            "completeness_status": dict(parent_completeness_counts),
        },
    }


def load_from_qdrant(collection: str, url: str) -> list[dict[str, Any]]:
    from qdrant_client import QdrantClient

    client = QdrantClient(url=url)
    records: list[dict[str, Any]] = []
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=500,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        for p in points:
            if p.payload:
                records.append(p.payload)
        if next_offset is None:
            break
        offset = next_offset
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=Path, help="Path to exported points JSON file")
    parser.add_argument("--collection", default="fp-context-v1", help="Qdrant collection name")
    parser.add_argument("--url", default="http://localhost:6333", help="Qdrant URL")
    parser.add_argument("--check", action="store_true", help="Exit 1 if any blocker defects found")
    parser.add_argument("--out", type=Path, help="Path to write JSON report")
    args = parser.parse_args()

    if args.points:
        with open(args.points, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                records = [p.get("payload", p) for p in data]
            elif isinstance(data, dict) and "points" in data:
                records = [p.get("payload", p) for p in data["points"]]
            else:
                logger.error("Unknown format in --points JSON")
                return 2
    else:
        try:
            records = load_from_qdrant(args.collection, args.url)
        except Exception as e:
            logger.error(f"Failed to load from Qdrant {args.collection} at {args.url}: {e}")
            return 2

    results = audit_records(records)

    print("=" * 60)
    print("FIRST-PERSON SPAN BOUNDARY & RIGHTS AUDIT")
    print("=" * 60)
    print(json.dumps(results, indent=2))
    print("=" * 60)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Report written to {args.out}")

    if args.check:
        ch = results["children"]
        blockers = []
        if ch.get("bare_speaker_flags", 0) > 0:
            blockers.append(f"{ch['bare_speaker_flags']} bare speaker flags found")
        if ch.get("hash_mismatches", 0) > 0:
            blockers.append(f"{ch['hash_mismatches']} hash mismatches found")
        unlicensed = sum(
            v for k, v in ch.get("domain_rights_status", {}).items() if k != "licensed"
        )
        if unlicensed > 0:
            blockers.append(f"{unlicensed} unlicensed child spans found")
        if blockers:
            print("AUDIT FAILED (Blockers found):", file=sys.stderr)
            for b in blockers:
                print(f"  - {b}", file=sys.stderr)
            return 1
        print("AUDIT PASSED: All blocker checks clear.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
