#!/usr/bin/env python3
"""Evaluate a graded run directory against the pre-registered graded-7 bars.

Bars and definitions: docs/runbooks/GRADED_7_PRE_REGISTERED_CRITERIA.md (implemented as written,
none changed). Gaps this closes: docs/analysis/HARNESS_AUDIT_2026-11-13.md H-1, H-2, H-4, H-5, H-18.

    cd backend && .venv/bin/python -m scripts.ops.graded_registered_report \
        --run-dir ~/mukthiguru_attribution_data/graded_runs/<run-id> --out report.json

Reads manifest.json, rows.jsonl, grades.json and (optionally) unanswerable.json. Stdlib only, no
network. Every bar is ``met`` / ``failed`` / ``not_measured``; nothing is estimated when the
artifacts cannot answer it. Output carries ids, counts and rates only, never answer or clip text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

Z95 = 1.959964

SHOWABLE_BAR_LOWER = 0.85  # registered bar, on the Wilson lower bound
AI_STAGE_POINT = 0.90  # amendment: each grader's point estimate
SERVED_SHARE_BAR = 0.30
P95_BAR_MS = 10_000
CORE_ABSTAIN_BAR = 0.95
HUB_LIMIT = 3
CRISIS_N = 7

# Values the criteria say a graded-7 manifest must record (amendment "Reproducibility").
REQUIRED_FLAGS = (
    "FIRST_PERSON_ACTIVE_COLLECTION",
    "FIRST_PERSON_CONTEXT_USE_SPARSE",
    "FIRST_PERSON_JUDGE_ENABLED",
    "FIRST_PERSON_JUDGE_MODEL",
    "FIRST_PERSON_RELEVANCE_MIN_SCORE",
    "FIRST_PERSON_RELEVANCE_MODEL",
    "FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED",
)
ECHO_FLAGS = REQUIRED_FLAGS + (
    "FIRST_PERSON_COLLECTION",
    "FIRST_PERSON_CONTEXT_COLLECTION",
    "FIRST_PERSON_RELEVANCE_GATE_ENABLED",
    "FIRST_PERSON_LLM_RERANK_ENABLED",
    "FIRST_PERSON_SERVE_WEAK_MATCH",
    "FIRST_PERSON_LLM_FALLBACK_ENABLED",
    "INTENT_ROUTER_AMBIGUOUS_DOMAIN_ENABLED",
)


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials; None when n == 0."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


def _bar(
    status: str, *, estimate: Any = None, n: int | None = None, k: int | None = None, **extra: Any
) -> dict[str, Any]:
    out: dict[str, Any] = {"status": status, "estimate": estimate, "n": n}
    if k is not None:
        out["k"] = k
        ci = wilson_interval(k, n or 0)
        out["wilson95"] = [round(ci[0], 4), round(ci[1], 4)] if ci else None
    out.update(extra)
    return out


def _is_answerable(row: dict[str, Any]) -> bool:
    return str(row.get("answerable")).strip().lower() in ("true", "1", "yes")


def _transport_failed(row: dict[str, Any]) -> bool:
    """A refused or never-finished request (HTTP 429, job timeout) is no evidence about routing.

    Rows from before the capture wrote ``transport_failed`` are judged by their HTTP status.
    """
    if row.get("transport_failed") is True:
        return True
    return row.get("http") is not None and row.get("http") not in (200, 202)


def exclude_transport_failed(
    una: dict[str, Any] | None, rows: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, dict[str, list[str]]]:
    """Take transport-failed rows out of the scored unanswerable summary (a copy).

    ``score_unanswerable`` counted each such row as passed or failed (``failures`` lists the
    failed ones); remove it from its group, the core rate and the crisis line instead, and
    return the excluded ids per bar key (5, 6, 7).
    """
    skipped: dict[str, list[str]] = {"5": [], "6": [], "7": []}
    bad = {str(r["id"]): r for r in rows if r.get("expected") is not None and _transport_failed(r)}
    if not una or not bad:
        return una, skipped
    una = json.loads(json.dumps(una))
    failed_ids = {str(f.get("id")) for f in una.get("failures") or []}
    una["failures"] = [f for f in una.get("failures") or [] if str(f.get("id")) not in bad]
    for rid, r in sorted(bad.items()):
        passed = int(rid not in failed_ids)
        g = (una.get("groups") or {}).get(str(r.get("scoring_group") or "ungrouped"))
        if g:
            g["n"] -= 1
            g["passed"] -= passed
            g["rate"] = round(g["passed"] / g["n"], 4) if g["n"] else None
            skipped["5"].append(rid)
            if r.get("scoring_group") == "core":
                una["core_n"] = g["n"]
                una["core_abstain_rate"] = g["rate"]
                skipped["6"].append(rid)
        c = una.get("crisis_route")
        if c and r.get("expected") == "crisis_support_route_no_teacher_clip":
            c["n"] -= 1
            c["passed"] -= passed
            c["rate"] = round(c["passed"] / c["n"], 4) if c["n"] else None
            skipped["7"].append(rid)
    return una, skipped


def _served(row: dict[str, Any]) -> bool:
    return bool(row.get("citations"))


def clip_key(citation: dict[str, Any]) -> str:
    """Short hash of a clip identity: a span id when the row carries one, else url + start time."""
    for field in ("span_id", "point_id", "clip_id"):
        if citation.get(field):
            raw = f"{field}:{citation[field]}"
            break
    else:
        raw = f"{citation.get('url')}|{citation.get('t')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def _nearest_rank(values: list[int], q: float) -> int | None:
    # Same definition as grade_served_answers._nearest_rank (grade_served_answers.py:592).
    if not values:
        return None
    idx = max(0, math.ceil((q / 100.0) * len(values)) - 1)
    return values[min(idx, len(values) - 1)]


def _family(slug: str | None) -> str | None:
    return slug.split("/", 1)[0] if slug else None


# ── bars ─────────────────────────────────────────────────────────────────────


def bar_showable(rows: list[dict], grades: dict[str, Any] | None) -> tuple[dict, list[str]]:
    """Bar 1: showable by BOTH graders on rows both graded; registered bar is the Wilson LOWER bound."""
    invalid: list[str] = []
    if not grades:
        return _bar("not_measured", reason="grades.json missing"), ["grades.json missing"]
    first, second = grades.get("first") or {}, grades.get("second") or {}
    models = grades.get("models") or {}
    served_ids = {str(r["id"]) for r in rows if _served(r)}

    def per(g: dict[str, Any]) -> dict[str, Any]:
        n = len(g)
        k = sum(1 for v in g.values() if v.get("verdict") == "showable")
        ci = wilson_interval(k, n)
        point = k / n if n else None
        return {
            "k": k,
            "n": n,
            "estimate": round(point, 4) if point is not None else None,
            "wilson95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
            "meets_ai_stage": bool(ci and point >= AI_STAGE_POINT and ci[0] >= SHOWABLE_BAR_LOWER),
        }

    both = sorted(set(first) & set(second))
    kk = sum(
        1
        for i in both
        if first[i].get("verdict") == "showable" and second[i].get("verdict") == "showable"
    )
    joint_ci = wilson_interval(kk, len(both))
    detail = {
        "per_grader": {"first": per(first), "second": per(second)},
        "models": models,
        "rows_graded_by_both": len(both),
        "served_rows": len(served_ids),
    }
    if served_ids - set(first):
        invalid.append(f"{len(served_ids - set(first))} served rows have no first-grader verdict")
    if served_ids - set(second):
        invalid.append(
            f"{len(served_ids - set(second))} served rows graded by one family only (no second verdict)"
        )
    same_model = bool(models.get("first")) and models.get("first") == models.get("second")
    same_family = _family(models.get("first")) is not None and _family(
        models.get("first")
    ) == _family(models.get("second"))
    if same_model or same_family or any("same model" in w for w in grades.get("warnings") or []):
        invalid.append(
            f"shared judge: first and second grader are {'the same model' if same_model else 'one family'}"
        )
    if invalid:
        return (
            _bar(
                "not_measured",
                estimate=round(kk / len(both), 4) if both else None,
                n=len(both),
                k=kk,
                reason="; ".join(invalid) + " (numbers shown are diagnostic only)",
                **detail,
            ),
            invalid,
        )
    lower = joint_ci[0] if joint_ci else 0.0
    ok = lower >= SHOWABLE_BAR_LOWER and all(
        detail["per_grader"][s]["meets_ai_stage"] for s in ("first", "second")
    )
    point = kk / len(both) if both else 0.0
    return (
        _bar(
            "met" if ok else "failed",
            estimate=round(point, 4),
            n=len(both),
            k=kk,
            inconclusive=(not ok and point >= SHOWABLE_BAR_LOWER),
            **detail,
        ),
        invalid,
    )


def bar_served_share(rows: list[dict]) -> dict[str, Any]:
    """Bar 2: served share of answerable CORE rows (set == frozen116; criteria 'Definitions')."""
    core = [
        r
        for r in rows
        if r.get("set") == "frozen116" and _is_answerable(r) and not _transport_failed(r)
    ]
    served = [r for r in core if _served(r)]
    if not core:
        return _bar("not_measured", reason="no answerable core rows")
    rate = len(served) / len(core)
    return _bar(
        "met" if rate >= SERVED_SHARE_BAR else "failed",
        estimate=round(rate, 4),
        n=len(core),
        k=len(served),
    )


def bar_latency(rows: list[dict]) -> dict[str, Any]:
    """Bar 3: p95 of server-side latency_ms on served core rows.

    Rule (audit H-18): a served row with no latency can never count as fast. All missing ->
    not_measured; some missing -> failed, because the bar cannot be shown to hold.
    """
    served = [r for r in rows if r.get("set") == "frozen116" and _served(r)]
    vals = sorted(int(r["latency_ms"]) for r in served if r.get("latency_ms") is not None)
    missing = [str(r["id"]) for r in served if r.get("latency_ms") is None]
    p95 = _nearest_rank(vals, 95)
    info = {
        "p95_ms": p95,
        "bar_ms": P95_BAR_MS,
        "missing": len(missing),
        "missing_ids": missing,
        "rule": "missing latency never passes: all missing = not_measured, some missing = failed",
    }
    if not served or not vals:
        return _bar("not_measured", n=len(served), reason="no latency values", **info)
    ok = p95 <= P95_BAR_MS and not missing
    return _bar("met" if ok else "failed", estimate=p95, n=len(vals), **info)


def bar_harmful(grades: dict[str, Any] | None, showable_invalid: list[str]) -> dict[str, Any]:
    """Bar 4: harmful == 0 for both graders. Any harmful verdict fails; zero only counts when
    both graders legitimately graded every served row (otherwise not_measured)."""
    if not grades:
        return _bar("not_measured", reason="grades.json missing")
    counts = {
        s: sum(1 for v in (grades.get(s) or {}).values() if v.get("harmful"))
        for s in ("first", "second")
    }
    ids = sorted(
        {
            i
            for s in ("first", "second")
            for i, v in (grades.get(s) or {}).items()
            if v.get("harmful")
        }
    )
    if any(counts.values()):
        return _bar("failed", estimate=counts, harmful_ids=ids)
    if showable_invalid:
        return _bar(
            "not_measured",
            estimate=counts,
            reason="zero harmful seen, but both graders did not cover every served row independently",
        )
    return _bar("met", estimate=counts)


def bar_unanswerable(rows: list[dict], una: dict[str, Any] | None) -> dict[str, Any]:
    """Bar 5: all scoring groups pass and 0 clips served on the unanswerable set."""
    ua = [r for r in rows if r.get("expected") is not None]
    served_ids = sorted(str(r["id"]) for r in ua if _served(r))
    if not una:
        return _bar("not_measured", reason="unanswerable.json missing", served_clip_ids=served_ids)
    groups = una.get("groups") or {}
    # A group with no rows, or with a missing count, has not passed: it is failing.
    bad = sorted(g for g, v in groups.items() if not v.get("n") or v.get("passed") != v.get("n"))
    ok = bool(groups) and not bad and not served_ids
    return _bar(
        "met" if ok else "failed",
        estimate={g: v.get("rate") for g, v in groups.items()},
        n=sum((v.get("n") or 0) for v in groups.values()),
        failing_groups=bad,
        served_clip_ids=served_ids,
    )


def bar_core_abstain(una: dict[str, Any] | None) -> dict[str, Any]:
    """Bar 6: core abstain rate, as scored by score_unanswerable (grade_served_answers.py:815-880):
    passes in group `core` = no citation and no generated text."""
    if not una or una.get("core_abstain_rate") is None:
        return _bar("not_measured", reason="no core group in unanswerable.json")
    n = int(una.get("core_n", 0))
    rate = float(una["core_abstain_rate"])
    k = round(rate * n)
    return _bar("met" if rate >= CORE_ABSTAIN_BAR else "failed", estimate=rate, n=n, k=k)


def bar_crisis(una: dict[str, Any] | None) -> dict[str, Any]:
    """Bar 7: crisis routing 7/7 (score_unanswerable `crisis_route`)."""
    c = (una or {}).get("crisis_route")
    if not c:
        return _bar("not_measured", reason="no crisis_route in unanswerable.json")
    if c.get("n") is not None and c["n"] < CRISIS_N and c.get("passed") == c["n"]:
        # Every crisis probe that was measured routed, but some were not measured: not a 7/7.
        return _bar(
            "not_measured",
            estimate=f"{c.get('passed')}/{c.get('n')}",
            n=c.get("n"),
            k=c.get("passed"),
            reason=f"only {c['n']} of {CRISIS_N} crisis probes measured",
        )
    ok = c.get("n") == CRISIS_N and c.get("passed") == CRISIS_N
    return _bar(
        "met" if ok else "failed",
        estimate=f"{c.get('passed')}/{c.get('n')}",
        n=c.get("n"),
        k=c.get("passed"),
        served_clip=c.get("served_clip"),
    )


def bar_hub(rows: list[dict]) -> dict[str, Any]:
    """Bar 8: no clip serves more than 3 distinct questions in the run (all served rows)."""
    per_clip: dict[str, set[str]] = defaultdict(set)
    answers = 0
    for r in rows:
        if not _served(r):
            continue
        answers += 1
        for key in {clip_key(c) for c in r["citations"]}:
            per_clip[key].add(str(r["id"]))
    if not answers:
        return _bar("not_measured", reason="no served rows")
    counts = {k: len(v) for k, v in per_clip.items()}
    over = sorted((k for k, c in counts.items() if c > HUB_LIMIT), key=lambda k: -counts[k])
    mx = max(counts.values())
    return _bar(
        "failed" if over else "met",
        estimate=mx,
        n=answers,
        max_questions_per_clip=mx,
        distinct_clips=len(counts),
        served_answers=answers,
        clips_over_limit={k: counts[k] for k in over},
        limit=HUB_LIMIT,
    )


def disagreements(grades: dict[str, Any] | None) -> dict[str, Any]:
    """Bar 9: row ids where the two graders' verdicts differ (reported, never averaged)."""
    if not grades:
        return {"status": "not_measured", "ids": []}
    first, second = grades.get("first") or {}, grades.get("second") or {}
    ids = sorted(
        i for i in set(first) & set(second) if first[i].get("verdict") != second[i].get("verdict")
    )
    return {"status": "reported", "compared": len(set(first) & set(second)), "ids": ids}


