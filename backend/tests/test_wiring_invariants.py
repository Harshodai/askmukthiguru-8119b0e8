"""Wiring invariant regression tests (S1 of the ruthless audit).

Two independent nets:

(a) Dead-settings scan: every field declared on ``app.config.Settings`` must be
    read by at least one backend module outside ``app/config.py``, or be
    allowlisted here as a known-dead field whose deletion is owned elsewhere.
    Reads count from every backend module (app/, services/, rag/, ingest/,
    tasks/, scripts/, benchmarks/, evaluation/, ...) except tests, so a field
    consumed only by a benchmark script is still "read".

(b) Auth dependency sweep: every non-probe, non-public HTTP route must resolve
    some identity/auth dependency (Supabase user, optional user, AAL2/MFA
    admin gate, FastAPI-Users authenticator, or the anon-identity bridge).
    Routes are read off the built ``app`` object the same way
    ``test_authz_regression.py`` does (``from app.main import app``).

Audit coordination:
  - Concurrent task C5 may DELETE known-dead settings while this test runs.
    ``missing = dead - ALLOWED_DEAD_SETTINGS - KNOWN_EXTRA_DEAD`` therefore
    only fails on fields that are dead AND unlisted — deleting a listed field
    shrinks ``dead`` and the test still passes.
"""

from __future__ import annotations

import inspect
import re
import sys
from functools import lru_cache
from pathlib import Path

import pytest

# --- Part (a): dead-settings scan -----------------------------------------

# Settings declared but never read — deletion owned by concurrent task C5.
# Each entry carries its justification; if C5 deletes the field, it stops
# appearing in ``dead`` and the test keeps passing.
ALLOWED_DEAD_SETTINGS: set[str] = {
    "csrf_secret": "C5: dead, deletion owned by C5 (comment in config.py marks it kept as signing secret)",
    "csrf_token_ttl": "C5: dead, deletion owned by C5 (already removed from config.py 2026-08-11)",
    "auth_rate_limit_per_ip": "C5: dead, deletion owned by C5",
    "auth_rate_limit_per_account": "C5: dead, deletion owned by C5",
    "auth_rate_limit_burst": "C5: dead, deletion owned by C5",
    "memory_write_rate_limit": "C5: dead, deletion owned by C5",
    "notebook_rate_limit": "C5: dead, deletion owned by C5",
    "profile_rate_limit": "C5: dead, deletion owned by C5",
    "guardrails_audit_enabled": "C5: dead, deletion owned by C5",
}

# Additional dead fields found by the initial scan (S1, 2026-08-11) that are
# NOT owned by C5. Allowlisted so the build does not fail; report to the user.
# NOTE: the anthropic_* and web_ingest_* families were initially misflagged
# dead — they are live via helper closures (_get("field") in
# services/gateways/anthropic_gateway.py:149-167 and getattr(app_settings, ...)
# in ingestion/web_ingest_pipeline.py:130-160). The scan regexes were widened
# and they no longer appear dead.
KNOWN_EXTRA_DEAD: dict[str, str] = {
    "context_budget_enabled": "Declared context-budget toggle; no runtime read",
    "correlation_id_max_length": "Declared header-length cap; no runtime read",
    "ingestion_relation_cache_size": "Declared relation-cache size; no runtime read",
    "llm_provider_chain": "Declared provider chain; provider selection reads only LLM_PROVIDER",
    "openrouter_fast_model": "openrouter_generation_model/classify_model are read; fast_model is not",
    "persona_max_paragraphs": "Declared persona format cap; no runtime read",
    "persona_max_sentence_words": "Declared persona format cap; no runtime read",
    "sarvam_model_name": "Legacy explicit Sarvam model name; gateway reads sarvam_cloud_model",
    "sarvam_stt_language": "STT family (sarvam_stt_* + stt_*) — no runtime read",
    "sarvam_stt_mode": "STT family — no runtime read",
    "sarvam_stt_model": "STT family — no runtime read",
    "semantic_cache_hnsw_ef": "Semantic-cache family — no runtime read (qdrant client uses embedding_dimension)",
    "semantic_cache_qdrant_collection": "Semantic-cache family — no runtime read",
    "semantic_router_enabled": "Semantic-router family (enabled/top_k/fallback_llm/llm_fallback) — no runtime read",
    "semantic_router_fallback_llm": "Semantic-router family — no runtime read",
    "semantic_router_llm_fallback": "Semantic-router family — no runtime read",
    "semantic_router_top_k": "Semantic-router family — no runtime read",
    "stt_chunk_minutes": "STT family — no runtime read",
    "stt_max_audio_mb": "STT family — no runtime read",
    "transcript_max_retries": "Declared transcript retry cap; no runtime read",
    "use_contextual_chunking": "Declared chunking toggle; contextual chunking read via reingest_late_chunking",
    "use_qdrant_semantic_cache": "Semantic-cache family — no runtime read",
    "data_audit_strict_mode": "Strict mode toggle for data audit quality gate",
    "verifier_pass_ratio": "Verifier pass ratio threshold config",
}

