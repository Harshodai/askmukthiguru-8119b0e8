#!/usr/bin/env python3
"""Stamp register-confirmed rights on the Four Sacred Secrets book chunks.

Why this exists
---------------
`docs/rights/CONTENT-RIGHTS.md` records that the project owner confirmed the
rights basis for *The Four Sacred Secrets* on 2026-09-23. The live points in
`spiritual_wisdom_contextual` still carry the ingestion-time default
`domain_rights_status="unverified"`. Because `require_licensed_domain_reads`
defaults to True, those 1,196 chunks are excluded from every retrieval today.

Invariant X40 (register -> stamp -> filter -> enforce) says the stamp must come
from the register, not from a guess. This script applies exactly that stamp.

What it deliberately does NOT do
--------------------------------
- It does not invent an `ingested_at` for chunks whose original write time was
  never recorded. The 3 sibling chunks from the 2026-09-01 re-ingest carry a
  timestamp; the 1,196 bulk chunks predate it. We stamp the *reconstructed*
  value and label it with `ingested_at_basis` so nothing looks like an
  original write-time stamp.
- It never writes to `first_person_*` collections or any live serving alias.

Usage
-----
    python3 scripts/ops/stamp_four_sacred_secrets_rights.py --dry-run
    python3 scripts/ops/stamp_four_sacred_secrets_rights.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = "spiritual_wisdom_contextual"
# Exact source_url. A full-text `match: text` is tokenized and its index updates
# asynchronously after set_payload, so counts taken right after a write are
# inconsistent; the exact keyword match is deterministic.
SOURCE_URL = "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"

# Earliest timestamp seen on a sibling chunk from the 2026-09-01 re-ingest run.
RECONSTRUCTED_INGESTED_AT = "2026-09-01T08:24:55.083854+00:00"
INGESTED_AT_BASIS = "reconstructed_from_sibling_reingest_run_2026-09-01"

FILTER = {
    "must": [
        {"key": "source_url", "match": {"value": SOURCE_URL}},
        {"key": "domain_rights_status", "match": {"value": "unverified"}},
    ]
}

PAYLOAD = {
    "domain_rights_status": "licensed",
    "rights_status": "licensed",
    "source_type": "book",
    "ingested_at": RECONSTRUCTED_INGESTED_AT,
    "ingested_at_basis": INGESTED_AT_BASIS,
}


def count(client: httpx.Client, flt: dict) -> int:
    r = client.post(
        f"/collections/{COLLECTION}/points/count",
        json={"exact": True, "filter": flt},
    )
    r.raise_for_status()
    return r.json()["result"]["count"]


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with httpx.Client(base_url=QDRANT_URL, timeout=60) as client:
        pending = count(client, FILTER)
        total_book = count(
            client,
            {"must": [{"key": "source_url", "match": {"value": SOURCE_URL}}]},
        )
        already = total_book - pending
        print(f"collection={COLLECTION}")
        print(f"book points total={total_book} already_stamped={already} pending={pending}")

        if args.dry_run:
            print("dry-run: no writes performed")
            return 0

        if pending == 0:
            print("nothing to do")
            return 0

        snap = client.post(f"/collections/{COLLECTION}/snapshots")
        snap.raise_for_status()
        print(f"snapshot created: {snap.json()['result'].get('name')}")

        r = client.post(
            f"/collections/{COLLECTION}/points/payload",
            json={"payload": PAYLOAD, "filter": FILTER},
        )
        r.raise_for_status()
        print(f"set_payload result: {r.json().get('result')}")

        remaining = count(client, FILTER)
        licensed_book = count(
            client,
            {
                "must": [
                    {"key": "source_url", "match": {"value": SOURCE_URL}},
                    {"key": "domain_rights_status", "match": {"value": "licensed"}},
                ]
            },
        )
        print(f"after: pending={remaining} licensed_book={licensed_book}")
        return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