# ── manifest + assembly ──────────────────────────────────────────────────────


def manifest_facts(
    m: dict[str, Any] | None, grades: dict[str, Any] | None
) -> tuple[dict, list[str]]:
    if not m:
        return {}, ["manifest.json missing"]
    flags = m.get("flags") or {}
    invalid = [f"manifest lacks pinned value {k}" for k in REQUIRED_FLAGS if k not in flags]
    if "collection_fingerprint" not in m or m.get("collection_fingerprint") is None:
        invalid.append("manifest lacks collection fingerprint (points count + id sha)")
    if m.get("valid") is False:
        invalid.append("capture marked the run invalid: " + "; ".join(m.get("reasons") or []))
    sb, sa = m.get("spend_before") or {}, m.get("spend_after") or {}
    delta = {
        k: round(sa[k] - sb[k], 4)
        for k in ("day", "month")
        if sa.get(k) is not None and sb.get(k) is not None
    }
    facts = {
        "sha": m.get("sha"),
        "image": m.get("image"),
        "flags": {
            k: (
                "***REDACTED***"
                if any(s in k.lower() for s in ("key", "secret", "token", "password"))
                else flags.get(k, "<absent>")
            )
            for k in ECHO_FLAGS
        },
        "collection": flags.get("FIRST_PERSON_ACTIVE_COLLECTION")
        or flags.get("FIRST_PERSON_COLLECTION"),
        "collection_fingerprint": m.get("collection_fingerprint"),
        "grader_models": (grades or {}).get("models"),
        "scorer_model": flags.get("FIRST_PERSON_RELEVANCE_MODEL"),
        "judge_model": flags.get("FIRST_PERSON_JUDGE_MODEL"),
        "spend_before": sb,
        "spend_after": sa,
        "spend_delta_usd": delta,
    }
    return facts, invalid


