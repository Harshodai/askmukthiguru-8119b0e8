#!/usr/bin/env python3
"""Outcome and cost report from /internal/metrics snapshots (NEW-LOAD-2).

Take one snapshot before a load stage and one after. The report is the delta:
outcome mix, provider-reported cost, unknown-cost calls, a latency upper bound and the
cost per request, per served answer and (given an external share) per useful answer.

    export METRICS_SCRAPE_TOKEN=...            # never pass it on the command line
    python3 scripts/ops/load_run_report.py snapshot https://staging.example.test before_s2.prom
    ... run the stage ...
    python3 scripts/ops/load_run_report.py snapshot https://staging.example.test after_s2.prom
    python3 scripts/ops/load_run_report.py report before_s2.prom after_s2.prom --stage S2 \
        [--useful-share 0.4] [--json s2.json]

Read only: one GET of /internal/metrics per snapshot. Standard library only, so the same
file can run inside the image (a byte-identical copy lives in backend/scripts/ops/).
Plan: LOAD_AND_COST_MODEL.md section 6.6. "Useful" cannot come from the counter during a
load test (nothing clicks), so --useful-share must come from the offline judged share.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

_LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?\s+(\S+)\s*$")
_LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')

Row = tuple[str, dict[str, str], float]


def parse_metrics(text: str) -> list[Row]:
    rows: list[Row] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        name, labels, value = m.groups()
        try:
            val = float(value)
        except ValueError:
            continue
        rows.append((name, dict(_LABEL.findall(labels or "")), val))
    return rows


def _by_key(rows: list[Row], name: str, *label_names: str) -> dict[tuple[str, ...], float]:
    out: dict[tuple[str, ...], float] = {}
    for n, labels, v in rows:
        if n == name:
            key = tuple(labels.get(k, "") for k in label_names)
            out[key] = out.get(key, 0.0) + v
    return out


def _delta(before: dict, after: dict) -> dict:
    return {k: after.get(k, 0.0) - before.get(k, 0.0) for k in set(before) | set(after)}


def _p50_upper_bound(before: list[Row], after: list[Row]) -> float | None:
    """Smallest bucket bound that holds at least half of the new served observations.

    A histogram bucket gives an upper bound, not the median. Say so in the report.
    """
    name = "guru_answer_latency_seconds_bucket"

    def buckets(rows: list[Row]) -> dict[str, float]:
        out: dict[str, float] = {}
        for n, labels, v in rows:
            if n == name and labels.get("outcome") == "served":
                out[labels.get("le", "")] = out.get(labels.get("le", ""), 0.0) + v
        return out

    d = _delta(buckets(before), buckets(after))
    total = d.get("+Inf", 0.0)
    if total <= 0:
        return None
    bounds = sorted((float(k), v) for k, v in d.items() if k != "+Inf")
    for le, count in bounds:
        if count >= total / 2:
            return le
    return float("inf")


def build_report(before: list[Row], after: list[Row], useful_share: float | None = None) -> dict:
    outcome = _delta(
        _by_key(before, "guru_answer_outcome_total", "outcome"),
        _by_key(after, "guru_answer_outcome_total", "outcome"),
    )
    outcomes = {k[0]: int(v) for k, v in outcome.items() if v}
    cost = sum(
        _delta(
            _by_key(before, "guru_provider_reported_cost_usd_total", "provider"),
            _by_key(after, "guru_provider_reported_cost_usd_total", "provider"),
        ).values()
    )
    unknown = sum(
        _delta(
            _by_key(before, "guru_openrouter_cost_unknown_total", "model", "operation"),
            _by_key(after, "guru_openrouter_cost_unknown_total", "model", "operation"),
        ).values()
    )
    total = sum(outcomes.values())
    served = outcomes.get("served", 0)
    useful = served * useful_share if useful_share is not None else None
    return {
        "outcomes": outcomes,
        "requests": total,
        "cost_usd": cost,
        "unknown_cost_calls": int(unknown),
        "cost_per_request_usd": cost / total if total else None,
        "cost_per_served_usd": cost / served if served else None,
        "cost_per_useful_usd": cost / useful if useful else None,
        "useful_share_input": useful_share,
        "latency_p50_upper_bound_s": _p50_upper_bound(before, after),
    }


def to_markdown(rep: dict, *, stage: str = "") -> str:
    def money(v):
        return "n/a" if v is None else f"${v:.4f}"

    lines = [
        f"### Stage {stage or '?'}: outcome and cost (delta of two metric snapshots)",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Requests with an outcome | {rep['requests']} |",
        "| Outcome mix | "
        + (", ".join(f"{k} {v}" for k, v in sorted(rep["outcomes"].items())) or "none")
        + " |",
        f"| Provider-reported cost | {money(rep['cost_usd'])} |",
        f"| Cost per request | {money(rep['cost_per_request_usd'])} |",
        f"| Cost per served answer | {money(rep['cost_per_served_usd'])} |",
        f"| Cost per useful answer | {money(rep['cost_per_useful_usd'])}"
        + ("" if rep["useful_share_input"] is not None else " (needs --useful-share)")
        + " |",
        f"| Unknown-cost calls | {rep['unknown_cost_calls']} (must be 0, PC-8) |",
        f"| Served latency p50, upper bound | "
        f"{rep['latency_p50_upper_bound_s'] if rep['latency_p50_upper_bound_s'] is not None else 'n/a'} s |",
        "",
        "Latency is a histogram bucket bound, not a median. Locust holds the exact percentiles.",
    ]
    return "\n".join(lines) + "\n"


def fetch_snapshot(base_url: str, token: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(
        base_url.rstrip("/") + "/internal/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https URL given by the operator
        return resp.read().decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("url")
    snap.add_argument("out")
    rep = sub.add_parser("report")
    rep.add_argument("before")
    rep.add_argument("after")
    rep.add_argument("--stage", default="")
    rep.add_argument("--useful-share", type=float, default=None)
    rep.add_argument("--json", dest="json_out")
    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        token = os.environ.get("METRICS_SCRAPE_TOKEN", "")
        if not token:
            print("Set METRICS_SCRAPE_TOKEN in the environment.", file=sys.stderr)
            return 2
        try:
            text = fetch_snapshot(args.url, token)
        except (urllib.error.URLError, OSError) as exc:
            print(f"Snapshot failed: {type(exc).__name__}", file=sys.stderr)
            return 2
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Wrote {len(text.splitlines())} lines to {args.out}")
        return 0

    with open(args.before, encoding="utf-8") as fb, open(args.after, encoding="utf-8") as fa:
        report = build_report(parse_metrics(fb.read()), parse_metrics(fa.read()), args.useful_share)
    sys.stdout.write(to_markdown(report, stage=args.stage))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
    return 1 if report["unknown_cost_calls"] else 0


if __name__ == "__main__":
    sys.exit(main())
