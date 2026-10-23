from app.config import FIRST_PERSON_MODES
from scripts.ops.validate_production_env import _read_first_person_modes, validate_environment


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
    }


def test_valid_production_environment_passes():
    result = validate_environment(_valid_env())
    assert result.ok
    assert result.errors == ()


def test_missing_required_values_fail_closed():
    result = validate_environment({"IS_PRODUCTION": "true"})
    assert not result.ok
    assert "SUPABASE_KEY is required" in result.errors
    assert "REDIS_URL is required" in result.errors


def test_wildcard_proxy_and_test_auth_are_rejected():
    env = _valid_env()
    env.update({"FORWARDED_ALLOW_IPS": "*", "ENABLE_TEST_AUTH": "true"})
    result = validate_environment(env)
    assert "FORWARDED_ALLOW_IPS must not be '*'" in result.errors
    assert "ENABLE_TEST_AUTH must be false in production" in result.errors


def test_first_person_mode_validation():
    env = _valid_env()
    env["FIRST_PERSON_MODE"] = "retrieval_only"
    result = validate_environment(env)
    assert result.ok

    env["FIRST_PERSON_MODE"] = "bogus_mode"
    result_invalid = validate_environment(env)
    assert not result_invalid.ok
    assert (
        "FIRST_PERSON_MODE must be one of ('disabled', 'retrieval_only', 'hybrid')"
        in result_invalid.errors
    )

    # 2026-10-20: "editorial" was accepted by QuoteWeaver but declared nowhere.
    # The preflight and app.config.FIRST_PERSON_MODES must agree, so it is now
    # rejected here too.
    env["FIRST_PERSON_MODE"] = "editorial"
    result_editorial = validate_environment(env)
    assert not result_editorial.ok
    assert (
        "FIRST_PERSON_MODE must be one of ('disabled', 'retrieval_only', 'hybrid')"
        in result_editorial.errors
    )


def test_source_parse_matches_app_config_modes():
    """The dependency-free parse must never drift from the real constant."""
    assert _read_first_person_modes() == FIRST_PERSON_MODES


def test_mode_check_survives_an_incomplete_environment():
    """A bare env must not turn the mode check into a settings build failure."""
    result = validate_environment({"IS_PRODUCTION": "true", "FIRST_PERSON_MODE": "retrieval_only"})
    assert not any("FIRST_PERSON_MODE" in error for error in result.errors)