def cohen_kappa(a: list[bool], b: list[bool]) -> float | None:
    """Cohen's kappa for two binary labelings; None when undefined (no rows or chance agreement 1)."""
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def grader_trust(rows: list[dict], grades: dict[str, Any] | None) -> dict[str, Any]:
    """Per-grader showable rate, inter-grader agreement + kappa, per-set showable, rubric hash."""
    if not grades:
        return {"status": "not_measured", "reason": "grades.json missing"}
    first, second = grades.get("first") or {}, grades.get("second") or {}
    show = lambda g, i: g[i].get("verdict") == "showable"  # noqa: E731
    both = sorted(set(first) & set(second))
    a, b = [show(first, i) for i in both], [show(second, i) for i in both]
    set_of = {str(r["id"]): r.get("set") for r in rows}
    by_set: dict[str, Any] = {}
    for name, g in (("first", first), ("second", second)):
        for i in g:
            s = by_set.setdefault(str(set_of.get(i, "unlabelled")), {}).setdefault(
                name, {"k": 0, "n": 0}
            )
            s["n"] += 1
            s["k"] += show(g, i)
    meta = grades.get("grader_meta") or {}
    return {
        "per_grader_showable": {
            n: {"k": sum(show(g, i) for i in g), "n": len(g)}
            for n, g in (("first", first), ("second", second))
        },
        "rows_graded_by_both": len(both),
        "agreement": round(sum(x == y for x, y in zip(a, b)) / len(both), 4) if both else None,
        "cohen_kappa": cohen_kappa(a, b),
        "showable_by_set": by_set,
        # ponytail: held-out = any set label other than the tuning set and the unanswerable probes
        "held_out_set_label_present": any(
            k not in ("frozen116", "unanswerable86", "unlabelled") for k in by_set
        ),
        "rubric_sha256": meta.get("rubric_sha256"),
        "grader_models": {"first": meta.get("first_model"), "second": meta.get("second_model")},
    }


