#!/usr/bin/env python3
"""Launch gate: Qdrant data-integrity and index readiness.

Distinguishes four separate conditions that are easy to conflate:
schema declared vs index actually created vs field present on points vs
field actually usable by a filter. Per
docs/audits/LAUNCH_READINESS_GATES_2026-09-13.md.

Exit 0: no BLOCKER/HIGH failures. Exit 1: otherwise.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

REQUIRED_FILTER_FIELDS = ["tenant_id", "corpus_id", "teacher_id", "teacher_ids", "domain_rights_status"]


@dataclass
class Finding:
    severity: str
    name: str
    passed: bool
    detail: str
    remediation: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity, name, passed, detail, remediation=""):
        self.findings.append(Finding(severity, name, passed, detail, remediation))

    def blocking_failures(self):
        return [f for f in self.findings if not f.passed and f.severity in ("BLOCKER", "HIGH")]

    def print_report(self):
        for f in self.findings:
            status = "PASS" if f.passed else "FAIL"
            print(f"[{f.severity:8s}] [{status}] {f.name}: {f.detail}")
            if not f.passed and f.remediation:
                print(f"           remediation: {f.remediation}")


def main() -> int:
    from qdrant_client import QdrantClient

    url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    collection = os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom_contextual")
    documented_count = int(os.environ.get("DOCUMENTED_POINT_COUNT", "12904"))

    report = Report()
    client = QdrantClient(url=url)

    try:
        info = client.get_collection(collection)
        report.add("BLOCKER", "qdrant_reachable", True, f"Connected, collection={collection}")
    except Exception as exc:
        report.add("BLOCKER", "qdrant_reachable", False, f"Connection/collection failed: {exc}")
        report.print_report()
        return 1

    actual_count = info.points_count
    drift = abs(actual_count - documented_count) / documented_count if documented_count else 1
    report.add(
        "HIGH",
        "corpus_count_matches_docs",
        drift < 0.05,
        f"live={actual_count}, documented={documented_count} ({drift:.1%} drift)",
        "Update DOCUMENTED_POINT_COUNT / CLAUDE.md / README.md to the live figure, "
        "or investigate why the corpus size moved unexpectedly. This is the exact "
        "class of bug the 89,053-vs-12,904 stale figure was.",
    )

    payload_schema = info.payload_schema
    for field_name in REQUIRED_FILTER_FIELDS:
        idx = payload_schema.get(field_name)
        idx_exists = idx is not None
        report.add(
            "BLOCKER",
            f"index_exists:{field_name}",
            idx_exists,
            f"{'indexed' if idx_exists else 'NOT indexed'}"
            + (f", points={idx.points}" if idx_exists else ""),
            f"Add ('{field_name}', 'keyword') to QdrantClientManager._PAYLOAD_INDEXES "
            f"and apply via create_payload_index — this field is used in a `must` "
            f"filter somewhere in rag/nodes/retrieval.py or rag/corpus_scope.py.",
        )
        if idx_exists:
            # Schema declares the index; separately confirm points actually carry
            # non-null values under it — an index with 0 points means the filter
            # silently matches nothing, not an error.
            populated = idx.points > 0
            report.add(
                "BLOCKER" if field_name in ("tenant_id", "corpus_id", "domain_rights_status") else "MEDIUM",
                f"index_populated:{field_name}",
                populated,
                f"{idx.points} points carry a value under this index",
                f"An index that exists but indexes 0 points means any filter on "
                f"'{field_name}' silently returns zero results, not an error — this "
                f"is exactly what happened to teacher_id before its backfill.",
            )

    for f in REQUIRED_FILTER_FIELDS:
        empty = client.count(
            collection_name=collection,
            count_filter={"must": [{"is_empty": {"key": f}}]},
            exact=True,
        ).count
        empty_rate = empty / actual_count if actual_count else 0
        report.add(
            "HIGH" if f in ("corpus_id", "domain_rights_status", "tenant_id") else "MEDIUM",
            f"field_coverage:{f}",
            empty_rate < 0.05,
            f"{empty}/{actual_count} points ({empty_rate:.1%}) have this field empty/missing",
        )

    report.print_report()
    return 1 if report.blocking_failures() else 0


if __name__ == "__main__":
    sys.exit(main())
