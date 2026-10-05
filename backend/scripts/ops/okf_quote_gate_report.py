#!/usr/bin/env python3
"""Read-only dry-run report for the OKF load-time verbatim quote gate (P0, 2026-09-25).

Scans the LIVE `memory/okf/` entries (excludes `staging/` and `_scripts/`, same
as `OKFStore.list_entries()`) and reports what `settings.okf_verbatim_quote_gate`
WOULD strip if it were turned on. Writes nothing under `memory/okf/`; the gate
itself stays off by default (owner decision, 2026-09-25) — this script never
flips it.

A quote only gets checked (and can only be removed) when its entry's `source`
carries a `v=<video_id>` — same as the gate's own no-op-without-video_id rule
in `okf_store.py` / `services.transcript_verbatim.strip_fabricated_quotes`.

Usage:
  .venv/bin/python -m scripts.ops.okf_quote_gate_report
  .venv/bin/python -m scripts.ops.okf_quote_gate_report --output /path/to/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from services.memory.okf_store import OKFStore, _video_id_from_source  # noqa: E402
from services.transcript_verbatim import (  # noqa: E402
    _QUOTED_STRING_RE,
    MIN_QUOTE_WORDS,
    find_verbatim,
)

DEFAULT_OUTPUT = Path(
    "/Users/harshodaikolluru/mukthiguru_attribution_data/p0/okf_quote_gate_report.json"
)


def _quotes_in(body: str) -> list[str]:
    return [
        m.group(1)
        for m in _QUOTED_STRING_RE.finditer(body)
        if len(m.group(1).split()) >= MIN_QUOTE_WORDS
    ]


def build_report() -> dict:
    """Read-only: OKFStore() defaults to okf_verbatim_quote_gate off, so bodies
    here are exactly what is served today. We check each quote ourselves rather
    than flipping the flag, so this never depends on (or mutates) settings."""
    entries = OKFStore().list_entries()

    status_counts = {"verbatim": 0, "partial": 0, "not_found": 0}
    quotes_skipped_no_video_id = 0
    affected_entries: list[dict] = []
    would_be_empty: list[str] = []

    for entry in entries:
        video_id = _video_id_from_source(entry.source)
        quotes = _quotes_in(entry.body)
        if not quotes:
            continue

        if not video_id:
            # Gate is a hard no-op without a video_id (strip_fabricated_quotes
            # returns the body unchanged) — nothing here would ever be removed.
            quotes_skipped_no_video_id += len(quotes)
            continue

        removed = 0
        kept = 0
        for quote in quotes:
            result = find_verbatim(quote, video_id=video_id)
            status_counts[result["status"]] += 1
            if result["status"] == "verbatim":
                kept += 1
            else:
                removed += 1

        if removed:
            affected_entries.append(
                {
                    "path": str(entry.path),
                    "video_id": video_id,
                    "quotes_found": len(quotes),
                    "would_remove": removed,
                }
            )
        if quotes and kept == 0:
            would_be_empty.append(str(entry.path))

    affected_entries.sort(key=lambda e: -e["would_remove"])

    return {
        "entries_scanned": len(entries),
        "quotes_found": sum(status_counts.values()) + quotes_skipped_no_video_id,
        "quotes_checked": sum(status_counts.values()),
        "quotes_skipped_no_video_id": quotes_skipped_no_video_id,
        "status_counts": status_counts,
        "entries_affected": len(affected_entries),
        "entries_that_would_end_up_empty": would_be_empty,
        "worst_10_entries": affected_entries[:10],
        "entries_affected_detail": affected_entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_report()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"DRY-RUN (read-only) — OKF verbatim quote gate report -> {args.output}")
    print(f"  entries scanned:              {report['entries_scanned']}")
    print(f"  quotes found (>= {MIN_QUOTE_WORDS} words):     {report['quotes_found']}")
    print(f"    checked (had a video_id):  {report['quotes_checked']}")
    print(f"    skipped (no video_id):     {report['quotes_skipped_no_video_id']}")
    print(
        f"  verbatim / partial / not_found: "
        f"{report['status_counts']['verbatim']} / "
        f"{report['status_counts']['partial']} / "
        f"{report['status_counts']['not_found']}"
    )
    print(f"  entries affected:             {report['entries_affected']}")
    print(f"  entries that would end up empty: {len(report['entries_that_would_end_up_empty'])}")
    for e in report["worst_10_entries"]:
        print(
            f"    - {e['path']} (video_id={e['video_id']}): would remove {e['would_remove']}/{e['quotes_found']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
