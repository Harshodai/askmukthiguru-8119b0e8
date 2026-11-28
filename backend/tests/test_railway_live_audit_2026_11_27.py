"""The Railway live-config audit flags the drift found on 2026-11-27 and stays quiet when clean."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "railway_live_audit.py"
_spec = importlib.util.spec_from_file_location("railway_live_audit", SCRIPT)
audit = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["railway_live_audit"] = audit  # @dataclass resolves its module through sys.modules
_spec.loader.exec_module(audit)

CLEAN = {
    "FIRST_PERSON_LLM_FALLBACK_ENABLED": "false",
    "OPENROUTER_BUDGET_GUARD_ENABLED": "true",
    "OPENROUTER_DAILY_BUDGET_USD": "10",
    "OPENROUTER_MONTHLY_BUDGET_USD": "100",
}


def _checks(findings, severity):
    return {f.check for f in findings if f.severity == severity}


def test_clean_service_has_no_findings():
    assert audit.evaluate_service_vars("svc", CLEAN, max_daily_usd=15, max_monthly_usd=150) == []


def test_fallback_true_is_critical_in_any_spelling():
    for spelling in ("true", "TRUE", " 1 ", "yes", "on"):
        vals = {**CLEAN, "FIRST_PERSON_LLM_FALLBACK_ENABLED": spelling}
        found = audit.evaluate_service_vars("svc", vals, max_daily_usd=15, max_monthly_usd=150)
        assert "llm_fallback" in _checks(found, audit.CRITICAL), spelling


def test_disabled_budget_guard_is_critical():
    vals = {**CLEAN, "OPENROUTER_BUDGET_GUARD_ENABLED": "false"}
    found = audit.evaluate_service_vars("svc", vals, max_daily_usd=15, max_monthly_usd=150)
    assert "budget_guard" in _checks(found, audit.CRITICAL)


def test_loose_spend_caps_warn():
    vals = {**CLEAN, "OPENROUTER_DAILY_BUDGET_USD": "50", "OPENROUTER_MONTHLY_BUDGET_USD": "500"}
    found = audit.evaluate_service_vars("svc", vals, max_daily_usd=15, max_monthly_usd=150)
    assert _checks(found, audit.WARN) == {"llm_daily_cap", "llm_monthly_cap"}


def test_extra_uvicorn_workers_warn():
    found = audit.evaluate_service_vars(
        "svc", {**CLEAN, "WEB_CONCURRENCY": "2"}, max_daily_usd=15, max_monthly_usd=150
    )
    assert _checks(found, audit.WARN) == {"web_concurrency"}
    one = audit.evaluate_service_vars(
        "svc", {**CLEAN, "WEB_CONCURRENCY": "1"}, max_daily_usd=15, max_monthly_usd=150
    )
    assert one == []


def test_posture_drift_between_services_warns():
    v13 = {"FIRST_PERSON_SERVING_POSTURE": "v13_shadow"}
    v10 = {"FIRST_PERSON_SERVING_POSTURE": "v10_only"}
    assert _checks(audit.evaluate_posture({"a": v13, "b": v10}), audit.WARN) == {"posture_drift"}
    assert audit.evaluate_posture({"a": v13, "b": v13}) == []


def test_usage_limits_and_cost_driver():
    base = {
        "currentUsageDollars": 14.0,
        "usageLimit": {"softLimit": 30, "hardLimit": 60},
        "lineItems": [
            {"label": "CPU", "currentUsageDollars": 0.2},
            {"label": "Memory", "currentUsageDollars": 13.5},
        ],
    }
    soft = audit.evaluate_usage({**base, "estimatedBillDollars": 41.9})
    hard = audit.evaluate_usage({**base, "estimatedBillDollars": 61.0})
    fine = audit.evaluate_usage({**base, "estimatedBillDollars": 20.0})
    assert "soft_limit" in _checks(soft, audit.WARN)
    assert "hard_limit" in _checks(hard, audit.CRITICAL)
    assert not _checks(fine, audit.WARN) and not _checks(fine, audit.CRITICAL)
    assert any(f.check == "cost_driver" and "Memory" in f.detail for f in soft)


def test_deploy_lag_warns_when_main_has_moved_on():
    found = audit.evaluate_deploy_lag("backend", "c667beec2aaaa", 146)
    assert _checks(found, audit.WARN) == {"deploy_lag"}
    assert "146" in found[0].detail and "c667beec2" in found[0].detail


def test_deploy_lag_quiet_when_current_and_informational_when_unknown():
    assert audit.evaluate_deploy_lag("backend", "850b49796abc", 0) == []
    unknown = audit.evaluate_deploy_lag("backend", "850b49796abc", None)
    assert _checks(unknown, audit.INFO) == {"deploy_lag"} and not _checks(unknown, audit.WARN)
    assert _checks(audit.evaluate_deploy_lag("backend", None, None), audit.INFO) == {"deploy_lag"}
