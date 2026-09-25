#!/usr/bin/env python3
"""Read-only nightly data-quality audit — the data gate for the transcript
corpus, the OKF doctrine bundle, and the live Qdrant collection.

See backend/CLAUDE.md's "#1 priority" banner: "The data gate is
scripts/ops/data_quality_audit.py." This is that gate.

Read-only: it never writes to scripts/ingestion/corpus/, memory/okf/, or
Qdrant. It writes only its own JSON report under backend/reports/.

Checks
------
  * corpus   — services.transcript_verbatim.per_video_checks over every
               video directory (empty/malformed segments, repetition loops,
               missing verbatim/timestamp/confidence layers).
  * okf      — quoted strings (>=8 words) in every live OKF entry, checked
               against that entry's own video_id via find_verbatim
               (verbatim / partial / fabricated); "Unknown"-attributed
               quotes; duplicate filenames across teacher subdirectories.
  * qdrant   — teacher-tag sanity (external-teacher tags, which should be
               zero absent a registered external source), video_id/summary
               point counts, timestamp presence. Degrades to "skipped" with
               a clear reason if Qdrant is unreachable, rather than crashing.
  * coverage — corpus video_ids with no matching Qdrant points, and vice
               versa (points whose video_id has no local corpus directory).

Thresholds are regression guards pinned to the 2026-09-24 measured baseline
(see each Thresholds field's docstring) — they intentionally do not require
today's real, already-known defects to instantly clear. Use --strict to
demand zero on everything instead.

Usage
-----
    .venv/bin/python -m scripts.ops.data_quality_audit
    .venv/bin/python -m scripts.ops.data_quality_audit --json backend/reports/data_quality_2026-09-24.json
    .venv/bin/python -m scripts.ops.data_quality_audit --skip-qdrant
    .venv/bin/python -m scripts.ops.data_quality_audit --strict
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_REPO_ROOT = _BACKEND.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ops.corpus_audit import _scroll, _validate_qdrant_base_url  # noqa: E402
from services.memory.okf_store import OKFStore  # noqa: E402
from services.transcript_verbatim import (  # noqa: E402
    CORPUS_ROOT,
    find_verbatim,
    has_hard_failure,
    per_video_checks,
)

logger = logging.getLogger("data_quality_audit")

REPORTS_DIR = _BACKEND / "reports"
_QUOTE_RE = re.compile(r'"([^"\n]{20,400})"')
_MIN_QUOTE_WORDS = 8
_UNKNOWN_ATTRIBUTION_RE = re.compile(r'"\s*(?:—|-)\s*Unknown\b', re.IGNORECASE)
_EXTERNAL_TEACHER_TAG_PREFIXES = ("teacher:sadhguru", "teacher:amma_bhagavan", "teacher:iskcon")


@dataclass
class Thresholds:
    """Regression guards, not aspirational targets. Each default is the
    2026-09-24 measured baseline (see root CLAUDE.md's data-quality audit
    numbers) plus a little slack — a nightly run should fail on a NEW
    regression, not on a debt item that is already tracked elsewhere.
    ``--strict`` zeroes every one of these out."""

    max_corpus_hard_failure_rate: float = 0.05
    max_okf_not_found_rate: float = 0.60  # measured 2026-09-24: ~0.52
    max_okf_duplicate_pairs: int = 45  # measured: 40
    max_qdrant_external_teacher_tags: int = 3200  # measured: 3121 (another agent's fix, in flight)
    max_qdrant_missing_video_id: int = 4900  # measured: 4818
    max_qdrant_orphaned_video_ids: int = 1700  # measured: 1662 (points from videos with no corpus dir)

    @classmethod
    def strict(cls) -> "Thresholds":
        return cls(0.0, 0.0, 0, 0, 0, 0)


@dataclass
class Check:
    name: str
    severity: str  # "hard" | "soft"
    passed: bool
    value: Any
    threshold: Any
    detail: str = ""


@dataclass
class AuditReport:
    generated_at: str
    corpus: dict = field(default_factory=dict)
    okf: dict = field(default_factory=dict)
    qdrant: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    exit_code: int = 0


# ── corpus ───────────────────────────────────────────────────────────────


def audit_corpus(corpus_root: Path) -> dict:
    if not corpus_root.is_dir():
        return {"video_count": 0, "error": f"corpus root not found: {corpus_root}"}

    video_dirs = sorted(p for p in corpus_root.iterdir() if p.is_dir())
    finding_counts: Counter[str] = Counter()
    videos_with_hard = 0
    hard_examples: list[dict] = []

    for v_dir in video_dirs:
        findings = per_video_checks(v_dir)
        for f in findings:
            finding_counts[f.check] += 1
        if has_hard_failure(findings):
            videos_with_hard += 1
            if len(hard_examples) < 20:
                hard_examples.append(
                    {
                        "video_id": v_dir.name,
                        "reasons": [f"{f.check}: {f.detail}" for f in findings if f.severity == "hard"],
                    }
                )

    n = len(video_dirs)
    return {
        "video_count": n,
        "videos_with_hard_failure": videos_with_hard,
        "hard_failure_rate": round(videos_with_hard / n, 4) if n else 0.0,
        "finding_counts": dict(finding_counts),
        "hard_failure_examples": hard_examples,
    }


# ── OKF ──────────────────────────────────────────────────────────────────


def _okf_quotes(body: str) -> list[str]:
    return [q for q in _QUOTE_RE.findall(body) if len(q.split()) >= _MIN_QUOTE_WORDS]


def audit_okf(corpus_root: Path, okf_dir: Optional[Path] = None) -> dict:
    entries = OKFStore(okf_dir).list_entries()
    status_counts: Counter[str] = Counter()
    unknown_attribution = 0
    total_quotes = 0
    fabricated_examples: list[dict] = []

    for entry in entries:
        video_id = entry.meta.get("video_id")
        quotes = _okf_quotes(entry.body)
        total_quotes += len(quotes)
        for quote in quotes:
            result = find_verbatim(quote, video_id=video_id, corpus_root=corpus_root)
            status_counts[result["status"]] += 1
            if result["status"] == "not_found" and len(fabricated_examples) < 20:
                fabricated_examples.append(
                    {"file": entry.path.name, "video_id": video_id, "quote": quote[:120]}
                )
        if _UNKNOWN_ATTRIBUTION_RE.search(entry.body):
            unknown_attribution += 1

    by_name: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        by_name[entry.path.name].append(str(entry.path))
    duplicate_groups = {k: v for k, v in by_name.items() if len(v) > 1}

    not_found_rate = status_counts["not_found"] / total_quotes if total_quotes else 0.0
    return {
        "entry_count": len(entries),
        "quotes_checked": total_quotes,
        "verbatim": status_counts["verbatim"],
        "partial": status_counts["partial"],
        "not_found": status_counts["not_found"],
        "not_found_rate": round(not_found_rate, 4),
        "unknown_attribution_count": unknown_attribution,
        "duplicate_filename_pairs": len(duplicate_groups),
        "duplicate_examples": list(duplicate_groups.keys())[:10],
        "fabricated_examples": fabricated_examples,
    }


# ── Qdrant ───────────────────────────────────────────────────────────────


def audit_qdrant(base_url: str, collection: str, cap: Optional[int]) -> dict:
    total = 0
    with_video_id = 0
    summary_points = 0
    with_timestamps = 0
    external_teacher_tags = 0
    speaker_known = 0
    video_ids: set[str] = set()

    try:
        base_url = _validate_qdrant_base_url(base_url)
        for payload in _scroll(base_url, collection, 500, cap):
            total += 1
            vid = payload.get("video_id")
            if vid:
                with_video_id += 1
                video_ids.add(vid)
            if payload.get("content_type") == "summary":
                summary_points += 1
            if payload.get("start") is not None and payload.get("end") is not None:
                with_timestamps += 1
            tags = payload.get("tags") or []
            if any(t in tags for t in _EXTERNAL_TEACHER_TAG_PREFIXES):
                external_teacher_tags += 1
            speaker = payload.get("speaker")
            if speaker and speaker not in ("Unknown", "Unknown Channel"):
                speaker_known += 1
    except Exception as exc:
        logger.warning("Qdrant audit could not complete: %s", exc)
        return {"skipped": True, "reason": str(exc)}

    return {
        "skipped": False,
        "total_points": total,
        "with_video_id": with_video_id,
        "without_video_id": total - with_video_id,
        "summary_points": summary_points,
        "with_timestamps": with_timestamps,
        "timestamp_coverage_rate": round(with_timestamps / total, 4) if total else 0.0,
        "external_teacher_tag_count": external_teacher_tags,
        "speaker_known_rate": round(speaker_known / total, 4) if total else 0.0,
        "distinct_video_ids": sorted(video_ids),
    }


# ── coverage ─────────────────────────────────────────────────────────────


def audit_coverage(corpus_root: Path, qdrant_video_ids: Optional[list[str]]) -> dict:
    if qdrant_video_ids is None:
        return {"skipped": True, "reason": "qdrant audit was skipped"}
    corpus_ids = {p.name for p in corpus_root.iterdir() if p.is_dir()} if corpus_root.is_dir() else set()
    qdrant_ids = set(qdrant_video_ids)
    not_yet_ingested = corpus_ids - qdrant_ids
    orphaned = qdrant_ids - corpus_ids
    return {
        "corpus_video_count": len(corpus_ids),
        "qdrant_distinct_video_count": len(qdrant_ids),
        "corpus_not_in_qdrant": len(not_yet_ingested),
        "qdrant_video_ids_without_corpus_dir": len(orphaned),
        "orphaned_examples": sorted(orphaned)[:20],
    }


# ── orchestration ────────────────────────────────────────────────────────


def _check(name: str, severity: str, value, threshold, passed: bool, detail: str = "") -> Check:
    return Check(name=name, severity=severity, passed=passed, value=value, threshold=threshold, detail=detail)


def run_audit(
    corpus_root: Path,
    qdrant_url: Optional[str],
    qdrant_collection: Optional[str],
    thresholds: Thresholds,
    skip_qdrant: bool,
    qdrant_cap: Optional[int],
    okf_dir: Optional[Path] = None,
) -> AuditReport:
    report = AuditReport(generated_at=datetime.now(timezone.utc).isoformat())

    report.corpus = audit_corpus(corpus_root)
    report.okf = audit_okf(corpus_root, okf_dir)

    if skip_qdrant:
        report.qdrant = {"skipped": True, "reason": "--skip-qdrant"}
    else:
        from app.config import settings

        report.qdrant = audit_qdrant(
            qdrant_url or settings.qdrant_url, qdrant_collection or settings.qdrant_collection, qdrant_cap
        )

    report.coverage = audit_coverage(
        corpus_root, report.qdrant.get("distinct_video_ids") if not report.qdrant.get("skipped") else None
    )

    checks: list[Check] = []
    if "error" in report.corpus:
        checks.append(_check("corpus_readable", "hard", False, True, False, report.corpus["error"]))
    else:
        checks.append(_check("corpus_has_videos", "hard", report.corpus["video_count"], 1, report.corpus["video_count"] > 0))
        checks.append(
            _check(
                "corpus_hard_failure_rate",
                "hard",
                report.corpus["hard_failure_rate"],
                thresholds.max_corpus_hard_failure_rate,
                report.corpus["hard_failure_rate"] <= thresholds.max_corpus_hard_failure_rate,
            )
        )
    checks.append(
        _check(
            "okf_not_found_rate",
            "soft",
            report.okf["not_found_rate"],
            thresholds.max_okf_not_found_rate,
            report.okf["not_found_rate"] <= thresholds.max_okf_not_found_rate,
            "quoted strings (>=8 words) find_verbatim could not confirm are the teacher's actual words",
        )
    )
    checks.append(
        _check(
            "okf_duplicate_filename_pairs",
            "soft",
            report.okf["duplicate_filename_pairs"],
            thresholds.max_okf_duplicate_pairs,
            report.okf["duplicate_filename_pairs"] <= thresholds.max_okf_duplicate_pairs,
        )
    )
    if not report.qdrant.get("skipped"):
        checks.append(
            _check(
                "qdrant_external_teacher_tags",
                "hard",
                report.qdrant["external_teacher_tag_count"],
                thresholds.max_qdrant_external_teacher_tags,
                report.qdrant["external_teacher_tag_count"] <= thresholds.max_qdrant_external_teacher_tags,
                "sadhguru/amma_bhagavan/iskcon tags with no source registered to them (services.teacher_attribution.EXTERNAL_TEACHER_SOURCE_REGISTRY)",
            )
        )
        checks.append(
            _check(
                "qdrant_missing_video_id",
                "soft",
                report.qdrant["without_video_id"],
                thresholds.max_qdrant_missing_video_id,
                report.qdrant["without_video_id"] <= thresholds.max_qdrant_missing_video_id,
            )
        )
        if not report.coverage.get("skipped"):
            checks.append(
                _check(
                    "qdrant_orphaned_video_ids",
                    "soft",
                    report.coverage["qdrant_video_ids_without_corpus_dir"],
                    thresholds.max_qdrant_orphaned_video_ids,
                    report.coverage["qdrant_video_ids_without_corpus_dir"]
                    <= thresholds.max_qdrant_orphaned_video_ids,
                )
            )
    else:
        checks.append(_check("qdrant_reachable", "soft", False, True, False, report.qdrant.get("reason", "")))

    report.checks = [asdict(c) for c in checks]
    report.exit_code = 1 if any(not c.passed and c.severity == "hard" for c in checks) else 0
    return report


def print_summary(report: AuditReport) -> None:
    print("=" * 72)
    print(f"Data quality audit — {report.generated_at}")
    print("=" * 72)
    c = report.corpus
    if "error" in c:
        print(f"CORPUS: ERROR — {c['error']}")
    else:
        print(
            f"CORPUS:  {c['video_count']} videos, "
            f"{c['videos_with_hard_failure']} with a hard finding ({c['hard_failure_rate']:.1%})"
        )
        if c["finding_counts"]:
            print(f"         finding counts: {c['finding_counts']}")
    o = report.okf
    print(
        f"OKF:     {o['entry_count']} live entries, {o['quotes_checked']} quotes checked — "
        f"verbatim={o['verbatim']} partial={o['partial']} not_found={o['not_found']} "
        f"({o['not_found_rate']:.1%} not found)"
    )
    print(f"         unknown-attributed quotes: {o['unknown_attribution_count']}")
    print(f"         duplicate filename pairs: {o['duplicate_filename_pairs']}")
    q = report.qdrant
    if q.get("skipped"):
        print(f"QDRANT:  SKIPPED — {q.get('reason')}")
    else:
        print(
            f"QDRANT:  {q['total_points']} points, {q['without_video_id']} without video_id, "
            f"{q['summary_points']} summary points, timestamp coverage {q['timestamp_coverage_rate']:.1%}, "
            f"external-teacher tags: {q['external_teacher_tag_count']}"
        )
    cov = report.coverage
    if not cov.get("skipped"):
        print(
            f"COVERAGE: {cov['corpus_not_in_qdrant']} corpus videos not yet in Qdrant, "
            f"{cov['qdrant_video_ids_without_corpus_dir']} Qdrant video_ids with no corpus dir"
        )
    print("-" * 72)
    for check in report.checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"[{status}] ({check['severity']}) {check['name']}: {check['value']} (threshold {check['threshold']})")
    print("-" * 72)
    print(f"exit_code={report.exit_code}")


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-root", type=Path, default=CORPUS_ROOT)
    parser.add_argument("--okf-dir", type=Path, default=None, help="OKF bundle dir (default: services.memory.okf_store.OKF_DIR)")
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--qdrant-collection", default=None)
    parser.add_argument("--qdrant-cap", type=int, default=None, help="cap points scrolled (testing only)")
    parser.add_argument("--skip-qdrant", action="store_true")
    parser.add_argument("--strict", action="store_true", help="zero-tolerance thresholds instead of baseline-guard defaults")
    parser.add_argument("--json", type=Path, default=None, help="report path (default: backend/reports/data_quality_<date>.json)")
    parser.add_argument("--max-corpus-hard-failure-rate", type=float, default=None)
    parser.add_argument("--max-okf-not-found-rate", type=float, default=None)
    args = parser.parse_args(argv)

    thresholds = Thresholds.strict() if args.strict else Thresholds()
    if args.max_corpus_hard_failure_rate is not None:
        thresholds.max_corpus_hard_failure_rate = args.max_corpus_hard_failure_rate
    if args.max_okf_not_found_rate is not None:
        thresholds.max_okf_not_found_rate = args.max_okf_not_found_rate

    report = run_audit(
        corpus_root=args.corpus_root,
        qdrant_url=args.qdrant_url,
        qdrant_collection=args.qdrant_collection,
        thresholds=thresholds,
        skip_qdrant=args.skip_qdrant,
        qdrant_cap=args.qdrant_cap,
        okf_dir=args.okf_dir,
    )
    print_summary(report)

    out_path = args.json
    if out_path is None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = REPORTS_DIR / f"data_quality_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Report written to {out_path}")

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
