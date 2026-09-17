"""Tree-wide settings guards (Task R1 + Task S3, round-4 addendum step 5a: R2).

Replaces the original two-file scope with discovery: every directory
containing ``__init__.py`` under ``backend/`` minus ``_EXCLUDED_GUARD_DIRS``.
Pattern is the baselined debt-list guard: the frozen sorted baselines below
grandfather known debt, so the tests are green on day one and fail ONLY on
NEW names/sites. A baseline may shrink (fixed debt stays green); it must
never grow without an explicit test edit, so every addition is
reviewer-visible.

Exclusion list (each out for a documented reason, not by oversight):
- ``benchmarks``: offline load/eval harnesses; CLI-driven argparse-over-env,
  not the production request path.
- ``colab``: notebook/Colab bootstrap scripts; not server runtime.
- ``migrations``: offline one-shot schema/maintenance runner; not the
  request path (example blessed by the task spec: "migrations data").
- ``tests`` (incl. ``tests/security`` subtree): test-suite fixtures set env
  deliberately and assert on config; guarded separately, not shipped code.

Prior art (websearch 2026-09-13):
- pytest-ratchet (justified allowlist + bidirectional ratchet):
  https://github.com/YucelOzcan/pytest-ratchet
- a11y-violation-gate (grandfathered-baseline ratchet, fail only on new):
  https://github.com/testland/qa/blob/main/plugins/qa-accessibility/skills/a11y-violation-gate/SKILL.md
- allowlist-ratchet.cjs (identity-based, not count-based, ratchet):
  https://github.com/open-gsd/gsd-core/blob/next/scripts/lib/allowlist-ratchet.cjs

Baselines frozen 2026-09-13 at bf7ada3d: 12 undeclared ``getattr`` names,
63 ``file::VAR`` env-read sites (71 read lines; same-VAR multi-reads and
multiline calls collapse to one site). Task S3 absorbs 3 known gaps as
baseline debt (to pay down, not passes): ``web_ingest_request_timeout``
(backend/ingestion, via the ``app_settings`` alias the broadened regex now
catches), ``redis_password`` (backend/ops, no ``__init__.py`` so outside the
walked tree), ``supabase_service_role_key`` (backend/scripts, likewise
outside the walk). Pure writes (``os.environ[X] =``) and
``setdefault`` propagation are not reads and are excluded.

2026-09-16 ratchet DOWN (benchmark-unification workstream): ``backend/evaluation``
gained an ``__init__.py`` so ``_discover_guard_dirs()`` walks it for the first
time, and the 16 ``evaluation/*`` env-read sites plus the ``llm_judge_max_concurrent``
getattr that would have been found there were CONVERTED to ``app.config.settings``
rather than baselined. Both baselines shrank; neither grew.
"""

import pathlib
import re

from app.config import Settings

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

# Directories containing __init__.py that stay OUT of the guard, with reasons
# in the module docstring. Matching is subtree-based: "tests" excludes
# "tests/security" too.
_EXCLUDED_GUARD_DIRS = frozenset({"benchmarks", "colab", "migrations", "tests"})

_SKIP_DIR_PARTS = frozenset({"venv", ".venv", "__pycache__"})


def _discover_guard_dirs() -> tuple[str, ...]:
    found: set[str] = set()
    for init in _BACKEND.rglob("__init__.py"):
        rel = init.parent.relative_to(_BACKEND)
        if set(rel.parts) & _SKIP_DIR_PARTS:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] in _EXCLUDED_GUARD_DIRS:
            continue
        found.add(str(rel))
    return tuple(sorted(found))


_GETATTR_RE = re.compile(r'getattr\(\s*\w*[Ss]ettings\w*\s*,\s*["\']([^"\']+)["\']')
_ENV_LITERAL_RE = re.compile(
    r'os\.environ\.get\s*\(\s*["\']([^"\']+)["\']'
    r'|os\.environ\s*\[\s*["\']([^"\']+)["\']'
    r'|os\.getenv\s*\(\s*["\']([^"\']+)["\']'
)
_ENV_DYNAMIC_RE = re.compile(r'os\.environ\.get\(\s*([^"\'\s])|os\.getenv\(\s*([^"\'\s])')
_WRITE_LHS_RE = re.compile(r"os\.environ\s*\[[^\]]+\]\s*=(?!=)")

_DYNAMIC = "<dynamic>"

_GETATTR_DEBT_BASELINE = frozenset(
    {
        "citation_by_sentence",
        "crag_score_delta_ratio",
        "data_quality_gate_enabled",
        "git_sha",
        "kg_max_concurrent_queries",
        "lightrag_query_timeout_seconds",
        "llm_generate_timeout",
        "qdrant_timeout",
        "quality_gate_threshold",
        "redis_password",
        "sarvam_rpm_limit",
        "schema_version",
        "supabase_service_role_key",
        "upload_dir",
        "web_ingest_request_timeout",
    }
)

