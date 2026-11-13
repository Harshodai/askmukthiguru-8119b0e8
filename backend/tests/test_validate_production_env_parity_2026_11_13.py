import pytest

from scripts.ops.validate_production_env import validate_environment


def _valid_env():
    return {
        "IS_PRODUCTION": "true",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "service-role-redacted",
        "REDIS_URL": "rediss://redis.example/0",
        "ANON_SESSION_HMAC_SECRET": "x" * 64,
        "FORWARDED_ALLOW_IPS": "10.0.0.0/8",
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "key-redacted",
        "BRAIN_KEK": "kek-redacted",
        "FACULTY_ACCESS_CODE": "code-redacted",
        "OPENROUTER_BUDGET_GUARD_ENABLED": "true",
        "OPENROUTER_BUDGET_FAIL_CLOSED": "true",
    }


def test_fully_valid_production_environment_passes():
    result = validate_environment(_valid_env())
    assert result.ok
    assert result.errors == ()


def test_missing_brain_kek_fails():
    env = _valid_env()
    del env["BRAIN_KEK"]
    result = validate_environment(env)
    assert "BRAIN_KEK is required" in result.errors


def test_brain_kek_present_passes():
    env = _valid_env()
    env["BRAIN_KEK"] = "kek-redacted"
    assert "BRAIN_KEK is required" not in validate_environment(env).errors


def test_missing_faculty_code_without_gate_disabled_fails():
    env = _valid_env()
    del env["FACULTY_ACCESS_CODE"]
    result = validate_environment(env)
    assert any(error.startswith("FACULTY_ACCESS_CODE is required") for error in result.errors)


def test_faculty_gate_disabled_true_replaces_access_code():
    env = _valid_env()
    del env["FACULTY_ACCESS_CODE"]
    env["FACULTY_GATE_DISABLED"] = "true"
    result = validate_environment(env)
    assert not any("FACULTY_ACCESS_CODE" in error for error in result.errors)


def test_budget_guard_disabled_fails_without_uncapped_decision():
    env = _valid_env()
    env["OPENROUTER_BUDGET_GUARD_ENABLED"] = "false"
    result = validate_environment(env)
    assert any("OPENROUTER_BUDGET_GUARD_ENABLED" in error for error in result.errors)


def test_budget_unset_defaults_to_guarded_and_passes():
    env = _valid_env()
    del env["OPENROUTER_BUDGET_GUARD_ENABLED"]
    del env["OPENROUTER_BUDGET_FAIL_CLOSED"]
    result = validate_environment(env)
    assert not any("OPENROUTER_BUDGET" in error for error in result.errors)


@pytest.mark.parametrize("bad", [" ", "", "maybe", " true"])
@pytest.mark.parametrize(
    "name",
    ["OPENROUTER_BUDGET_GUARD_ENABLED", "FACULTY_GATE_DISABLED", "ALLOW_UNCAPPED_LLM_SPEND"],
)
def test_unparseable_boolean_fails_like_settings_does(name, bad):
    """Found by the test challenge pass: the preflight stripped and defaulted a
    value that pydantic rejects at import, so it passed an env that cannot boot."""
    env = _valid_env()
    env[name] = bad
    result = validate_environment(env)
    assert f"{name} is not a valid boolean" in result.errors


@pytest.mark.parametrize("good", ["TRUE", "0", "off", "Yes"])
def test_pydantic_boolean_spellings_are_accepted(good):
    env = _valid_env()
    env["FACULTY_GATE_DISABLED"] = good
    assert not any("not a valid boolean" in e for e in validate_environment(env).errors)


def test_allow_uncapped_spend_overrides_budget_guard():
    env = _valid_env()
    env["OPENROUTER_BUDGET_FAIL_CLOSED"] = "false"
    env["ALLOW_UNCAPPED_LLM_SPEND"] = "true"
    result = validate_environment(env)
    assert not any("OPENROUTER_BUDGET" in error for error in result.errors)
