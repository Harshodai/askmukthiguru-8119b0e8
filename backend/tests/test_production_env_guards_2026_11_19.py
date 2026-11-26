"""Never-again guards for a .env-derived production variable set (2026-11-19).

Failure classes seen today: a local .env copied onto Railway (overwrote BRAIN_KEK,
which bricked the vault), dev hosts and local Supabase keys reaching production.
"""

from __future__ import annotations

import base64
import json

import pytest

from scripts.ops.validate_production_env import validate_environment
from tests.test_production_env_preflight import _valid_env


def _jwt(payload: dict) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64(payload)}.sig"


@pytest.mark.parametrize(
    "name,value",
    [
        ("SUPABASE_URL", "http://127.0.0.1:54321"),
        ("SUPABASE_URL", "http://host.docker.internal:54321"),
        ("QDRANT_URL", "http://qdrant:6333"),
        ("REDIS_URL", "redis://:pw@redis:6379/0"),
        ("NEO4J_URI", "bolt://localhost:7687"),
        ("MEMGRAPH_URI", "bolt://memgraph:7687"),
    ],
)
def test_dev_hosts_are_refused(name, value):
    env = {**_valid_env(), name: value}
    result = validate_environment(env)
    assert any(name in e and "development host" in e for e in result.errors), result.errors
    assert value not in " ".join(result.errors)  # the value (may hold a password) is not echoed


@pytest.mark.parametrize(
    "value",
    [
        "redis://default:pw@redis.railway.internal:6379",
        "rediss://redis.example/0",
        "http://qdrant.railway.internal:6333",
    ],
)
def test_real_hosts_pass(value):
    assert validate_environment({**_valid_env(), "REDIS_URL": value}).ok


def test_local_supabase_demo_key_is_refused():
    env = {**_valid_env(), "SUPABASE_KEY": _jwt({"iss": "supabase-demo", "role": "service_role"})}
    assert any("local Supabase" in e for e in validate_environment(env).errors)
    real = {**_valid_env(), "SUPABASE_KEY": _jwt({"iss": "supabase", "role": "service_role"})}
    assert validate_environment(real).ok


def test_is_production_false_is_refused():
    assert (
        "IS_PRODUCTION must be true"
        in validate_environment({**_valid_env(), "IS_PRODUCTION": "false"}).errors
    )


@pytest.mark.parametrize("name", ["BRAIN_KEK", "SUPABASE_JWT_SECRET", "SUPABASE_KEY", "JWT_SECRET"])
def test_overwriting_a_data_protecting_secret_is_refused(name):
    proposed = {**_valid_env(), name: "new-value"}
    current = {name: "old-value"}
    result = validate_environment(proposed, current=current)
    assert any(name in e and "overwrite" in e for e in result.errors), result.errors
    assert "old-value" not in " ".join(result.errors) and "new-value" not in " ".join(result.errors)


def test_same_secret_or_first_set_is_allowed():
    env = _valid_env()
    assert validate_environment(env, current={"BRAIN_KEK": env["BRAIN_KEK"]}).ok
    assert validate_environment(env, current={}).ok  # a brand-new service holds no data yet


def test_quantized_image_with_encoder_on_warns():
    env = {**_valid_env(), "QUANTIZED_ONLY": "true"}
    assert any("MiniLM" in w for w in validate_environment(env).warnings)
    env["ON_DEVICE_INTENT_ENCODER_ENABLED"] = "false"
    assert not any("MiniLM" in w for w in validate_environment(env).warnings)


def test_scheme_less_host_vars_are_checked():
    assert any(
        "REDIS_HOST" in e
        for e in validate_environment({**_valid_env(), "REDIS_HOST": "localhost"}).errors
    )
    assert validate_environment({**_valid_env(), "REDIS_HOST": "redis.railway.internal"}).ok


def test_env_file_parser_drops_inline_comments_but_keeps_quoted_hashes(tmp_path):
    from scripts.ops.validate_production_env import _read_env_file

    f = tmp_path / "x.env"
    f.write_text(
        "export A=1 # note\nB=\"pa#ss\" # inline comment\nC='q'\n# full comment\nD=plain # comment\n",
        encoding="utf-8",
    )
    assert _read_env_file(str(f)) == {"A": "1", "B": "pa#ss", "C": "q", "D": "plain"}


def test_invalid_boolean_flag_fails_even_without_quantized_only():
    env = {
        **_valid_env(),
        "QUANTIZED_ONLY": "false",
        "ON_DEVICE_INTENT_ENCODER_ENABLED": "not-a-bool",
    }
    result = validate_environment(env)
    assert any(
        "ON_DEVICE_INTENT_ENCODER_ENABLED is not a valid boolean" in e for e in result.errors
    )


def test_scheme_host_with_query_params_strips_params():
    from scripts.ops.validate_production_env import _host_of

    assert _host_of("redis://redis:6379/0?ssl=true") == "redis"
    assert (
        _host_of("redis://default:pw@redis.railway.internal:6379?query=1")
        == "redis.railway.internal"
    )
