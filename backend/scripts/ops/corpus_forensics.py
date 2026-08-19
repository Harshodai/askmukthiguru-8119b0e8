"""Corpus forensics — data quality, field parity, and a migrate-vs-refetch verdict.

Two subcommands over one scan:

    forensic     full data-quality report (contamination, parent-child integrity,
                 FIELD PARITY against the source collection, metadata bloat,
                 citation readiness, duplication, pooling consistency)
    feasibility  per-source verdict + confidence on whether each source can be
                 MIGRATED into the contextual collection or must be REFETCHED

Why this exists
---------------
`corpus_audit.py` answers "how contaminated is this collection?". It does not
answer the two questions the re-ingest actually turns on:

1. **Can this specific source be migrated at all?** That has a measured answer
   and it is not the obvious one. Re-chunking CONCENTRATES contamination: source
   5hNCT4duOgc measured 46.4% contaminated in blue, and re-ingesting it produced
   81 rejected chunks out of 82 (98.8%) — semantic re-chunking moves boundaries
   and one chain-of-thought fragment condemns its entire new chunk. A source that
   looks "half clean" is not half migratable, it is unmigratable.

2. **Did the migration silently drop capabilities?** A green collection can be
   100% clean and still be a downgrade, because the fields that make retrieval
   and citation work do not travel automatically. Measured on 2026-08-02, green
   was missing THIRTEEN payload fields blue had, including the entire
   parent-child triple and PDF page ranges.

Field parity is therefore a first-class check, not a footnote. A clean corpus
that cannot cite a page or resolve a parent is not a better corpus.

Usage
-----
    python -m scripts.ops.corpus_forensics forensic --collection spiritual_wisdom_contextual
    python -m scripts.ops.corpus_forensics forensic --compare-to spiritual_wisdom
    python -m scripts.ops.corpus_forensics feasibility --collection spiritual_wisdom --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
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

_HEADER_RE = re.compile(r"^\[(?:Source|RAPTOR|Context)[^\]]*\]\s*", re.MULTILINE)

# Current practice (2026): child chunks 50-200 tokens against parents of
# 500-1500 tokens. A "parent" shorter than this carries no context its child
# lacks, so it costs storage and buys nothing — worse than absent, because the
# answer path trusts a field that is empty of meaning.
_MIN_USEFUL_PARENT_CHARS = 800

# Migration bands, calibrated on the ONE source actually re-ingested end to end:
# 46.4% blue contamination -> 98.8% post-rechunk rejection. Superlinear, so the
# safe band is narrow and the verdicts are deliberately conservative.
_MIGRATE_CLEAN_MAX = 0.02
_MIGRATE_RISKY_MAX = 0.10

# Fields whose ABSENCE breaks a specific capability, and the CONSUMER that reads
# them. A field with no consumer is bloat, not a capability, however many points
# carry it — the first version of this table listed `important_kwd`,
# `video_id`, `channel_name`, `published_at`, `duration` and `thumbnail_url` as
# lost capabilities on the strength of per-source presence, when a full scan of
# blue showed all six live on SIX points from one source. Reporting those as
# regressions sent the reader after work that restores nothing.
_CAPABILITY_FIELDS: dict[str, tuple[str, ...]] = {
    # searcher.py reads all three onto the doc; retrieval.py swaps parent_text in.
    "parent-child retrieval (small-to-big)": ("parent_id", "parent_text", "is_child"),
    # tree_navigator.py filters leaf search by cluster_id.
    "RAPTOR cluster navigation": ("cluster_id",),
    # PageIndex section id + page span — the only per-chunk page citation there is.
    "PDF page citation": ("page_range", "node_id"),
    # Carried by RAPTOR summaries, which a transcript migration excludes by design.
    "summary provenance (summaries only)": ("source_chunks", "source_urls", "titles"),
}

# Minimum viable citation: without these an answer cannot be attributed at all.
_CITATION_REQUIRED = ("source_url", "title", "chunk_index")
_RETRIEVAL_REQUIRED = ("text", "pooling")

# Earns no retrieval or citation value; costs storage and ingest throughput.
# `phonetic_tokens` in particular is a large per-chunk list, written on every
# point to feed a searcher prefetch that was deleted for latency.
#
# `source_version` was on this list and does NOT belong: retrieval.py's
# pre-rerank dedup keeps the highest source_version for a given source_id+title,
# so it is load-bearing. Verify a consumer is really absent before calling a
# field bloat — pruning a field a ranking path reads is a silent regression.
_KNOWN_BLOAT = ("phonetic_tokens", "original_chunk_count")


def _scroll(client, collection: str, cap: int | None) -> Iterator[dict]:
    offset, seen = None, 0
    while True:
        records, offset = client.scroll(
            collection_name=collection,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for rec in records:
            yield rec.payload or {}
            seen += 1
            if cap and seen >= cap:
                return
        if offset is None:
            return


def _body(text: str) -> str:
    """Strip ingest headers so we judge the teaching, not its wrapper."""
    return _HEADER_RE.sub("", text or "").strip()


def scan(client, collection: str, cap: int | None = None) -> dict[str, Any]:
    """One pass; everything both subcommands need."""
    per_source: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "poisoned": 0, "chars": 0, "samples": []}
    )
    field_presence: Counter[str] = Counter()
    empty_fields: Counter[str] = Counter()
    parent_lens: list[int] = []
    pooling_modes: Counter[str] = Counter()
    norm_texts: Counter[str] = Counter()
    total = 0

    for p in _scroll(client, collection, cap):
        total += 1
        src = p.get("source_url") or p.get("title") or "(unknown)"
        body = _body(p.get("text", ""))
        rec = per_source[src]
        rec["total"] += 1
        rec["chars"] += len(body)

        artifact = find_artifact(body) or find_artifact(p.get("topic") or "")
        if artifact:
            rec["poisoned"] += 1
            if len(rec["samples"]) < 2:
                rec["samples"].append(f"{artifact[:40]} :: {body[:80]}".replace("\n", " "))

        for k, v in p.items():
            field_presence[k] += 1
            if v in ("", None, [], {}):
                empty_fields[k] += 1

        if "parent_text" in p:
            parent_lens.append(len(p.get("parent_text") or ""))
        pooling_modes[str(p.get("pooling") or "(absent)")] += 1
        norm_texts[" ".join(body.split()).casefold()[:400]] += 1

    dups = {t: n for t, n in norm_texts.items() if n > 1 and t}
    return {
        "collection": collection,
        "scanned": total,
        "per_source": dict(per_source),
        "field_presence": dict(field_presence),
        "empty_fields": {k: v for k, v in empty_fields.items() if v},
        "parent_lens": parent_lens,
        "pooling_modes": dict(pooling_modes),
        "duplicate_groups": len(dups),
        "redundant_copies": sum(n - 1 for n in dups.values()),
    }


def field_parity(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """What capabilities did the target collection lose relative to the source?

    Coverage matters as much as presence: a field on 89% of source rows that is
    absent from every target row is a lost capability, while a field on 0.02% of
    source rows is probably an artifact of one ad-hoc script and not worth
    porting. Report both so the reader can tell those apart.
    """
    t_n, s_n = max(target["scanned"], 1), max(source["scanned"], 1)
    t_fields, s_fields = target["field_presence"], source["field_presence"]

    lost = []
    for field, count in sorted(s_fields.items(), key=lambda kv: -kv[1]):
        if field in t_fields:
            continue
        lost.append(
            {
                "field": field,
                "source_coverage": round(count / s_n, 4),
                "source_count": count,
            }
        )

    broken_caps = []
    for capability, fields in _CAPABILITY_FIELDS.items():
        missing = [f for f in fields if f not in t_fields and f in s_fields]
        if missing:
            cov = max((s_fields.get(f, 0) / s_n) for f in missing)
            broken_caps.append(
                {
                    "capability": capability,
                    "missing_fields": missing,
                    "source_coverage": round(cov, 4),
                }
            )
    broken_caps.sort(key=lambda c: -c["source_coverage"])

    return {
        "target": target["collection"],
        "source": source["collection"],
        "lost_fields": lost,
        "broken_capabilities": broken_caps,
        "gained_fields": sorted(set(t_fields) - set(s_fields)),
        "bloat_in_target": [
            {"field": f, "coverage": round(t_fields[f] / t_n, 4)}
            for f in _KNOWN_BLOAT
            if f in t_fields
        ],
    }


def _verdict(rate: float, chunks: int) -> tuple[str, float, list[str]]:
    """Migrate-vs-refetch with an honest confidence.

    Confidence describes the VERDICT, not the contamination measurement. The rate
    is measured exactly; what is uncertain is how it projects through re-chunking,
    and that projection is superlinear and calibrated on a single observed point.
    """
    if chunks == 0:
        return "SKIP", 1.0, ["no chunks"]

    if rate <= _MIGRATE_CLEAN_MAX:
        reasons = [f"contamination {rate:.2%} <= {_MIGRATE_CLEAN_MAX:.0%} (safe band)"]
        if chunks < 50:
            reasons.append(f"only {chunks} chunks — rate is noisy at this sample size")
            return "MIGRATE", 0.75, reasons
        return "MIGRATE", 0.90, reasons

    if rate <= _MIGRATE_RISKY_MAX:
        return (
            "MIGRATE_THEN_VERIFY",
            0.45,
            [
                f"contamination {rate:.2%} sits in the "
                f"{_MIGRATE_CLEAN_MAX:.0%}-{_MIGRATE_RISKY_MAX:.0%} band; re-chunking "
                "amplifies contamination unpredictably here — verify post-write"
            ],
        )

    return (
        "REFETCH_FROM_ORIGIN",
        0.95,
        [
            f"contamination {rate:.2%} > {_MIGRATE_RISKY_MAX:.0%}; the one measured "
            "re-ingest went 46.4% -> 98.8% after re-chunking. Migration cannot clean this."
        ],
    )


def build_forensic(scan_result: dict, parity: dict | None) -> dict[str, Any]:
    total = scan_result["scanned"]
    srcs = scan_result["per_source"]
    poisoned = sum(s["poisoned"] for s in srcs.values())
    plens = scan_result["parent_lens"]
    present = set(scan_result["field_presence"])

    parent_health: dict[str, Any] = {"present": bool(plens)}
    if plens:
        useless = sum(1 for L in plens if L < _MIN_USEFUL_PARENT_CHARS)
        parent_health.update(
            {
                "median_chars": statistics.median(plens),
                "unusable": useless,
                "unusable_rate": round(useless / len(plens), 4),
                "target_min_chars": _MIN_USEFUL_PARENT_CHARS,
            }
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "collection": scan_result["collection"],
        "scanned": total,
        "sources": len(srcs),
        "contamination": {
            "poisoned": poisoned,
            "rate": round(poisoned / total, 4) if total else 0.0,
        },
        "duplication": {
            "groups": scan_result["duplicate_groups"],
            "redundant_copies": scan_result["redundant_copies"],
        },
        "parent_child": parent_health,
        "citation_readiness": {
            "missing": [f for f in _CITATION_REQUIRED if f not in present],
            "ready": all(f in present for f in _CITATION_REQUIRED),
        },
        "retrieval_readiness": {
            "missing": [f for f in _RETRIEVAL_REQUIRED if f not in present],
            "pooling_modes": scan_result["pooling_modes"],
            "pooling_mixed": len([m for m in scan_result["pooling_modes"] if m != "(absent)"]) > 1,
        },
        "metadata_hygiene": {
            "bloat_present": [f for f in _KNOWN_BLOAT if f in present],
            "always_empty": {k: v for k, v in scan_result["empty_fields"].items() if v == total},
        },
    }
    if parity:
        report["field_parity"] = parity
    return report


def build_feasibility(scan_result: dict) -> dict[str, Any]:
    rows = []
    for src, s in scan_result["per_source"].items():
        rate = s["poisoned"] / s["total"] if s["total"] else 0.0
        verdict, conf, reasons = _verdict(rate, s["total"])
        rows.append(
            {
                "source_url": src,
                "chunks": s["total"],
                "poisoned": s["poisoned"],
                "contamination_rate": round(rate, 4),
                "verdict": verdict,
                "confidence": conf,
                "reasons": reasons,
                "samples": s["samples"],
            }
        )
    rows.sort(key=lambda r: (-r["contamination_rate"], -r["chunks"]))
    tally = Counter(r["verdict"] for r in rows)
    migratable = [r for r in rows if r["verdict"] == "MIGRATE"]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "collection": scan_result["collection"],
        "total_sources": len(rows),
        "verdicts": dict(tally),
        "migratable_sources": len(migratable),
        "migratable_chunks": sum(r["chunks"] for r in migratable),
        "total_chunks": sum(r["chunks"] for r in rows),
        "bulk_reingest_all_sources": tally.get("REFETCH_FROM_ORIGIN", 0) == 0,
        "sources": rows,
    }


def _print_forensic(r: dict) -> None:
    print(f"\ncollection  : {r['collection']}")
    print(f"scanned     : {r['scanned']:,} chunks across {r['sources']} sources")
    c = r["contamination"]
    print(f"CONTAMINATED: {c['poisoned']:,} ({100 * c['rate']:.1f}%)")
    d = r["duplication"]
    print(f"duplication : {d['redundant_copies']:,} redundant copies / {d['groups']:,} groups")

    pc = r["parent_child"]
    print("\nparent-child (small-to-big retrieval):")
    if not pc["present"]:
        print("  ABSENT — no parent_text. Every chunk is served without surrounding")
        print("  context; the documented Parent-Child Retrieval path is dead here.")
    else:
        print(
            f"  median parent {pc['median_chars']:.0f} chars (target >= {pc['target_min_chars']})"
        )
        print(
            f"  UNUSABLE: {pc['unusable']:,} ({100 * pc['unusable_rate']:.1f}%) shorter than target"
        )

    cr, rr = r["citation_readiness"], r["retrieval_readiness"]
    print(
        f"\ncitation-ready: {'YES' if cr['ready'] else 'NO — missing ' + ', '.join(cr['missing'])}"
    )
    if rr["missing"]:
        print(f"retrieval gaps : missing {', '.join(rr['missing'])}")
    if rr["pooling_mixed"]:
        print(f"  !! MIXED POOLING {rr['pooling_modes']} — mean and CLS vectors sit ~0.757")
        print("     cosine apart; mixing them corrupts ranking on every query.")

    mh = r["metadata_hygiene"]
    if mh["bloat_present"]:
        print(f"\nmetadata bloat : {', '.join(mh['bloat_present'])}")
    if mh["always_empty"]:
        print(f"always-empty   : {', '.join(mh['always_empty'])}")

    fp = r.get("field_parity")
    if fp:
        print(f"\n=== FIELD PARITY vs {fp['source']} ===")
        if fp["broken_capabilities"]:
            print("CAPABILITIES LOST:")
            for cap in fp["broken_capabilities"]:
                print(f"  {100 * cap['source_coverage']:5.1f}% src coverage  {cap['capability']}")
                print(f"         missing: {', '.join(cap['missing_fields'])}")
        else:
            print("  no capability-bearing field lost")
        if fp["bloat_in_target"]:
            b = ", ".join(
                f"{x['field']} ({100 * x['coverage']:.0f}%)" for x in fp["bloat_in_target"]
            )
            print(f"BLOAT CARRIED FORWARD: {b}")


def _print_feasibility(r: dict, top: int) -> None:
    print(f"\ncollection : {r['collection']}")
    print(f"sources    : {r['total_sources']}")
    print("\nverdicts:")
    for v, n in sorted(r["verdicts"].items(), key=lambda kv: -kv[1]):
        print(f"  {n:5}  {v}")
    pct = 100 * r["migratable_chunks"] / max(r["total_chunks"], 1)
    print(
        f"\nmigratable : {r['migratable_sources']}/{r['total_sources']} sources, "
        f"{r['migratable_chunks']:,}/{r['total_chunks']:,} chunks ({pct:.1f}%)"
    )
    print(
        f"\nCAN WE BULK RE-INGEST EVERYTHING?  {'YES' if r['bulk_reingest_all_sources'] else 'NO'}"
    )
    if not r["bulk_reingest_all_sources"]:
        n = r["verdicts"].get("REFETCH_FROM_ORIGIN", 0)
        print(f"  {n} source(s) exceed the migration ceiling. Re-chunking AMPLIFIES")
        print("  contamination (measured 46.4% -> 98.8%), so migrating them yields")
        print("  near-total rejection. Those need re-fetching from origin.")

    worst = [s for s in r["sources"] if s["verdict"] != "MIGRATE"][:top]
    if worst:
        print(f"\ntop {len(worst)} problem sources:")
        for s in worst:
            print(
                f"  {100 * s['contamination_rate']:5.1f}%  {s['chunks']:5}ch  conf={s['confidence']:.2f}"
                f"  {s['verdict']:20} {s['source_url'][:50]}"
            )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Corpus forensics (read-only).")
    ap.add_argument("mode", choices=("forensic", "feasibility"))
    ap.add_argument("--collection", default=None)
    ap.add_argument(
        "--compare-to", default=None, help="forensic mode: source collection for field-parity check"
    )
    ap.add_argument("--url", default=None)
    ap.add_argument("--sample", type=int, default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args(argv)

    collection, url = args.collection, args.url
    if not collection or not url:
        from app.config import settings

        collection = collection or settings.qdrant_collection
        url = url or settings.qdrant_url

    from qdrant_client import QdrantClient

    client = QdrantClient(url=url.rstrip("/"))
    result = scan(client, collection, args.sample)

    if args.mode == "forensic":
        parity = None
        if args.compare_to:
            parity = field_parity(result, scan(client, args.compare_to, args.sample))
        report = build_forensic(result, parity)
        _print_forensic(report)
    else:
        report = build_feasibility(result)
        _print_feasibility(report, args.top)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