_ENV_READ_BASELINE = frozenset(
    {
        "app/api/compliance.py::COMPLIANCE_AUDIT_DIR",
        "app/api/memory.py::REDIS_URL",
        "app/core/database.py::AUTH_DB_PATH",
        "app/core/limiter.py::RATE_LIMIT_STORAGE_URI",
        "app/core/limiter.py::REDIS_URL",
        "app/db/seed_ontology.py::ENV",
        "app/llm_tracing.py::LLM_TRACE_CONTENT",
        "app/llm_tracing.py::LLM_TRACE_CONTENT_MAX_CHARS",
        "app/main.py::ENABLE_GRADIO_UI",
        "app/main.py::ENVIRONMENT",
        "app/main.py::GRADIO_PASS",
        "app/main.py::GRADIO_USER",
        "app/main.py::PYTHON_MEMORY_LIMIT_MB",
        "app/main.py::SENTENCE_TRANSFORMERS_HOME",
        "app/middleware/rate_limit.py::IS_PRODUCTION",
        "app/observability.py::OTEL_ENABLED",
        "app/observability.py::OTEL_EXPORTER_OTLP_ENDPOINT",
        "app/observability.py::OTEL_PYTHON_FASTAPI_EXCLUDED_URLS",
        "app/observability.py::OTEL_SERVICE_NAME",
        "app/orchestrator.py::REDIS_URL",
        "app/qa_wiring_check.py::REDIS_URL",
        "app/release_manifest.py::BUILD_TIMESTAMP",
        "app/release_manifest.py::CORPUS_VERSION",
        "app/release_manifest.py::GIT_SHA",
        "app/release_manifest.py::RAILWAY_GIT_COMMIT_SHA",
        "app/release_manifest.py::RELEASE_ID",
        "app/release_manifest.py::SCHEMA_VERSION",
        "app/telemetry_sink.py::SUPABASE_SERVICE_ROLE_KEY",
        "ingest/contextual_reingest.py::ALLOW_OPENROUTER_REINGEST",
        "ingest/contextual_reingest.py::OLLAMA_REINGEST_FALLBACK_MODEL",
        "ingest/contextual_reingest.py::OLLAMA_REINGEST_MODEL",
        "ingest/contextual_reingest.py::REINGEST_STATE_FILE",
        "ingest/pipeline.py::QDRANT_API_KEY",
        "ingest/pipeline.py::QDRANT_URL",
        "ingest/sources/supadata.py::SUPADATA_API_KEY",
        "ingest/youtube_loader.py::WEBSHARE_PROXY_URL",
        "ingest/youtube_loader.py::WHISPER_ONLY",
        "ingest/youtube_loader.py::YOUTUBE_COOKIES_B64",
        "ingest/youtube_loader.py::YOUTUBE_COOKIES_FILE",
        "services/compliance_logger.py::COMPLIANCE_AUDIT_DIR",
        "services/confidence_calibrator.py::CONFIDENCE_CALIBRATION_PATH",
        "services/config_watcher.py::HOTRELOAD_WATCH_PATHS",
        "services/cookie_helper.py::KEYCHAIN_PASS",
        "services/embedding_service.py::HF_HOME",
        "services/embedding_service.py::HF_REVISION",
        "services/embedding_service.py::PRUNE_UNUSED_HF_VARIANTS",
        "services/embedding_service.py::SENTENCE_TRANSFORMERS_HOME",
        "services/embedding_service.py::TRANSFORMERS_CACHE",
        "services/gateways/anthropic_gateway.py::<dynamic>",
        "services/gateways/sarvam_http.py::SARVAM_RPM_LIMIT",
        "services/layered_memory/persona_store.py::BRAIN_KEK",
        "services/layered_memory/persona_store.py::PERSONA_ENCRYPTION_SECRET",
        "services/lightrag_service.py::LIGHTRAG_WORKING_DIR",
        "services/memory_outbox.py::MEMORY_OUTBOX_WORKER_ID",
        "services/memory_service_v2.py::QDRANT_URL",
        "services/memory_service_v2.py::QDRANT_URL_V2",
        "services/memory_service_v2.py::REDIS_URL",
        "services/multi_provider_llm.py::<dynamic>",
        "services/onnx_reranker.py::HF_HOME",
        "services/push_service.py::FIREBASE_CREDENTIALS_JSON",
        "services/reranker_service.py::HF_HOME",
        "services/reranker_service.py::SENTENCE_TRANSFORMERS_HOME",
        "services/reranker_service.py::TRANSFORMERS_CACHE",
        "services/second_brain/second_brain_service.py::BRAIN_KEK",
        "services/turboquant_cache.py::TURBOQUANT_NATIVE_ENABLED",
    }
)