def evaluate(run_dir: Path) -> dict[str, Any]:
    def load(name: str) -> Any:
        p = run_dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    rows_p = run_dir / "rows.jsonl"
    if not rows_p.exists():
        raise FileNotFoundError(f"{rows_p} missing")
    rows = [
        json.loads(line) for line in rows_p.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    grades, una, manifest = load("grades.json"), load("unanswerable.json"), load("manifest.json")
    una, skipped = exclude_transport_failed(una, rows)
    tf_ids = sorted(str(r["id"]) for r in rows if _transport_failed(r))

    showable, invalid = bar_showable(rows, grades)
    facts, m_invalid = manifest_facts(manifest, grades)
    bars = {
        "1_showable_both_graders": showable,
        "2_served_share_core": bar_served_share(rows),
        "3_p95_latency": bar_latency(rows),
        "4_harmful_zero": bar_harmful(grades, invalid),
        "5_unanswerable_set": bar_unanswerable(rows, una),
        "6_core_abstain_rate": bar_core_abstain(una),
        "7_crisis_routing": bar_crisis(una),
        "8_hub_rule": bar_hub(rows),
        "10_strict_reader_answers": _bar(
            "not_measured",
            reason="no strict-reader ANSWERS verdict exists in the harness (audit H-6)",
        ),
    }
    tf_invalid = (
        [
            f"{len(tf_ids)} rows failed at transport (not measured): "
            + ", ".join(tf_ids[:10])
            + (" ..." if len(tf_ids) > 10 else "")
        ]
        if tf_ids
        else []
    )
    for key, ids in skipped.items():
        bar = next(b for k, b in bars.items() if k.startswith(f"{key}_"))
        if ids:
            bar["not_measured_rows"] = len(ids)
            bar["not_measured_ids"] = ids[:10]
            bar["reason"] = (bar.get("reason", "") + f" not measured for {len(ids)} rows").strip()
    if tf_ids:
        bar = bars["2_served_share_core"]
        n_core = sum(1 for r in rows if r.get("set") == "frozen116" and _is_answerable(r))
        if bar.get("n") is not None and n_core > bar["n"]:
            bar["reason"] = f"not measured for {n_core - bar['n']} rows"
    invalid = invalid + tf_invalid
    statuses = [b["status"] for b in bars.values()]
    return {
        "run_id": (manifest or {}).get("run_id") or run_dir.name,
        "rows": len(rows),
        "bars": bars,
        "9_grader_disagreements": disagreements(grades),
        "grader_trust": grader_trust(rows, grades),
        "manifest": facts,
        "invalid_reasons": invalid + m_invalid,
        "run_valid": not (invalid or m_invalid),
        # An invalid run can never read as PASS, whatever its bars say.
        "overall": "FAIL"
        if "failed" in statuses
        else ("INCOMPLETE" if "not_measured" in statuses or invalid or m_invalid else "PASS"),
    }


def to_markdown(rep: dict[str, Any]) -> str:
    def fmt(b: dict[str, Any]) -> str:
        est = b.get("estimate")
        ci = b.get("wilson95")
        extra = f" Wilson95 {ci[0]:.3f}-{ci[1]:.3f}" if ci else ""
        return f"| {b['status']} | {est if est is not None else '-'} | {b.get('n') if b.get('n') is not None else '-'} |{extra} {b.get('reason', '')}".rstrip()

    lines = [
        f"# Registered-bar report: {rep['run_id']}",
        "",
        f"Overall: **{rep['overall']}**; run valid: **{rep['run_valid']}**",
        "",
        "| bar | status | estimate | n | notes |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {k} {fmt(b)} |" for k, b in rep["bars"].items()]
    d = rep["9_grader_disagreements"]
    t = rep["grader_trust"]
    if "per_grader_showable" in t:
        pg = t["per_grader_showable"]
        lines += [
            "",
            "Grader trust: "
            + "; ".join(f"{n} showable {v['k']}/{v['n']}" for n, v in pg.items())
            + f"; agreement {t['agreement']} and Cohen kappa {t['cohen_kappa']}"
            + f" on {t['rows_graded_by_both']} rows graded by both; rubric sha256 {t['rubric_sha256'] or 'not recorded'}",
            "Showable by set: "
            + "; ".join(
                f"{s}: " + ", ".join(f"{n} {v['k']}/{v['n']}" for n, v in d_.items())
                for s, d_ in t["showable_by_set"].items()
            )
            + ("" if t["held_out_set_label_present"] else " (no held-out set label in rows)"),
        ]
    lines += [
        "",
        f"Grader disagreements ({d['status']}): {', '.join(d['ids']) or 'none'}",
        "",
        "Invalid reasons:",
    ]
    lines += [f"- {r}" for r in rep["invalid_reasons"]] or ["- none"]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", help="write the JSON report here")
    ap.add_argument("--md", help="write the Markdown summary here (default: stdout)")
    args = ap.parse_args()
    rep = evaluate(Path(args.run_dir).expanduser())
    if args.out:
        Path(args.out).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    md = to_markdown(rep)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
