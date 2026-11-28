"""Scaling/cost audit 2026-11-27: shared /api/health probe, cacheable /api/capabilities,
quiet telemetry consumer, lazy sklearn, pooled turn-counter client."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

import app.api.capabilities as capabilities
import app.api.health as health
import app.dependencies as app_dependencies
from app.config import settings


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {"type": "http", "method": "GET", "path": "/", "headers": raw, "query_string": b""}
    )


# ---- /api/health: one shared probe for public callers --------------------------------


@pytest.fixture()
def counted_probe(monkeypatch):
    calls = {"n": 0}

    async def fake_build(_container):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return JSONResponse(
            {"ready": True, "status": "healthy", "services": {"redis": {"ok": True}}}
        )

    monkeypatch.setattr(health, "_build_health_response", fake_build)
    monkeypatch.setattr(settings, "health_public_cache_ttl_s", 10.0)
    monkeypatch.setattr(settings, "metrics_scrape_token", "scrape-secret")
    health._public_health_cache.update(until=0.0, body=None, status=200)
    health._public_health_lock = None
    return calls


def test_public_health_concurrent_callers_share_one_probe(counted_probe) -> None:
    async def run():
        return await asyncio.gather(*(health.health_endpoint(_request(), None) for _ in range(20)))

    responses = asyncio.run(run())
    assert counted_probe["n"] == 1
    assert {r.status_code for r in responses} == {200}
    for r in responses:  # the public view stays redacted
        assert json.loads(r.body) == {"ready": True, "status": "healthy"}


def test_public_health_cache_expires_and_token_callers_always_probe(
    counted_probe, monkeypatch
) -> None:
    async def run():
        await health.health_endpoint(_request(), None)
        await health.health_endpoint(_request(), None)
        assert counted_probe["n"] == 1
        token = _request({"Authorization": "Bearer scrape-secret"})
        full = await health.health_endpoint(token, None)
        assert counted_probe["n"] == 2
        assert "services" in json.loads(full.body)  # token callers keep the deep body
        monkeypatch.setitem(health._public_health_cache, "until", time.monotonic() - 1)
        await health.health_endpoint(_request(), None)
        assert counted_probe["n"] == 3

    asyncio.run(run())


def test_public_health_ttl_zero_disables_cache(counted_probe, monkeypatch) -> None:
    monkeypatch.setattr(settings, "health_public_cache_ttl_s", 0.0)

    async def run():
        await health.health_endpoint(_request(), None)
        await health.health_endpoint(_request(), None)

    asyncio.run(run())
    assert counted_probe["n"] == 2


def test_public_health_never_caches_starting_state(monkeypatch) -> None:
    calls = {"n": 0}

    async def starting(_container):
        calls["n"] += 1
        return JSONResponse({"ready": False, "status": "starting", "services": {}})

    monkeypatch.setattr(health, "_build_health_response", starting)
    monkeypatch.setattr(settings, "health_public_cache_ttl_s", 10.0)
    health._public_health_cache.update(until=0.0, body=None, status=200)
    health._public_health_lock = None

    async def run():
        await health.health_endpoint(_request(), None)
        await health.health_endpoint(_request(), None)

    asyncio.run(run())
    assert calls["n"] == 2


# ---- /api/capabilities: ETag + Cache-Control + one render per TTL --------------------

_CONTAINER = SimpleNamespace(
    qdrant=object(),
    embedding=object(),
    ollama=object(),
    standard_graph=object(),
    lightrag_degraded=False,
    web_search=object(),
    job_queue=object(),
)


@pytest.fixture()
def ready_app(monkeypatch):
    monkeypatch.setattr(app_dependencies, "startup_complete", True)
    capabilities._manifest_cache.update(until=0.0, body=None, etag=None)
    renders = {"n": 0}
    real = capabilities.build_capability_manifest

    def counting(container):
        renders["n"] += 1
        return real(container)

    monkeypatch.setattr(capabilities, "build_capability_manifest", counting)
    return renders


def test_capabilities_cached_with_etag_and_304(ready_app, monkeypatch) -> None:
    monkeypatch.setattr(settings, "capabilities_cache_ttl_s", 60.0)

    async def run():
        first = await capabilities.capabilities_endpoint(_request(), _CONTAINER)
        etag = first.headers["etag"]
        assert first.headers["cache-control"] == "public, max-age=60"
        assert json.loads(first.body)["ready"] is True
        again = await capabilities.capabilities_endpoint(_request(), _CONTAINER)
        assert again.headers["etag"] == etag
        revalidated = await capabilities.capabilities_endpoint(
            _request({"If-None-Match": etag}), _CONTAINER
        )
        assert revalidated.status_code == 304 and not revalidated.body

    asyncio.run(run())
    assert ready_app["n"] == 1


def test_capabilities_not_ready_is_503_and_uncached(monkeypatch) -> None:
    monkeypatch.setattr(app_dependencies, "startup_complete", False)
    resp = asyncio.run(capabilities.capabilities_endpoint(_request(), _CONTAINER))
    assert resp.status_code == 503
    assert resp.headers["cache-control"] == "no-store"
    assert json.loads(resp.body) == {"ready": False, "capabilities": {}}


def test_capabilities_ttl_zero_renders_every_time(ready_app, monkeypatch) -> None:
    monkeypatch.setattr(settings, "capabilities_cache_ttl_s", 0.0)

    async def run():
        await capabilities.capabilities_endpoint(_request(), _CONTAINER)
        r = await capabilities.capabilities_endpoint(_request(), _CONTAINER)
        assert r.headers["cache-control"] == "no-cache"

    asyncio.run(run())
    assert ready_app["n"] == 2


# ---- telemetry consumer: no per-cycle GET, no extra sleep ----------------------------


def test_telemetry_worker_idle_loop_reads_cursor_once() -> None:
    from app.telemetry_sink import TelemetryWorker

    class FakeRedis:
        def __init__(self) -> None:
            self.gets = 0
            self.blocks: list[int] = []

        async def get(self, _key):
            self.gets += 1
            return b"5-0"

        async def xread(self, streams, count=None, block=None):
            self.blocks.append(block)
            assert streams == {"telemetry:stream": "5-0"}
            await asyncio.sleep(0.12)  # a real block that elapses with no message
            return []

    sink = SimpleNamespace(redis=FakeRedis(), client=object())
    worker = TelemetryWorker(sink)  # type: ignore[arg-type]

    async def run():
        worker.running = True
        task = asyncio.create_task(worker._loop())
        await asyncio.sleep(0.5)
        worker.running = False
        task.cancel()

    asyncio.run(run())
    assert sink.redis.gets == 1
    assert len(sink.redis.blocks) >= 3
    assert set(sink.redis.blocks) == {settings.telemetry_worker_block_ms}


# ---- ingest-only heavy imports stay out of the serving process -----------------------


def test_raptor_import_does_not_load_sklearn() -> None:
    code = "import sys, ingest.raptor; print('sklearn' in sys.modules or 'scipy' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip().endswith("False")


# ---- turn counter reuses one pooled client -------------------------------------------


def test_turn_counter_client_is_pooled(monkeypatch) -> None:
    import app.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "_TURN_REDIS", None)
    first = orchestrator._turn_counter_redis()
    assert orchestrator._turn_counter_redis() is first
    monkeypatch.setattr(orchestrator, "_TURN_REDIS", None)


# ---- admin-role lookup: negative results may be cached longer ------------------------


def test_admin_role_negative_cache_ttl(monkeypatch) -> None:
    import services.auth_service as auth
    import supabase

    lookups = {"n": 0}

    def fake_create_client(*_a, **_k):
        lookups["n"] += 1
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(supabase, "create_client", fake_create_client)
    strategy = auth.SupabaseAuthStrategy()
    stale = time.time() - 200  # older than the 90 s positive TTL

    async def run(ttl: int, cached_value: bool) -> bool:
        monkeypatch.setattr(auth.settings, "admin_role_negative_cache_ttl_s", ttl)
        strategy._admin_cache["u1"] = (cached_value, stale)
        return await strategy._check_admin_role("u1", "jwt")

    assert asyncio.run(run(600, False)) is False and lookups["n"] == 0  # negative reused
    assert asyncio.run(run(90, False)) is False and lookups["n"] == 1  # old default: re-checked
    assert asyncio.run(run(600, True)) is False and lookups["n"] == 2  # positive never extended
    strategy._admin_cache.clear()


# ---- in-process limiter state stays bounded ------------------------------------------


def test_ttl_rate_limiter_prunes_idle_keys_when_large() -> None:
    from app.security_utils import TTLRateLimiter

    limiter = TTLRateLimiter(ttl=60.0, max_requests=5)
    for i in range(limiter._PRUNE_ABOVE_KEYS + 50):
        limiter.is_allowed(f"ip{i}", now=1000.0)
    assert len(limiter._store) > limiter._PRUNE_ABOVE_KEYS
    assert limiter.is_allowed("fresh", now=1000.0 + 120.0)  # one ttl later: sweep runs
    assert len(limiter._store) == 1


def test_token_bucket_local_fallback_prunes_idle_buckets() -> None:
    from app.middleware.rate_limit import TokenBucketMiddleware

    mw = TokenBucketMiddleware(lambda *a, **k: None, redis_url="redis://localhost:1/0")
    old = time.time() - 10_000
    mw._local_buckets = {f"k{i}": (0.0, old) for i in range(10_100)}
    allowed, _ = mw._local_allowed("new")
    assert allowed and set(mw._local_buckets) == {"new"}


def test_token_bucket_sweep_runs_at_most_once_a_minute() -> None:
    from app.middleware.rate_limit import TokenBucketMiddleware

    mw = TokenBucketMiddleware(lambda *a, **k: None, redis_url="redis://localhost:1/0")
    old = time.time() - 10_000
    mw._local_buckets = {f"k{i}": (0.0, old) for i in range(10_100)}
    mw._local_allowed("a")  # sweeps
    assert set(mw._local_buckets) == {"a"}
    mw._local_buckets.update({f"j{i}": (0.0, old) for i in range(10_100)})
    mw._local_allowed("b")  # within a minute of the last sweep: no full scan
    assert len(mw._local_buckets) > 10_000


def test_degraded_session_sweep_is_rate_limited() -> None:
    from services.anon_quota_redis import AnonQuotaRedisAdapter

    adapter = AnonQuotaRedisAdapter.__new__(AnonQuotaRedisAdapter)
    adapter._degraded_lock = asyncio.Lock()
    adapter._last_degraded_sweep = 0.0
    adapter._degraded_sessions = {f"s{i}": 1.0 for i in range(10_100)}  # all expired

    async def run():
        await adapter._track_degraded("fresh", 60.0)
        assert set(adapter._degraded_sessions) == {"fresh"}
        adapter._degraded_sessions.update({f"t{i}": 1.0 for i in range(10_100)})
        await adapter._track_degraded("fresh2", 60.0)  # within a minute: no scan
        assert len(adapter._degraded_sessions) > 10_000

    asyncio.run(run())


# ---- telemetry cursor only moves forward ---------------------------------------------


def test_stream_cursor_never_moves_backwards() -> None:
    from app.telemetry_sink import _advance_stream_cursor, _stream_id_key

    class FakeRedis:
        def __init__(self, stored):
            self.stored = stored
            self.sets = []

        async def get(self, _key):
            return self.stored

        async def set(self, _key, value):
            self.stored = value.encode() if isinstance(value, str) else value
            self.sets.append(value)

    assert _stream_id_key(b"10-2") > _stream_id_key("9-99") > _stream_id_key("9-3")
    assert _stream_id_key("nonsense") == (-1, -1)

    async def run():
        r = FakeRedis(b"1700000000010-0")
        # a slower overlapping consumer tries to store an older id: refused, newer id returned
        assert await _advance_stream_cursor(r, "k", "1700000000005-3") == "1700000000010-0"
        assert r.sets == []
        # equal id: nothing to write
        assert await _advance_stream_cursor(r, "k", "1700000000010-0") == "1700000000010-0"
        assert r.sets == []
        # newer id: stored and returned
        assert await _advance_stream_cursor(r, "k", "1700000000010-1") == "1700000000010-1"
        assert r.sets == ["1700000000010-1"]
        # nothing stored yet
        assert await _advance_stream_cursor(FakeRedis(None), "k", "5-0") == "5-0"

    asyncio.run(run())


# ---- current Host allowlist behaviour (no setting needed, none added) ----------------


def test_trusted_host_dot_prefix_is_not_a_wildcard() -> None:
    """Starlette treats only "*.x" as a wildcard: ".railway.app" matches exactly that host,
    so a default-domain Host such as foo.up.railway.app is already rejected with 400."""
    from starlette.applications import Starlette
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    app = Starlette(routes=[Route("/", lambda r: PlainTextResponse("ok"))])
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", ".railway.app", "healthcheck.railway.app"],
    )

    def status(host: str) -> int:
        return TestClient(app, base_url=f"http://{host}").get("/").status_code

    assert status("foo.up.railway.app") == 400
    assert status("healthcheck.railway.app") == 200
