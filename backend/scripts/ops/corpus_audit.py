"""Corpus contamination audit — measure, bucket, and target the re-ingest.

Read-only. Scans a Qdrant collection with the same `services.text_quality_filter`
gate that now guards every write path, and reports:

  * overall contamination rate (the number that scopes the re-ingest)
  * a breakdown by artifact reason (LLM chain-of-thought vs ASR decoder loop)
  * a per-source table bucketed into re-ingest priority

Why this exists
---------------
The 2026-08-01 audit found 29.4% of the 89,061-chunk `spiritual_wisdom`
collection was machine output — the extraction LLM's own reasoning and Whisper
decoder loops — embedded and retrievable as doctrine. That number came from
ad-hoc scripts rewritten four times as the detector sharpened
(59% -> 13.7% -> 24.3% -> 29.4%). This module is the reproducible version, so
before/after comparisons across the migration are apples to apples.

Two modes:

  audit  (default) — full report to stdout + optional JSON
  ci               — sample N points, exit non-zero above --max-rate

CI mode is the "distribution layer" the validation literature calls for: a source
whose artifact rate jumps from 2% to 60% is a source whose LLM went off the
rails, and without this that is invisible.

Usage
-----
    python -m scripts.ops.corpus_audit
    python -m scripts.ops.corpus_audit --collection spiritual_wisdom_contextual
    python -m scripts.ops.corpus_audit --json reports/corpus_audit.json
    python -m scripts.ops.corpus_audit --mode ci --sample 5000 --max-rate 0.01
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.text_quality_filter import find_artifact  # noqa: E402

# Ingest prepends "[Source: ... | Topic: ...]" / "[RAPTOR Level: N | ...]" to the
# chunk body. Strip it before judging the body so a RAPTOR header — by design,
# and stripped again at answer time — is not counted as body poison.
_HEADER_RE = re.compile(r"^\[(?:Source|RAPTOR)[^\]]*\]\s*")

# Ingestion writes two chunk sizes into the same collection: proposition-tier
# (single extracted sentences) and passage-tier (boundary-chunked teaching).
# They fail differently — a proposition is one LLM output, so extraction
# commentary lands as the whole chunk rather than as a fragment inside real
# teaching — so the overall rate hides which tier actually needs re-ingest.
PROPOSITION_MAX_CHARS = 200

# Re-ingest priority. A source above TOTAL_LOSS is unusable and must come from
# origin; PARTIAL is cheaper to re-ingest wholesale than to repair point-by-point.
_TOTAL_LOSS = 0.80
_PARTIAL = 0.05


def _bucket(pct: float) -> str:
    if pct >= _TOTAL_LOSS:
        return "total_loss"
    if pct >= _PARTIAL:
        return "partial"
    if pct > 0:
        return "trace"
    return "clean"


def _scroll(base_url: str, collection: str, limit: int, cap: int | None) -> Iterator[dict]:
    """Yield payloads from a Qdrant collection. Read-only."""
    import urllib.request

    offset: Any = None
    seen = 0
    while True:
        body: dict[str, Any] = {"limit": limit, "with_payload": True}
        if offset is not None:
            body["offset"] = offset
        req = urllib.request.Request(
            f"{base_url}/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.load(resp)["result"]
        points = result.get("points") or []
        if not points:
            return
        for p in points:
            yield p.get("payload") or {}
            seen += 1
            if cap and seen >= cap:
                return
        offset = result.get("next_page_offset")
        if offset is None:
            return


def audit(base_url: str, collection: str, cap: int | None = None) -> dict[str, Any]:
    """Scan *collection* and return a structured contamination report."""
    total = 0
    contaminated = 0
    reasons: Counter[str] = Counter()
    per_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [poisoned, total]
    samples: dict[str, list[str]] = defaultdict(list)
    per_tier: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [poisoned, total]

    for payload in _scroll(base_url, collection, 500, cap):
        total += 1
        source = payload.get("source_url") or payload.get("title") or "(unknown)"
        body = _HEADER_RE.sub("", payload.get("text") or "")
        topic = payload.get("topic") or ""
        tier = "proposition" if len(body.strip()) < PROPOSITION_MAX_CHARS else "passage"

        artifact = find_artifact(body) or find_artifact(topic)
        per_source[source][1] += 1
        per_tier[tier][1] += 1
        if artifact:
            contaminated += 1
            per_source[source][0] += 1
            per_tier[tier][0] += 1
            kind = "asr_repetition_loop" if artifact.startswith("repetition") else "llm_artifact"
            reasons[kind] += 1
            if len(samples[source]) < 2:
                samples[source].append(f"{artifact} :: {body[:120]}".replace("\n", " "))

    sources = []
    for src, (bad, tot) in per_source.items():
        pct = bad / tot if tot else 0.0
        sources.append(
            {
                "source_url": src,
                "total": tot,
                "poisoned": bad,
                "pct": round(pct, 4),
                "bucket": _bucket(pct),
                "samples": samples.get(src, []),
            }
        )
    sources.sort(key=lambda s: (-s["poisoned"], -s["pct"]))

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "collection": collection,
        "scanned": total,
        "contaminated": contaminated,
        "rate": round(contaminated / total, 4) if total else 0.0,
        "by_reason": dict(reasons),
        "by_tier": {
            tier: {
                "total": tot,
                "poisoned": bad,
                "rate": round(bad / tot, 4) if tot else 0.0,
            }
            for tier, (bad, tot) in sorted(per_tier.items())
        },
        "buckets": dict(Counter(s["bucket"] for s in sources)),
        "sources": sources,
    }


def _print_report(report: dict[str, Any], top: int = 20) -> None:
    total, bad = report["scanned"], report["contaminated"]
    print(f"\ncollection  : {report['collection']}")
    print(f"scanned     : {total:,} chunks across {len(report['sources'])} sources")
    print(f"CONTAMINATED: {bad:,}  ({100 * report['rate']:.1f}%)\n")

    if report["by_reason"]:
        print("by reason:")
        for kind, n in sorted(report["by_reason"].items(), key=lambda x: -x[1]):
            print(f"  {n:7,}  {kind}")

    if report.get("by_tier"):
        print(f"\nby chunk tier (proposition = body < {PROPOSITION_MAX_CHARS} chars):")
        for tier, stats in report["by_tier"].items():
            print(
                f"  {stats['poisoned']:7,}/{stats['total']:<8,} {100 * stats['rate']:5.1f}%  {tier}"
            )

    print("\nsource buckets (re-ingest priority):")
    for bucket in ("total_loss", "partial", "trace", "clean"):
        print(f"  {report['buckets'].get(bucket, 0):5}  {bucket}")

    worst = [s for s in report["sources"] if s["poisoned"]][:top]
    if worst:
        print(f"\ntop {len(worst)} re-ingest targets:")
        for s in worst:
            print(
                f"  {s['poisoned']:5}/{s['total']:<6} {100 * s['pct']:3.0f}%  "
                f"[{s['bucket']:10}] {s['source_url'][:64]}"
            )
    if not bad:
        print("\nno contamination detected.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Corpus contamination audit (read-only).")
    parser.add_argument(
        "--collection", default=None, help="Qdrant collection (default: settings.qdrant_collection)"
    )
    parser.add_argument(
        "--url", default=None, help="Qdrant base URL (default: settings.qdrant_url)"
    )
    parser.add_argument("--mode", choices=("audit", "ci"), default="audit")
    parser.add_argument(
        "--sample", type=int, default=None, help="stop after N chunks (ci mode defaults to 5000)"
    )
    parser.add_argument(
        "--max-rate", type=float, default=0.01, help="ci mode: fail above this contamination rate"
    )
    parser.add_argument(
        "--json", dest="json_out", default=None, help="write the full report to this path"
    )
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)

    collection, url = args.collection, args.url
    if not collection or not url:
        try:
            from app.config import settings

            collection = collection or settings.qdrant_collection
            url = url or settings.qdrant_url
        except Exception as exc:  # pragma: no cover - config optional for CLI use
            print(f"could not load settings ({exc}); pass --collection and --url", file=sys.stderr)
            return 2

    cap = args.sample or (5000 if args.mode == "ci" else None)
    try:
        report = audit(url.rstrip("/"), collection, cap)
    except Exception as exc:
        print(f"audit failed against {url} / {collection}: {exc}", file=sys.stderr)
        return 2

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"report -> {out}")

    _print_report(report, top=args.top)

    if args.mode == "ci":
        if report["rate"] > args.max_rate:
            print(
                f"\nFAIL: contamination {100 * report['rate']:.2f}% exceeds max "
                f"{100 * args.max_rate:.2f}%",
                file=sys.stderr,
            )
            return 1
        print(
            f"\nPASS: contamination {100 * report['rate']:.2f}% within max "
            f"{100 * args.max_rate:.2f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
