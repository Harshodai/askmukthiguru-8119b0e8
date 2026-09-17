import logging
import os
import sys
import warnings

# Suppress all warnings ruthlessly during testing — must be set BEFORE any
# third-party imports to catch import-time warnings.
warnings.filterwarnings("ignore")

# The LangChainPendingDeprecationWarning (langchain_core bug) has a mismatch
# between its instance class and the category argument passed to warnings.warn,
# so filterwarnings("ignore") doesn't suppress it. Catch it with a static filter
# before any third-party import triggers it.
_orig_warn_fn = warnings.warn


def _suppress_langchain_warn(*args, **kwargs):
    if args and "allowed_objects" in str(args[0]):
        return
    return _orig_warn_fn(*args, **kwargs)


warnings.warn = _suppress_langchain_warn

# Unit/full tests must not emit spans to an external collector by default.
# Observability integration tests explicitly opt in with monkeypatch; this keeps
# ordinary test runs deterministic when Jaeger/OTLP is not running.
os.environ.setdefault("OTEL_ENABLED", "false")

# Add backend/ to sys.path first so that 'app' and 'services' imports resolve
# regardless of whether pytest is invoked from the repo root or backend/.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

# Configure threading limits before heavy numerical libraries are imported.
from app.core.threading_config import configure_threading

configure_threading()

# Redis logical database reserved for the test suite. The application uses /0;
# keeping the suite off it means the per-test flush below can never destroy a
# developer's running state.
_TEST_REDIS_DB = 15