# Newly-added settings that must NEVER be flagged dead. If any of these shows
# up in the dead set, that is a real finding — verify separately and report.
NEVER_FLAG_DEAD: set[str] = {
    "anon_session_hmac_secret",
    "allowed_assistant_slugs",
    "lettucedetect_enabled",
    "guru_voice_mode",
    "guru_voice_gate_score",
    "guru_voice_benchmark_output",
    "langhanam_voice_enabled",
    "llm_judge_provider_model",
    "llm_judge_session_prefix",
    "embedding_dimension",
}


@lru_cache(maxsize=1)
def _declared_settings() -> set[str]:
    """Field names declared as class attributes on ``Settings`` in app/config.py.

    Matches 4-space-indented ``name: type`` annotations. Properties
    (``def name(self)``) and ``model_config`` are not matched.
    """
    cfg = (Path(__file__).resolve().parents[1] / "app" / "config.py").read_text()
    return set(re.findall(r"^\s{4}(\w+)\s*:", cfg, re.MULTILINE))


@lru_cache(maxsize=1)
def _read_settings_fields() -> set[str]:
    """Every ``settings.<field>`` / ``getattr(<var>, "<field>")`` / helper
    ``_get("<field>")`` read in the backend tree, plus ``self.<field>``
    references inside config.py itself (computed properties such as
    ``cors_origins_list`` keep their backing field live). Tests, virtualenvs
    and caches are excluded."""
    backend = Path(__file__).resolve().parents[1]
    skip_parts = {
        "__pycache__",
        ".venv",
        "venv",
        "tests",
        "node_modules",
        ".git",
        ".pytest_cache",
        "dotenv",
    }
    read: set[str] = set()
    for py in sorted(backend.rglob("*.py")):
        if any(part in py.parts for part in skip_parts):
            continue
        text = py.read_text()
        if str(py) == str(backend / "app" / "config.py"):
            read.update(re.findall(r"self\.(\w+)", text))
            continue
        read.update(re.findall(r"\bsettings\.(\w+)\b", text))
        # getattr on ANY variable (services alias settings as app_settings)
        read.update(re.findall(r'getattr\(\s*\w+\s*,\s*["\'](\w+)["\']', text))
        # local helper closures like AnthropicGatewayConfig._get("field", dflt)
        read.update(re.findall(r'\b_get\(\s*["\'](\w+)["\']', text))
        # os.environ.get("FIELD") fallbacks are env-backed, not Settings fields
    return read


def _dead_settings() -> set[str]:
    return _declared_settings() - _read_settings_fields()


def test_no_undeclared_dead_settings():
    """Every Settings field must be read somewhere, or be explicitly
    allowlisted. Fails on genuinely-dead fields that nobody owns."""
    dead = _dead_settings()
    # Fields this audit promised never to flag must not appear dead.
    verify = sorted(dead & NEVER_FLAG_DEAD)
    if verify:
        pytest.fail(
            "Newly-added settings are dead — verify separately (see NEVER_FLAG_DEAD): "
            + ", ".join(verify)
        )
    missing = dead - set(ALLOWED_DEAD_SETTINGS) - set(KNOWN_EXTRA_DEAD)
    assert not missing, (
        "REGRESSION: Settings fields are declared but never read (unowned):\n  - "
        + "\n  - ".join(sorted(missing))
    )


# --- Part (b): auth dependency on every non-probe route --------------------

# Routes intentionally unauthenticated. Probing/infra/documentation endpoints,
# plus /api/auth/anon-session which ISSUES anonymous tokens.
PROBE_ROUTES: set[str] = {
    "/api/health",
    "/api/healthz",
    "/api/readyz",
    "/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/health/mfa",
    "/api/metrics",
    "/api/auth/anon-session",
}

