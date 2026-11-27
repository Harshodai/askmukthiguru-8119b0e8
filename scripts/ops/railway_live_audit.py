#!/usr/bin/env python3
"""Read-only audit of the LIVE Railway configuration against the repo's invariants.

Why: `.railway/railway.ts` cannot express most live settings (Dockerfile path, restart
policy, limits, Wait for CI, ...), so live drift is invisible to the repo's drift tests.
On 2026-11-27 a review found production running with FIRST_PERSON_LLM_FALLBACK_ENABLED=true
(a binding owner directive says false), OpenRouter caps of $50/day and $500/month, and a
projected bill above the workspace soft limit.

Reads only: `railway variables --json` and `railway usage --json` (needs the Railway CLI,
logged in). It never prints a variable value other than the non-secret ones it checks.

Exit code: 0 clean, 1 warnings, 2 at least one critical finding.

    python3 scripts/ops/railway_live_audit.py
    python3 scripts/ops/railway_live_audit.py --workspace "My Workspace" --max-daily 10
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

SERVICES = ("askmukthiguru-8119b0e8", "celery-worker")
TRUTHY = {"1", "true", "yes", "on"}
CRITICAL = "CRITICAL"
WARN = "WARN"
INFO = "INFO"


@dataclass(frozen=True)
class Finding:
    severity: str
    check: str
    detail: str


def _num(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def evaluate_service_vars(
    service: str,
    values: dict[str, str],
    *,
    max_daily_usd: float,
    max_monthly_usd: float,
) -> list[Finding]:
    """Check one service's variables. `values` is the service's variable map."""
    out: list[Finding] = []
    fallback = str(values.get("FIRST_PERSON_LLM_FALLBACK_ENABLED", "")).strip().lower()
    if fallback in TRUTHY:
        out.append(
            Finding(
                CRITICAL,
                "llm_fallback",
                f"{service}: FIRST_PERSON_LLM_FALLBACK_ENABLED is {fallback!r}; the binding owner "
                "directive (2026-11-23) requires false",
            )
        )
    workers = _num(values.get("WEB_CONCURRENCY"))
    if workers is not None and workers > 1:
        out.append(
            Finding(
                WARN,
                "web_concurrency",
                f"{service}: WEB_CONCURRENCY={workers:g}; every uvicorn worker holds its own copy of "
                "the embedding and reranker models (about 2.5 GB each), and the repo default is 1",
            )
        )
    if str(values.get("OPENROUTER_BUDGET_GUARD_ENABLED", "")).strip().lower() not in TRUTHY:
        out.append(
            Finding(
                CRITICAL, "budget_guard", f"{service}: OPENROUTER_BUDGET_GUARD_ENABLED is not true"
            )
        )
    daily = _num(values.get("OPENROUTER_DAILY_BUDGET_USD"))
    monthly = _num(values.get("OPENROUTER_MONTHLY_BUDGET_USD"))
    if daily is not None and daily > max_daily_usd:
        out.append(
            Finding(
                WARN, "llm_daily_cap", f"{service}: daily cap ${daily:g} exceeds ${max_daily_usd:g}"
            )
        )
    if monthly is not None and monthly > max_monthly_usd:
        out.append(
            Finding(
                WARN,
                "llm_monthly_cap",
                f"{service}: monthly cap ${monthly:g} exceeds ${max_monthly_usd:g}",
            )
        )
    return out


def evaluate_posture(by_service: dict[str, dict[str, str]]) -> list[Finding]:
    """Every service must serve the same posture (backend and worker share collections)."""
    postures = {
        name: str(vals.get("FIRST_PERSON_SERVING_POSTURE", "")).strip()
        for name, vals in by_service.items()
    }
    if len(set(postures.values())) > 1:
        return [
            Finding(WARN, "posture_drift", f"serving posture differs across services: {postures}")
        ]
    return []


def evaluate_usage(usage: dict[str, Any]) -> list[Finding]:
    """Compare the projected bill to the workspace limits and name the dominant line item."""
    out: list[Finding] = []
    estimate = _num(usage.get("estimatedBillDollars"))
    current = _num(usage.get("currentUsageDollars")) or 0.0
    limit = usage.get("usageLimit") or {}
    soft = _num(limit.get("softLimitDollars") or limit.get("softLimit"))
    hard = _num(limit.get("hardLimitDollars") or limit.get("hardLimit"))
    if estimate is not None and hard is not None and estimate >= hard:
        out.append(
            Finding(
                CRITICAL,
                "hard_limit",
                f"projected ${estimate:.2f} reaches the hard limit ${hard:g}: all workloads go offline",
            )
        )
    elif estimate is not None and soft is not None and estimate >= soft:
        out.append(
            Finding(
                WARN, "soft_limit", f"projected ${estimate:.2f} exceeds the soft limit ${soft:g}"
            )
        )
    items = {
        i.get("label"): _num(i.get("currentUsageDollars")) or 0.0
        for i in usage.get("lineItems", [])
    }
    if current > 0 and items:
        top, amount = max(items.items(), key=lambda kv: kv[1])
        out.append(
            Finding(
                INFO,
                "cost_driver",
                f"{top} is {amount / current:.0%} of current usage (${amount:.2f})",
            )
        )
    return out


def _railway_json(args: list[str]) -> Any:
    proc = subprocess.run(["railway", *args, "--json"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"railway {' '.join(args)} failed: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace", default=None, help="Railway workspace name or id")
    parser.add_argument("--environment", default="production")
    parser.add_argument(
        "--max-daily", type=float, default=15.0, help="max sane OpenRouter daily cap (USD)"
    )
    parser.add_argument(
        "--max-monthly", type=float, default=150.0, help="max sane OpenRouter monthly cap (USD)"
    )
    args = parser.parse_args(argv)

    findings: list[Finding] = []
    by_service: dict[str, dict[str, str]] = {}
    for service in SERVICES:
        values = _railway_json(
            ["variables", "--service", service, "--environment", args.environment]
        )
        by_service[service] = {k: str(v) for k, v in values.items()}
        findings += evaluate_service_vars(
            service,
            by_service[service],
            max_daily_usd=args.max_daily,
            max_monthly_usd=args.max_monthly,
        )
    findings += evaluate_posture(by_service)
    usage_args = ["usage"] + (["--workspace", args.workspace] if args.workspace else [])
    findings += evaluate_usage(_railway_json(usage_args))

    for f in sorted(findings, key=lambda f: (f.severity != CRITICAL, f.severity != WARN, f.check)):
        print(f"[{f.severity}] {f.check}: {f.detail}")
    if not findings:
        print("[OK] no findings")
    if any(f.severity == CRITICAL for f in findings):
        return 2
    return 1 if any(f.severity == WARN for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
