#!/usr/bin/env python3
"""Check whether the LightRAG Railway ingestion is still alive via its checkpoint
timestamp, since `ps` cannot see processes started outside this sandbox
(confirmed 2026-07-24: a live 16.5h-old ingestion process was invisible to
`ps aux` from a Claude Code session, causing a duplicate-launch near-incident).
"""

import json
import sys
import time
from pathlib import Path

CHECKPOINT_FILE = Path(__file__).resolve().parent.parent / "data" / "lightrag_checkpoint_railway.json"
TOTAL_POINTS = 89053
STALE_AFTER_SECONDS = 300  # checkpoints save every ~50-point batch; should never be this old while alive


def main() -> int:
    if not CHECKPOINT_FILE.exists():
        print(f"NO CHECKPOINT: {CHECKPOINT_FILE} does not exist")
        return 1

    data = json.loads(CHECKPOINT_FILE.read_text())
    age = time.time() - data["timestamp"]
    pct = data["processed_count"] / TOTAL_POINTS * 100

    if age > STALE_AFTER_SECONDS:
        print(f"STALE: last checkpoint {age:.0f}s ago ({data['processed_count']}/{TOTAL_POINTS}, {pct:.1f}%) — likely dead")
        return 1

    print(f"FRESH: last checkpoint {age:.0f}s ago ({data['processed_count']}/{TOTAL_POINTS}, {pct:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