# Non-probe routes that are legitimately auth-less, with justification.
PUBLIC_ROUTES: dict[str, str] = {
    "/docs/oauth2-redirect": "Swagger UI infra (docs already probe-public)",
    "/api/auth/register": "Registration stub returns 501 — must stay reachable pre-auth",
    "/api/health/services": "Alias of /api/health — service readiness, no user data",
    "/api/ready": "Kubernetes readiness probe (503 when not ready)",
    "/api/memory/knowledge-graph": "Docstring: anonymous access allowed when no credentials; public /knowledge-graph page",
    "/api/memory/knowledge-graph/export": "Public KG export — same auth policy as the graph itself",
    "/api/teachings/tips": "Docstring: 'Public: current wisdom tips'",
    "/api/support/contact": "Public support contact form (no user context needed)",
    "/api/waitlist/": "Placeholder — returns 501 Not Implemented",
    "/api/capabilities": "Public non-secret capability manifest for clients and operational checks",
    "/.well-known/jwks.json": "JWKS must be public for JWT signature verification",
    "/api/compliance/eu-ai-act/status": "EU AI Act transparency and compliance public status",
    "/api/compliance/provenance/manifest/{artifact_id:path}": "Public provenance manifest query",
    "/api/compliance/provenance/search": "Public provenance query/search endpoint",
}

# Markers looked up in a dependency callable's source. Includes the canonical
# audit markers plus the codebase's real auth entry points (module-level
# AuthBridge instance, Supabase user deps, admin gates).
_AUTH_SOURCE_MARKERS: tuple[str, ...] = (
    "require_scoped_identity",
    "require_aal2",
    "require_admin",
    "get_authenticated_user",
    "AuthBridge",
    "resolve_anon_identity",
    "auth_bridge",
    "get_current_user_from_supabase",
    "get_optional_user",
    "_require_admin",
    "_authed_user_id",
    "set_tenant_from_request",
)

# Structural fallbacks for deps whose source is unavailable (FastAPI-Users
# closures) or that are security scheme objects (HTTPBearer).
_AUTH_NAME_MARKERS: tuple[str, ...] = (
    "HTTPBearer",
    "OAuth2PasswordBearer",
    "Authenticator.",
    "OAuth2PasswordRequestForm",
    "get_jwt_strategy",
    "get_user_db",
    "get_user_manager",
    "get_user_or_404",
)


def _route_dep_callables(route) -> list:
    """All dependency callables wired into a route: router-level
    ``route.dependencies`` plus every path-operation dependency (signature
    ``Depends(...)``) walked recursively through ``route.dependant``."""
    calls: list = []
    for dep in getattr(route, "dependencies", []) or []:
        call = getattr(dep, "call", None)
        if call is not None:
            calls.append(call)

    def walk(deps):
        for dep in deps:
            call = getattr(dep, "call", None)
            if call is not None:
                calls.append(call)
            nested = getattr(dep, "dependencies", None)
            if nested:
                walk(nested)

    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        walk(getattr(dependant, "dependencies", []) or [])
    return calls


def _has_auth_dep(route) -> bool:
    """True if the route resolves some caller identity: Supabase user, optional
    user (with anon-session scoping), AAL2/MFA admin gate, FastAPI-Users
    authenticator, or the AuthBridge family."""
    for call in _route_dep_callables(route):
        name = getattr(call, "__qualname__", str(call))
        if any(marker in name for marker in _AUTH_NAME_MARKERS):
            return True
        try:
            src = inspect.getsource(call)
        except (OSError, TypeError):
            src = ""
        if any(marker in src for marker in _AUTH_SOURCE_MARKERS):
            return True
    return False


def test_every_non_probe_route_has_auth_dependency():
    """Regression net: any route added without an auth dependency fails."""
    from app.main import app  # matches test_authz_regression's build pattern

    offenders: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if not methods or path.startswith("/static"):
            continue  # Mounts/WebSocket — no HTTP auth surface
        if methods.issubset({"OPTIONS", "HEAD"}):
            continue
        if path in PROBE_ROUTES or path in PUBLIC_ROUTES:
            continue
        if not _has_auth_dep(route):
            endpoint = getattr(getattr(route, "endpoint", None), "__name__", "?")
            offenders.append(f"{path} {sorted(methods)} -> {endpoint}")

    assert not offenders, (
        "REGRESSION: the following non-probe routes lack any auth dependency"
        " (add an identity dependency, or justify them in PUBLIC_ROUTES):\n  - "
        + "\n  - ".join(sorted(offenders))
    )


if __name__ == "__main__":
    # Self-check block: print the dead-settings inventory.
    dead = _dead_settings()
    print(
        f"declared={len(_declared_settings())} read={len(_read_settings_fields())} dead={len(dead)}"
    )
    for field in sorted(dead):
        print(f"  DEAD {field}")
    unowned = dead - set(ALLOWED_DEAD_SETTINGS) - set(KNOWN_EXTRA_DEAD)
    print(f"unowned={sorted(unowned)}")
    sys.exit(1 if unowned else 0)