def _resolve_test_redis_url() -> str:
    """Pick a Redis URL the test process can actually reach.

    An exported REDIS_URL always wins (CI, docker-compose runs). Otherwise fall
    back to the gitignored ``backend/.env`` — but rewrite its host, because that
    file is written for the compose network (``redis:6379``) and that name does
    not resolve on a developer's host, while the credentials in it do apply to
    the published localhost port.

    Why this exists: the previous passwordless ``redis://localhost:6379/0``
    default could not authenticate against a password-protected Redis, so 11
    tests failed with ``AuthenticationError: Authentication required`` /
    ``LLMBudgetUnavailable`` for anyone who had not exported REDIS_URL by hand.
    The failure looked like a code regression and was purely local config.

    Still never commits a password: the value is read at runtime from a file
    that is gitignored, and the last resort remains passwordless localhost.
    """
    explicit = os.environ.get("REDIS_URL")
    if explicit:
        return explicit

    env_file = os.path.join(_BACKEND_DIR, ".env")
    try:
        with open(env_file, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line.startswith("REDIS_URL="):
                    continue
                candidate = line.split("=", 1)[1].strip().strip("'\"")
                if not candidate:
                    break
                from urllib.parse import urlsplit, urlunsplit

                parts = urlsplit(candidate)
                if not parts.hostname:
                    break
                # Keep userinfo (the credentials) and port; swap only the host.
                userinfo = ""
                if parts.username or parts.password:
                    userinfo = parts.username or ""
                    if parts.password:
                        userinfo += f":{parts.password}"
                    userinfo += "@"
                port = f":{parts.port}" if parts.port else ""
                # Dedicated DB index: the app uses /0, and the suite flushes
                # whatever it is given between tests. Never point the tests at
                # the database a developer's running backend is using.
                return urlunsplit(
                    (parts.scheme, f"{userinfo}127.0.0.1{port}", f"/{_TEST_REDIS_DB}", "", "")
                )
    except OSError:
        pass

    return f"redis://localhost:6379/{_TEST_REDIS_DB}"


# Point REDIS_URL to local host-mapped Redis for testing. Env-driven, with the
# gitignored .env as a fallback source of credentials — never commit a Redis
# password.
os.environ["REDIS_URL"] = _resolve_test_redis_url()
# Unit tests exercise limiter behaviour separately; collection must not require
# a Redis client merely because integration services use REDIS_URL.
os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"
# Host-run tests use the mapped localhost port; Docker tests re-apply the
# Compose service hostname after `.env.test` is loaded below.
os.environ["IS_PRODUCTION"] = "false"

# Enable the X-Test-Key benchmark auth backdoor (dev-only; guarded by
# IS_PRODUCTION=false above). Set before any app.config import so
# services.auth_service registers TestAuthStrategy at import time.
os.environ["ENABLE_TEST_AUTH"] = "true"
# Non-production fixture value — only active under IS_PRODUCTION=false +
# ENABLE_TEST_AUTH=true. Override via BENCHMARK_SECRET env var in CI.
os.environ["BENCHMARK_SECRET"] = os.environ.get(
    "BENCHMARK_SECRET", "test-benchmark-secret-for-aal2-tests"
)  # gitleaks:allow


# Ensure JWT_SECRET is set for import-time validation
os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET", "mock_jwt_secret_for_testing_12345")
os.environ["SARVAM_API_KEY"] = os.environ.get("SARVAM_API_KEY", "mock_sarvam_key_for_testing")

from dotenv import load_dotenv

# Force loading .env.test for all tests
test_env_path = os.path.join(_BACKEND_DIR, ".env.test")
if os.path.exists(test_env_path):
    load_dotenv(test_env_path, override=True)

# `.env.test` may contain host defaults. Use the reachable Compose hostname
# inside Docker and the host-mapped port for host-run pytest.
os.environ["QDRANT_URL"] = (
    "http://qdrant:6333" if os.path.exists("/.dockerenv") else "http://127.0.0.1:6333"
)

# backend/.env sets SUPABASE_URL=http://host.docker.internal:54321 for the
# Compose network; that name does not resolve on a host-run pytest process
# (macOS/Linux dev machine), so every request 500s with
# "[Errno 8] nodename nor servname provided". Local Supabase Kong is reachable
# at localhost:54321 on the host. pydantic-settings reads .env itself (it
# doesn't populate os.environ), so an explicit os.environ["SUPABASE_URL"] is
# the only way to override it here — mirrors the REDIS_URL resolution above.
# An already-exported SUPABASE_URL (CI, staging) always wins.
if not os.path.exists("/.dockerenv") and not os.environ.get("SUPABASE_URL"):
    _env_supabase_url = None
    try:
        with open(os.path.join(_BACKEND_DIR, ".env"), encoding="utf-8") as _handle:
            for _raw in _handle:
                _line = _raw.strip()
                if _line.startswith("SUPABASE_URL="):
                    _env_supabase_url = _line.split("=", 1)[1].strip().strip("'\"")
                    break
    except OSError:
        pass
    if _env_supabase_url and "host.docker.internal" in _env_supabase_url:
        os.environ["SUPABASE_URL"] = _env_supabase_url.replace("host.docker.internal", "localhost")

# Disable rate limiting during tests to avoid Redis connections
from app.core.limiter import limiter

limiter.enabled = False

# app/api/chat.py's routes all Depends() on get_container_async, not
# get_container (L-DOCKER-18: sync Depends callables exhaust the AnyIO
# threadpool under load — see backend/CLAUDE.md). Several test modules
# (test_chat_endpoint.py, test_edge_cases.py, test_title_endpoint.py,
# test_input_truncation.py) predate that migration and only ever set
# `app.dependency_overrides[get_container] = ...`, so their mocked
# container never reached chat endpoints — the real dependency fell through
# to the live ServiceContainer (real Redis job queue), producing a live 202
# job-queue response instead of the test's mocked synchronous one. Mirror
# every override of one onto the other, once, here, instead of patching each
# of the ~40 call sites across those files.
from app.dependencies import get_container, get_container_async
from app.main import app as _app_for_overrides


class _MirroringOverrides(dict):
    """dict subclass: assigning get_container also assigns get_container_async
    (and vice versa) so a test only needs to override one to cover both.
    Also mirrors removal (__delitem__/pop) — a test that does
    `dependency_overrides.pop(get_container, None)` without this would leave
    get_container_async's mirrored entry stuck forever, since the outer
    _clear_dependency_overrides fixture only protects a test that never
    touches the dict outside its own setup/teardown; any test that pops mid-body
    and expects the pop to fully clear both keeps a stale get_container_async
    override for its own remaining assertions."""

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key is get_container:
            super().__setitem__(get_container_async, value)
        elif key is get_container_async:
            super().__setitem__(get_container, value)

    def __delitem__(self, key):
        super().__delitem__(key)
        paired = (
            get_container_async
            if key is get_container
            else (get_container if key is get_container_async else None)
        )
        if paired is not None and paired in self:
            super().__delitem__(paired)

    def pop(self, key, *default):
        result = super().pop(key, *default)
        paired = (
            get_container_async
            if key is get_container
            else (get_container if key is get_container_async else None)
        )
        if paired is not None:
            super().pop(paired, None)
        return result


_app_for_overrides.dependency_overrides = _MirroringOverrides(
    _app_for_overrides.dependency_overrides
)

import asyncio

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture
def supabase_client():
    """Provide a real Supabase client if SUPABASE_URL and SUPABASE_KEY are set.

    Skips the test with a clear message if either env var is missing,
    allowing tests to run in CI or environments without Supabase.
    """
    from app.config import settings

    supabase_url = settings.supabase_url
    supabase_key = settings.supabase_key

    if not supabase_url or not supabase_key or supabase_key == "":
        pytest.skip(
            "SUPABASE_URL or SUPABASE_KEY not set — skipping Supabase integration test. "
            "Set both in backend/.env or backend/.env.test to run."
        )

    try:
        from supabase import create_client

        client = create_client(supabase_url, supabase_key)
        # Verify connectivity with a lightweight request
        try:
            client.table("_prisma_migrations").select("*", count="exact").limit(1).execute()
        except Exception:
            pytest.skip(
                f"Supabase at {supabase_url} is not reachable — "
                "start the local Supabase stack with 'npx supabase start'"
            )
        logger.info("Supabase client initialized for %s", supabase_url)
        yield client
    except Exception as e:
        pytest.skip(f"Supabase client initialization failed: {e}")


@pytest.fixture(autouse=True)
def _restore_event_loop():
    # ponytail: asyncio.run() closes and unsets the thread's current event loop;
    # downstream tests using get_event_loop() then raise RuntimeError. Keep a
    # current loop alive before and after each test so cross-file ordering works.
    asyncio.set_event_loop(asyncio.new_event_loop())
    yield
    _close_global_redis_pool()
    asyncio.set_event_loop(asyncio.new_event_loop())


def _close_global_redis_pool():
    """Drop every module-level coalescer pool connection between tests.

    pytest-asyncio creates a fresh event loop per test, so a pooled redis
    connection created on test N's loop is dead by test N+1 and raises
    'Event loop is closed' / 'attached to a different loop' on reuse.
    Coalescers are built at import time (app/main.py:77, app/orchestrator.py:33)
    and their pools outlive every test loop. Closing via RedisCoalescer.close()
    is not enough: redis-py's aclose() does not remove connections from the
    pool lists when their transport is already dead, so we clear the lists
    directly. The pool lazily creates fresh connections on the next test's
    loop.
    """
    _log = logging.getLogger(__name__)
    for module_name, attr in (("app.main", "coalescer"), ("app.orchestrator", "_coalescer")):
        try:
            module = __import__(module_name, fromlist=[attr])
        except Exception as _ie:
            _log.debug("_close_global_redis_pool: could not import %s: %s", module_name, _ie)
            continue
        redis_client = getattr(getattr(module, attr, None), "_redis", None)
        pool = getattr(redis_client, "connection_pool", None)
        if pool is None:
            continue
        for list_attr in ("_available_connections", "_in_use_connections"):
            conns = getattr(pool, list_attr, ())
            try:
                conns.clear()
            except Exception as _ce:
                _log.debug(
                    "_close_global_redis_pool: could not clear %s.%s: %s",
                    module_name,
                    list_attr,
                    _ce,
                )


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    # ponytail: app.main._ADMIN_RATE_LIMITER / _AUTH_RATE_LIMITER are module-level
    # singletons. Redis is unreachable in this test env, so RedisBackedRateLimiter
    # silently falls back to its in-process ExponentialBackoffRateLimiter (or, if
    # REDIS_URL has no redis:// scheme, app.main constructs a plain TTLRateLimiter
    # directly) — either way, request counts accumulate across every test in the
    # same pytest process with nothing to reset them, causing spurious 429s late
    # in a full-file run that never reproduce in isolation. Reset before each test.
    from app.main import _ADMIN_RATE_LIMITER, _AUTH_RATE_LIMITER

    for _limiter in (_ADMIN_RATE_LIMITER, _AUTH_RATE_LIMITER):
        if hasattr(_limiter, "reset_fallback"):
            _limiter.reset_fallback()
        elif hasattr(_limiter, "reset"):
            _limiter.reset()

    # OpenRouterService's RPM counter is CLASS-level (shared across every
    # instance, on purpose -- see services/openrouter_service.py's class
    # docstring), so it also accumulates across every test in the same
    # pytest process unless reset here.
    from services.openrouter_service import OpenRouterService

    OpenRouterService.reset_shared_rate_limiter()

    # HealthMonitor (services/health_monitor.py) is a process-wide singleton
    # doing phi-accrual failure detection per dependency. A circuit breaker's
    # can_execute() consults it (settings.phi_accrual_enabled defaults True)
    # even for a brand-new DefaultCircuitBreaker instance, so any earlier test
    # that records 3+ consecutive failures for a provider (e.g. simulating a
    # 429/503) leaves it permanently unhealthy for every later test in the
    # same process — a fresh circuit breaker opens immediately on construction
    # with no failure of its own. Reproduced: test_openrouter.py passes in
    # isolation but fails when run after test_openrouter_resilience.py in the
    # same process. Reset before each test.
    from services.health_monitor import HealthMonitor

    HealthMonitor().reset_all()
    yield


@pytest.fixture(autouse=True)
def _default_startup_complete():
    # ponytail: app.api.chat._reject_if_queue_unattended() (2026-09-13, the
    # queue-safety fix) checks app.dependencies.startup_complete and 503s
    # when it's falsy. The real value is only ever set True by main.py's
    # lifespan, which never runs in these tests, so every /api/chat(/stream)
    # test got a 503 before reaching its actual test logic (queue-full,
    # Redis-outage, etc. — a real regression, caught by running the full
    # suite). Default it True here; test_chat_readiness_guard.py's own tests
    # monkeypatch it explicitly per-case and are unaffected by this default.
    import app.dependencies as _app_deps

    original = getattr(_app_deps, "startup_complete", False)
    _app_deps.startup_complete = True
    yield
    _app_deps.startup_complete = original


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    # ponytail: app.dependency_overrides is a dict on the single shared `app`
    # object imported by every test module; several tests (test_edge_cases.py,
    # test_chat_endpoint.py) set app.dependency_overrides[get_container] /
    # [get_current_user_from_supabase] and never clear it, so it leaks into
    # every test that runs later in the same process and shares `app` (e.g.
    # test_health.py's client = TestClient(app) — the exact failure this fixes).
    # Snapshot + restore rather than blind-clear, in case a future test wants
    # a genuinely persistent override across its own sub-tests.
    from app.main import app as _app

    saved = dict(_app.dependency_overrides)
    try:
        from services.tenant_context import TenantContext

        TenantContext.reset()
    except Exception:
        pass
    yield
    _app.dependency_overrides.clear()
    _app.dependency_overrides.update(saved)
    try:
        from services.tenant_context import TenantContext

        TenantContext.reset()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _flush_test_redis():
    """Clear the suite's Redis database between tests.

    Once conftest started resolving a REACHABLE Redis, the Redis-backed rate
    limiter began working — and six tests that had only ever passed because the
    limiter could not reach Redis started returning 429 (the admin limit is
    5/minute, and a test file makes more calls than that). They were green
    because a dependency was down, which is the opposite of reassuring:
    production has Redis.

    Flushing only the dedicated test database (_TEST_REDIS_DB), never /0.
    Best-effort — a missing or unreachable Redis must not fail a test that does
    not need one.
    """
    try:
        import redis as _redis

        client = _redis.from_url(os.environ["REDIS_URL"])
        client.flushdb()
    except Exception:
        client = None
    yield
    try:
        if client is not None:
            client.flushdb()
            client.close()
    except Exception:
        pass
