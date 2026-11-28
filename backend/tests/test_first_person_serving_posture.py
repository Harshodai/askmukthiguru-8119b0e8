"""A-32: FIRST_PERSON_SERVING_POSTURE makes the serving lane an explicit, checked decision.

Before this setting, harness+terminal both off booted and served the v8 clip store in
production because it was indistinguishable from the deliberate ``v8_bridge`` rollback.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.runtime_budget import serving_gate_warnings
from scripts.ops.validate_production_env import validate_environment
from services.first_person_serving_contract import (
    FirstPersonServingContractError,
    assert_startup_safe,
    load_contract,
    validate_serving_contract,
)

_BACKEND = Path(__file__).resolve().parents[1]
V10, V8 = "first_person_v10", "first_person_v8"
FLAGS = {"both_on": (True, True), "both_off": (False, False), "mixed": (True, False)}


@pytest.fixture(scope="module")
def contract():
    return load_contract(_BACKEND / "config" / "first_person_serving_contract.json")


def _report(contract, harness: bool, terminal: bool):
    # Same slot resolution as Settings.resolve_first_person_active_collection.
    legacy = V10 if harness and terminal else V8
    return validate_serving_contract(
        contract=contract,
        legacy_collection=legacy,
        context_collection=V10,
        context_harness_enabled=harness,
        context_terminal_enabled=terminal,
    )


# (posture, flags) -> raises in production, raises outside production
CASES = {
    ("v10_only", "both_on"): (False, False),
    ("v10_only", "both_off"): (True, True),
    ("v10_only", "mixed"): (True, True),
    ("v8_bridge", "both_on"): (True, True),
    ("v8_bridge", "both_off"): (False, False),
    ("v8_bridge", "mixed"): (True, True),
    ("", "both_on"): (False, False),
    ("", "both_off"): (False, False),
    ("", "mixed"): (True, False),
}


@pytest.mark.parametrize("is_production", [True, False], ids=["prod", "nonprod"])
@pytest.mark.parametrize(("posture", "flags"), sorted(CASES))
def test_posture_matrix(contract, posture, flags, is_production):
    harness, terminal = FLAGS[flags]
    expect_raise = CASES[(posture, flags)][0 if is_production else 1]

    def run():
        assert_startup_safe(
            _report(contract, harness, terminal),
            is_production=is_production,
            legacy_route_enabled=True,
            context_harness_enabled=harness,
            context_terminal_enabled=terminal,
            serving_posture=posture,
        )

    if expect_raise:
        with pytest.raises(FirstPersonServingContractError) as exc:
            run()
        if posture:
            assert "FIRST_PERSON_SERVING_POSTURE" in str(exc.value)
            assert "FIRST_PERSON_CONTEXT_HARNESS_ENABLED" in str(exc.value)
    else:
        run()


def test_v10_only_rejects_a_slot_override_off_v10(contract):
    report = validate_serving_contract(
        contract=contract,
        legacy_collection=V8,
        context_collection=V10,
        context_harness_enabled=True,
        context_terminal_enabled=True,
    )
    with pytest.raises(FirstPersonServingContractError, match="FIRST_PERSON_COLLECTION="):
        assert_startup_safe(
            report,
            is_production=False,
            legacy_route_enabled=True,
            context_harness_enabled=True,
            context_terminal_enabled=True,
            serving_posture="v10_only",
        )


def test_settings_rejects_an_unknown_posture(monkeypatch):
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.setenv("FIRST_PERSON_SERVING_POSTURE", "v9")
    with pytest.raises(ValidationError):
        Settings()


def test_lifespan_passes_the_posture_to_the_startup_check():
    main = (_BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    call = main.split("assert_startup_safe(\n", 1)[1].split("\n        )\n", 1)[0]
    assert 'serving_posture=str(getattr(settings, "first_person_serving_posture"' in call


def _settings(**kw):
    base = {
        "is_production": True,
        "first_person_serving_posture": "",
        "first_person_context_harness_enabled": False,
        "first_person_context_terminal_enabled": False,
        "first_person_collection": V8,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_undeclared_posture_warns_in_production_and_names_the_lane():
    (warning,) = serving_gate_warnings(_settings())
    assert "FIRST_PERSON_SERVING_POSTURE is undeclared" in warning
    assert "legacy clip store" in warning and V8 in warning
    (warning,) = serving_gate_warnings(
        _settings(
            first_person_context_harness_enabled=True,
            first_person_context_terminal_enabled=True,
            first_person_collection=V10,
        )
    )
    assert "v10-only context harness" in warning


@pytest.mark.parametrize(
    "kw", [{"is_production": False}, {"first_person_serving_posture": "v8_bridge"}]
)
def test_no_posture_warning_outside_production_or_when_declared(kw):
    assert serving_gate_warnings(_settings(**kw)) == []


def test_warning_reaches_the_startup_log(caplog):
    from app.runtime_budget import log_runtime_budget

    with caplog.at_level(logging.WARNING):
        log_runtime_budget(logging.getLogger("posture-test"), _settings())
    assert "FIRST_PERSON_SERVING_POSTURE is undeclared" in caplog.text


_PROD_ENV = {
    "IS_PRODUCTION": "true",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_KEY": "k",
    "REDIS_URL": "redis://default:pw@redis.railway.internal:6379/0",
    "ANON_SESSION_HMAC_SECRET": "s",
    "FORWARDED_ALLOW_IPS": "10.0.0.0/8",
    "LLM_PROVIDER": "openrouter",
    "OPENROUTER_API_KEY": "k",
    "BRAIN_KEK": "k",
}
_FLAG_ENV = {
    "both_on": {
        "FIRST_PERSON_CONTEXT_HARNESS_ENABLED": "true",
        "FIRST_PERSON_CONTEXT_TERMINAL_ENABLED": "true",
    },
    "both_off": {
        "FIRST_PERSON_CONTEXT_HARNESS_ENABLED": "false",
        "FIRST_PERSON_CONTEXT_TERMINAL_ENABLED": "false",
    },
    "mixed": {
        "FIRST_PERSON_CONTEXT_HARNESS_ENABLED": "true",
        "FIRST_PERSON_CONTEXT_TERMINAL_ENABLED": "false",
    },
}


@pytest.mark.parametrize(("posture", "flags"), sorted(CASES))
def test_preflight_mirrors_the_startup_check(posture, flags):
    env = {**_PROD_ENV, **_FLAG_ENV[flags], "FIRST_PERSON_SERVING_POSTURE": posture}
    result = validate_environment(env)
    assert result.ok is (not CASES[(posture, flags)][0]), result.errors
    if not posture:
        assert any("undeclared" in w for w in result.warnings)


def test_preflight_v10_only_rejects_a_legacy_slot_override():
    env = {
        **_PROD_ENV,
        **_FLAG_ENV["both_on"],
        "FIRST_PERSON_SERVING_POSTURE": "v10_only",
        "FIRST_PERSON_COLLECTION": V8,
    }
    assert any("first_person_v10" in e for e in validate_environment(env).errors)


def test_v12_shadow_posture_accepts_v12_slots(contract):
    v12 = "first_person_v12_shadow"
    report = validate_serving_contract(
        contract=contract,
        legacy_collection=v12,
        context_collection=v12,
        context_harness_enabled=True,
        context_terminal_enabled=True,
    )
    assert_startup_safe(
        report,
        is_production=True,
        legacy_route_enabled=True,
        context_harness_enabled=True,
        context_terminal_enabled=True,
        serving_posture="v12_shadow",
    )


def test_v12_shadow_rejects_a_slot_override_off_v12(contract):
    v12 = "first_person_v12_shadow"
    report = validate_serving_contract(
        contract=contract,
        legacy_collection="first_person_v10",
        context_collection=v12,
        context_harness_enabled=True,
        context_terminal_enabled=True,
    )
    with pytest.raises(FirstPersonServingContractError, match="FIRST_PERSON_COLLECTION="):
        assert_startup_safe(
            report,
            is_production=False,
            legacy_route_enabled=True,
            context_harness_enabled=True,
            context_terminal_enabled=True,
            serving_posture="v12_shadow",
        )
