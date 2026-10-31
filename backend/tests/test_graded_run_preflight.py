"""The graded-run preflight and override (plan items F1 and F2, 2026-10-31)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from scripts.ops.graded_run_preflight import (
    CODE_DESTINATIONS,
    check_env_pins,
    check_git_clean,
    check_local_review_disabled,
    check_log_clean,
    check_no_code_binds,
    check_spend_headroom,
    check_started_after_head,
    load_compose_yaml,
    read_override_pins,
)

_OVERRIDE = Path(__file__).resolve().parents[1] / "docker-compose.graded.yml"


def _inspect(mounts=(), started="2026-10-31T10:00:00.123456789Z"):
    return [{"Mounts": list(mounts), "State": {"StartedAt": started}}]


# ── F1: a clean tree and no code binds ───────────────────────────────────────


def test_dirty_or_untracked_tree_fails():
    assert not check_git_clean(" M backend/app/config.py\n?? audits/manifests/x.json\n").ok
    assert check_git_clean("").ok


def test_a_bind_mount_over_application_code_fails():
    bind = {"Type": "bind", "Destination": "/app/services", "Source": "/host/services"}
    result = check_no_code_binds(_inspect([bind]))
    assert not result.ok and "/app/services" in result.detail


def test_data_mounts_and_named_volumes_are_fine():
    mounts = [
        {"Type": "bind", "Destination": "/app/audits", "Source": "/host/audits"},
        {"Type": "volume", "Destination": "/app/data", "Name": "telemetry"},
        {"Type": "volume", "Destination": "/app/services", "Name": "oddly-named-volume"},
    ]
    assert check_no_code_binds(_inspect(mounts)).ok  # only BIND mounts count


def test_every_code_directory_the_base_compose_binds_is_covered():
    base = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()
    for dest in ("/app/app", "/app/rag", "/app/services", "/app/domain", "/app/ingest"):
        assert f":{dest}" in base  # the base file does bind them ...
        assert dest in CODE_DESTINATIONS  # ... and the preflight knows to object


def test_container_older_than_head_fails():
    older = _inspect(started="2026-10-31T10:00:00.5Z")
    head = 1_793_000_000.0  # well after 2026-10-31T10:00Z? compute below
    from datetime import UTC, datetime

    head = datetime(2026, 10, 31, 11, 0, tzinfo=UTC).timestamp()
    assert not check_started_after_head(older, head).ok
    assert check_started_after_head(_inspect(started="2026-10-31T12:00:00Z"), head).ok
    assert not check_started_after_head(_inspect(started="garbage"), head).ok


# ── F2: the override and the env diff ────────────────────────────────────────


def test_env_drift_from_the_override_fails():
    pins = {"FIRST_PERSON_RELEVANCE_MIN_SCORE": "3", "FIRST_PERSON_LOCAL_REVIEW_ENABLED": "false"}
    drifted = {"FIRST_PERSON_RELEVANCE_MIN_SCORE": "2", "FIRST_PERSON_LOCAL_REVIEW_ENABLED": "true"}
    result = check_env_pins(drifted, pins)
    assert not result.ok and "MIN_SCORE" in result.detail
    assert check_env_pins({**pins}, pins).ok


def test_a_pinned_flag_missing_from_the_container_fails():
    assert not check_env_pins({}, {"FIRST_PERSON_CONTEXT_TERMINAL_ENABLED": "true"}).ok


def test_override_drops_every_code_bind_and_pins_the_serving_path():
    data = load_compose_yaml(_OVERRIDE)
    backend = data["services"]["backend"]
    targets = {v.split(":")[1] for v in backend["volumes"]}
    assert not (targets & CODE_DESTINATIONS), targets & CODE_DESTINATIONS
    pins = read_override_pins(_OVERRIDE)
    assert (
        pins["FIRST_PERSON_COLLECTION"]
        == pins["FIRST_PERSON_CONTEXT_COLLECTION"]
        == "first_person_v10"
    )
    assert pins["FIRST_PERSON_CONTEXT_HARNESS_ENABLED"] == "true"
    assert pins["FIRST_PERSON_CONTEXT_TERMINAL_ENABLED"] == "true"
    assert pins["FIRST_PERSON_LOCAL_REVIEW_ENABLED"] == "false"
    assert pins["FIRST_PERSON_RELEVANCE_TIMEOUT_S"] == "12"
    assert pins["OPENROUTER_BUDGET_GUARD_ENABLED"] == "true"  # caps are raised, never removed
    assert pins["OPENROUTER_BUDGET_FAIL_CLOSED"] == "true"


def test_every_pinned_flag_is_a_real_setting():
    """A typo'd pin would pin nothing and the preflight would still pass."""
    fields = set(Settings.model_fields)
    unknown = [
        k
        for k in read_override_pins(_OVERRIDE)
        if not k.startswith("CELERY_") and k.lower() not in fields
    ]
    assert unknown == []


# ── F3 run rule and log hygiene ──────────────────────────────────────────────


def test_spend_headroom_needs_room_in_both_the_day_and_the_month():
    assert check_spend_headroom(9.98, 30.4, 10.0, 40.0, 12.0).ok is False
    assert check_spend_headroom(9.98, 30.4, 100.0, 300.0, 12.0).ok is True
    assert check_spend_headroom(None, 1.0, 100.0, 300.0, 12.0).ok is False


@pytest.mark.parametrize(
    "line",
    [
        "Answerability check indeterminate (timeout/error): OpenRouter daily or monthly spend limit reached",
        "Relevance check indeterminate (timeout/error): boom",
    ],
)
def test_log_with_spend_limit_or_indeterminate_lines_fails(line):
    assert not check_log_clean("ok line\n" + line + "\n").ok
    assert check_log_clean("ok line\nanother ok line\n").ok


# ── Tier 3 item 5: the owner-only review API must not be live ────────────────


def test_an_available_local_review_route_fails_the_preflight():
    result = check_local_review_disabled(200, {"available": True})
    assert not result.ok and "live" in result.detail


def test_a_disabled_local_review_route_passes():
    assert check_local_review_disabled(
        200, {"available": False, "reason": "local_review_mode_disabled"}
    ).ok
    assert check_local_review_disabled(404, None).ok
    assert check_local_review_disabled(403, None).ok


def test_unreachable_or_ambiguous_status_is_not_a_pass():
    assert not check_local_review_disabled(None, None).ok
    assert not check_local_review_disabled(200, {"something": "else"}).ok
    assert not check_local_review_disabled(500, {"available": False}).ok