def _guard_files() -> list[pathlib.Path]:
    seen: set[pathlib.Path] = set()
    for dirname in _discover_guard_dirs():
        seen.update((_BACKEND / dirname).rglob("*.py"))
    return sorted(seen)


def _getattr_literals() -> set[str]:
    names: set[str] = set()
    for path in _guard_files():
        names.update(_GETATTR_RE.findall(path.read_text(errors="ignore")))
    return names


def _env_read_sites() -> set[str]:
    sites: set[str] = set()
    for path in _guard_files():
        kept: list[str] = []
        for line in path.read_text(errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _WRITE_LHS_RE.match(stripped):
                continue
            if "os.environ.setdefault" in line:
                continue
            kept.append(line)
        text = "\n".join(kept)
        rel = str(path.relative_to(_BACKEND))
        for match in _ENV_LITERAL_RE.finditer(text):
            var = match.group(1) or match.group(2) or match.group(3)
            sites.add(f"{rel}::{var}")
        if _ENV_DYNAMIC_RE.search(text):
            sites.add(f"{rel}::{_DYNAMIC}")
    return sites


def test_getattr_names_are_declared():
    s = Settings()
    new_undeclared = sorted(
        n for n in _getattr_literals() if not hasattr(s, n) and n not in _GETATTR_DEBT_BASELINE
    )
    assert not new_undeclared, f"NEW undeclared getattr(settings, ...) names: {new_undeclared}"


def test_no_direct_os_environ_in_owned_modules():
    # These two modules are the config chokepoint: every env value must reach
    # the app through Settings, never through a direct read here. Checked via
    # _env_read_sites() (which skips comments, docstrings, pure writes and
    # setdefault) rather than a bare `"os.environ" not in source` substring —
    # that naive form failed on 2026-09-16 against a *comment in app/config.py
    # explaining a fix that removed the reads*. A gate that fails on prose
    # describing its own satisfaction is a gate people switch off.
    sites = _env_read_sites()
    for rel in ("app/config.py", "services/llm_budget_guard.py"):
        offenders = sorted(s for s in sites if s.startswith(f"{rel}::"))
        assert not offenders, f"direct env read(s) in {rel}: {offenders}"
    new_sites = sorted(sites - _ENV_READ_BASELINE)
    assert not new_sites, f"NEW direct os.environ reads: {new_sites}"


def test_the_two_memory_write_flags_stay_separate():
    """`feature_memory_write` and `memory_write` are not duplicates.

    They gate different storage planes — the legacy outbox/Celery/episodic path
    and the canonical extractor/judge/resolver path respectively — and their
    defaults deliberately differ. Collapsing them onto one flag silently either
    switches the legacy outbox ON for everyone or switches canonical extraction
    OFF for everyone, so the merge waits on the two planes actually merging.
    """
    s = Settings()
    assert s.feature_memory_write is False
    assert s.memory_write is True

    base = pathlib.Path(__file__).resolve().parents[1]
    legacy = (base / "tasks/memory_outbox_tasks.py").read_text()
    canonical = (base / "app/container.py").read_text()
    assert "settings.feature_memory_write" in legacy
    assert "settings.memory_write" in canonical


# --- Orphan env-key sweep (defect class 6) ---------------------------------
#
# `.env.example` is the checked-in contract for what an operator is supposed
# to set. `Settings.model_config` uses ``extra="ignore"``, so a key documented
# there but declared on no field and read by no code is **silently dropped** —
# the operator sets it, nothing errors, and it configures nothing.
#
# That is not hypothetical: `supabase_anon_key` shipped exactly this way, so
# every caller that believed it was using the anon key was acting as
# **service_role** instead. Nothing in the app could have told you.
#
# Ratchet, not cliff: the five known orphans below are baselined with a reason
# each. The set may shrink (fixing debt stays green); it must never grow
# without an explicit, reviewer-visible edit to this file.

_ENV_EXAMPLE = _BACKEND / ".env.example"
_ENV_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=")

# Source extensions that can plausibly read an env var by name.
_ENV_CONSUMER_GLOBS = ("*.py", "*.yml", "*.yaml", "*.sh", "*.ts", "*.tsx", "*.mjs", "*.toml")

ORPHAN_ENV_KEYS_BASELINE: dict[str, str] = {
    "CELERY_BROKER_VISIBILITY_TIMEOUT": (
        "Documented for a Celery/SQS broker tuning knob that celery_config.py "
        "never wired. Setting it today changes nothing."
    ),
    "FACEBOOK_CLIENT_ID": (
        "Social-login placeholder. Supabase owns the OAuth provider config; "
        "the backend reads neither key."
    ),
    "FACEBOOK_CLIENT_SECRET": "See FACEBOOK_CLIENT_ID.",
    "RATE_LIMIT_PER_MINUTE": (
        "Superseded by the per-scope limiter settings in app/core/limiter.py "
        "(RATE_LIMIT_STORAGE_URI + per-route decorators). This single global "
        "number is read nowhere."
    ),
    "USE_OPENROUTER_FOR_SIMPLE": (
        "Predates the llm_factory provider split; routing is now decided by "
        "LLM_PROVIDER plus the classify/fast model settings."
    ),
}


def _env_example_keys() -> list[str]:
    keys: list[str] = []
    for line in _ENV_EXAMPLE.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_KEY_RE.match(stripped)
        if match:
            keys.append(match.group(1))
    return keys


def _declared_setting_names() -> set[str]:
    """Field names plus any explicit alias, lowercased. pydantic-settings
    matches env vars to fields case-insensitively, so lowercasing is the
    correct comparison key."""
    names: set[str] = set()
    for name, field in Settings.model_fields.items():
        names.add(name.lower())
        alias = getattr(field, "alias", None)
        if isinstance(alias, str):
            names.add(alias.lower())
    return names


def _keys_referenced_in_source() -> set[str]:
    """Env-var names appearing as a quoted literal anywhere in repo source.

    Deliberately broad (a plain quoted-substring match, not an
    ``os.getenv`` parse): a key consumed by docker-compose, a shell script,
    a third-party library's own env contract (MEMGRAPH_URI for lightrag), or
    the frontend still legitimately configures something. This sweep is only
    trying to catch the key that configures *nothing at all*.
    """
    root = _BACKEND.parent
    found: set[str] = set()
    candidates = set(_env_example_keys()) - _declared_setting_names()
    if not candidates:
        return found
    pattern = re.compile(r"[\"'](" + "|".join(re.escape(k) for k in sorted(candidates)) + r")[\"']")
    skip = _SKIP_DIR_PARTS | {"node_modules", ".git", "dist", ".pytest_cache", ".ruff_cache"}
    for glob in _ENV_CONSUMER_GLOBS:
        for path in root.rglob(glob):
            rel = path.relative_to(root)
            if set(rel.parts) & skip or any(p.startswith(".env") for p in rel.parts):
                continue
            if rel.parts[-1] == pathlib.Path(__file__).name:
                continue  # this guard's own baseline dict is not a consumer
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            found.update(pattern.findall(text))
    return found


def _orphan_env_keys() -> set[str]:
    declared = _declared_setting_names()
    referenced = _keys_referenced_in_source()
    return {
        key for key in _env_example_keys() if key.lower() not in declared and key not in referenced
    }


def test_no_new_orphan_env_keys():
    """Every `.env.example` key must be declared on Settings or read by name
    somewhere. An orphan is config theatre: the operator sets it, pydantic's
    ``extra="ignore"`` drops it, and nothing reports the gap."""
    new_orphans = sorted(_orphan_env_keys() - set(ORPHAN_ENV_KEYS_BASELINE))
    assert not new_orphans, (
        "NEW orphan key(s) in backend/.env.example — declared on no Settings "
        "field and read by no code, so setting them configures nothing:\n  - "
        + "\n  - ".join(new_orphans)
        + "\nDeclare the field on Settings (preferred), read it explicitly, "
        "delete the line, or baseline it in ORPHAN_ENV_KEYS_BASELINE with a reason."
    )


def test_orphan_env_key_baseline_has_no_stale_entries():
    """The baseline is a ratchet: an entry that is no longer an orphan (the
    key got declared, or the line was deleted) must be removed, so the list
    can only shrink."""
    stale = sorted(set(ORPHAN_ENV_KEYS_BASELINE) - _orphan_env_keys())
    assert not stale, (
        "ORPHAN_ENV_KEYS_BASELINE entries that are no longer orphans — remove "
        f"them so the baseline keeps shrinking: {stale}"
    )


if __name__ == "__main__":  # runnable self-check
    print(f".env.example keys: {len(_env_example_keys())}")
    print(f"declared Settings names: {len(_declared_setting_names())}")
    for key in sorted(_orphan_env_keys()):
        status = "baselined" if key in ORPHAN_ENV_KEYS_BASELINE else "NEW"
        print(f"  orphan [{status}]: {key}")
