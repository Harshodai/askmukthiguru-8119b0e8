from __future__ import annotations

from unittest.mock import patch

from services.cache.redis_adapter import RedisCacheAdapter


class _FakeRedis:
    def __init__(self, keys: list[str], ttls: dict[str, int] | None = None) -> None:
        self.keys = list(keys)
        self.ttls = ttls or {}
        self.setex_calls: list[tuple[str, int, str]] = []

    def ping(self) -> bool:
        return True

    def scan_iter(self, match: str | None = None, count: int = 0):
        del count
        if match is None:
            yield from self.keys
            return
        prefix = match.rstrip("*")
        yield from (key for key in self.keys if key.startswith(prefix))

    def ttl(self, key: str) -> int:
        return self.ttls.get(key, 60)

    def exists(self, key: str) -> bool:
        return key in self.keys

    def setex(self, key: str, ttl: int, payload: str) -> None:
        self.setex_calls.append((key, ttl, payload))


def _adapter(fake: _FakeRedis, max_keys: int) -> RedisCacheAdapter:
    with patch("redis.from_url", return_value=fake):
        return RedisCacheAdapter(
            redis_url="redis://cache",
            max_keys=max_keys,
            telemetry_interval_seconds=5,
        )


def test_budget_rejection_fires_at_namespace_ceiling() -> None:
    fake = _FakeRedis(
        ["mukthiguru:cache:tenant-a:key-1", "mukthiguru:cache:tenant-a:key-2"]
    )
    adapter = _adapter(fake, max_keys=2)

    adapter.put("new query", "response", "general", [])

    assert fake.setex_calls == []


def test_telemetry_snapshot_reports_namespace_and_budget() -> None:
    fake = _FakeRedis(
        [
            "mukthiguru:cache:tenant-a:key-1",
            "mukthiguru:cache:tenant-a:key-2",
            "unrelated:key",
        ],
        ttls={"mukthiguru:cache:tenant-a:key-1": -1},
    )
    adapter = _adapter(fake, max_keys=10_000)

    snapshot = adapter.telemetry_snapshot()

    assert snapshot == {
        "keys": 2,
        "nonexpiring": 1,
        "namespace": "exact_query",
        "max_keys": 10_000,
    }


def test_existing_key_can_refresh_at_budget_ceiling() -> None:
    fake = _FakeRedis(
        ["mukthiguru:cache:tenant-a:key-1", "mukthiguru:cache:tenant-a:key-2"]
    )
    adapter = _adapter(fake, max_keys=2)

    with patch.object(adapter, "_make_key", return_value=fake.keys[0]):
        adapter.put("existing query", "response", "general", [])

    assert len(fake.setex_calls) == 1


def test_zero_budget_disables_rejection_for_compatibility() -> None:
    fake = _FakeRedis([f"mukthiguru:cache:tenant-a:key-{i}" for i in range(25)])
    adapter = _adapter(fake, max_keys=0)

    adapter.put("new query", "response", "general", [])

    assert len(fake.setex_calls) == 1


def test_factory_passes_cache_budget_settings() -> None:
    from services.cache.factory import CacheFactory

    with (
        patch("services.cache.factory.RedisCacheAdapter") as constructor,
        patch.object(
            CacheFactory,
            "_resolve_mode",
            return_value="redis",
        ),
    ):
        CacheFactory.create_exact_cache()

    kwargs = constructor.call_args.kwargs
    assert kwargs["max_keys"] == 10_000
    assert kwargs["telemetry_interval_seconds"] == 60
