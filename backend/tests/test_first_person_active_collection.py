"""One active first-person collection name, derived into both serving slots.

Owner request 2026-11-01: FIRST_PERSON_COLLECTION and
FIRST_PERSON_CONTEXT_COLLECTION held the same literal for the v10 run and could drift.
`first_person_active_collection` is now the single name; the two old names are optional
overrides, and the serving-contract preflight rejects a slot that disagrees with it.
"""

from __future__ import annotations

from app.config import Settings
from services.first_person_serving_contract import (
    default_contract_path,
    load_contract,
    validate_serving_contract,
)

V8 = "first_person_v8"
V10 = "first_person_v10"


def _settings(**kw) -> Settings:
    base = {
        "first_person_collection": "",
        "first_person_context_collection": "",
        "first_person_active_collection": V10,
        # backend/.env on a dev box may switch these on; pin them so the test is hermetic.
        "first_person_context_harness_enabled": False,
        "first_person_context_terminal_enabled": False,
    }
    return Settings(**{**base, **kw})


def test_v10_only_posture_derives_both_slots_from_active_name():
    s = _settings(
        first_person_context_harness_enabled=True, first_person_context_terminal_enabled=True
    )
    assert (s.first_person_collection, s.first_person_context_collection) == (V10, V10)


def test_default_posture_keeps_legacy_rollback_slot():
    s = _settings()
    assert (s.first_person_collection, s.first_person_context_collection) == (V8, V10)


def test_explicit_override_wins():
    s = _settings(first_person_collection="first_person_v7")
    assert s.first_person_collection == "first_person_v7"


def _report(**kw):
    args = {
        "contract": load_contract(default_contract_path()),
        "legacy_collection": V10,
        "context_collection": V10,
        "context_harness_enabled": True,
        "context_terminal_enabled": True,
        "active_collection": V10,
    }
    return validate_serving_contract(**{**args, **kw})


def test_preflight_passes_when_slots_match_active():
    assert _report().ok


def test_preflight_fails_when_a_slot_differs_from_active():
    report = _report(legacy_collection=V8)
    assert not report.ok
    assert any("legacy first-person slot" in e for e in report.errors)


def test_preflight_fails_when_active_not_in_registry():
    report = _report(
        legacy_collection="first_person_v99",
        context_collection="first_person_v99",
        active_collection="first_person_v99",
    )
    assert any("active collection 'first_person_v99' is not declared" in e for e in report.errors)


def test_two_slot_rollback_posture_is_not_flagged_by_active_check():
    report = _report(
        legacy_collection=V8, context_harness_enabled=False, context_terminal_enabled=False
    )
    assert not any("active collection" in e for e in report.errors)


def test_preflight_rejects_a_legacy_collection_as_the_active_name():
    report = _report(
        legacy_collection=V8,
        context_collection=V8,
        active_collection=V8,
        context_harness_enabled=False,
        context_terminal_enabled=False,
    )
    assert any("is a legacy clip store" in e for e in report.errors)
