"""U2: the live first-person-only posture is pinned for backend AND celery-worker."""
import re
from pathlib import Path

IAC = (Path(__file__).resolve().parents[2] / ".railway" / "railway.ts").read_text()

EXPECTED = {
    "FIRST_PERSON_SERVING_POSTURE": "v12_shadow",
    "FIRST_PERSON_CONTEXT_HARNESS_ENABLED": "true",
    "FIRST_PERSON_CONTEXT_TERMINAL_ENABLED": "true",
    "FIRST_PERSON_COLLECTION": "first_person_v12_shadow",
    "FIRST_PERSON_CONTEXT_COLLECTION": "first_person_v12_shadow",
    "FIRST_PERSON_CHAT_BRIDGE_ENABLED": "true",
    "FIRST_PERSON_LLM_FALLBACK_ENABLED": "false",
    "FIRST_PERSON_SERVE_WEAK_MATCH": "true",
    "FIRST_PERSON_REQUIRE_SPEAKER_VERIFIED": "true",
    "FIRST_PERSON_RELEVANCE_MIN_SCORE": "2",
    "DISTRESS_LLM_ESCALATION_ENABLED": "true",
    "FIRST_PERSON_CONTEXT_USE_SPARSE": "false",
    "FIRST_PERSON_LLM_RERANK_ENABLED": "false",
    "SEMANTIC_CACHE_ENABLED": "false",
    "WEB_SEARCH_ENABLED": "false",
    "FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED": "true",
    "FIRST_PERSON_HYDE_ENABLED": "true",
    "FIRST_PERSON_RELEVANCE_MODEL": "anthropic/claude-haiku-5.5",
}


def _v10_and_live_blocks() -> str:
    v10 = IAC.split('SERVING_POSTURE === "v12_shadow"')[1].split(": SERVING_POSTURE === ")[0]
    live = IAC.split("const livePosture = {")[1].split("};")[0]
    return v10 + live


def _service_env(name: str) -> str:
    return IAC.split(f'service("{name}"')[1].split("env: {")[1].split("\n    },")[0]


def test_every_posture_var_pinned_once_with_expected_value():
    blocks = _v10_and_live_blocks().replace("SERVING_POSTURE,", '"v12_shadow",')
    for var, want in EXPECTED.items():
        vals = re.findall(rf'\b{var}: "?([A-Za-z0-9_./-]+)"?,', blocks)
        assert vals == [want], (var, vals)


def test_backend_and_worker_spread_both_blocks():
    for svc in ("askmukthiguru-8119b0e8", "celery-worker"):
        env = _service_env(svc)
        assert "...postureEnv," in env and "...livePosture," in env, svc
        for var in EXPECTED:  # no service may override a pinned var differently
            assert not re.search(rf"\b{var}:", env), (svc, var)


def test_gotcha_settings_pinned():
    assert 'healthcheck: "/api/healthz"' in IAC
    assert 'FORWARDED_ALLOW_IPS: "10.0.0.0/8"' in IAC
    assert 'PYTHON_MEMORY_LIMIT_MB: "0"' in IAC


def test_hash_check_flag_removed_not_pinned():
    # Integrity re-check on cache replay is always on (owner decision 2026-11-16).
    assert "POINTS_SERVABLE_HASH_CHECK" not in IAC
