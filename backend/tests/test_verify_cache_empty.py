"""`make verify-cache-empty` is the proof a flush worked, so its exit status is its contract.

Exit codes: 0 = every cache empty, 1 = something cached, 2 = a store was
unreachable (unreachable is NOT empty -- a gate that reads "can't connect" as
"nothing cached" certifies a stale cache as clean).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "ops" / "verify_cache_empty.py"
_FLUSH = _REPO / "scripts" / "ops" / "flush_cache.py"

# Every Redis cache prefix the backend writes (grep of backend/services + app).
EXPECTED_PREFIXES = (
    "mukthiguru:cache:*",
    "mukthiguru:semcache:*",
    "cache:first_person_exact:*",
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    assert _SCRIPT.exists(), "scripts/ops/verify_cache_empty.py is missing"
    return _load(_SCRIPT, "verify_cache_empty_under_test")


def _redis(mod, counts, dbsize=0):
    base = {p: 0 for p in mod.REDIS_PATTERNS}
    base.update(counts)
    return {"dbsize": dbsize, "patterns": base}


def _qdrant(mod, counts=None):
    base = {c: "absent" for c in mod.qdrant_collections(1024)}
    base.update(counts or {})
    return base


def test_all_known_cache_prefixes_are_checked(mod):
    assert set(EXPECTED_PREFIXES) <= set(mod.REDIS_PATTERNS)


def test_empty_exits_zero(mod, monkeypatch):
    monkeypatch.setattr(mod, "_redis_counts", lambda args: _redis(mod, {}, dbsize=12))
    monkeypatch.setattr(mod, "_qdrant_counts", lambda args: _qdrant(mod))
    assert mod.main([]) == 0


@pytest.mark.parametrize("prefix", EXPECTED_PREFIXES)
def test_any_redis_cache_key_exits_one(mod, monkeypatch, prefix):
    monkeypatch.setattr(mod, "_redis_counts", lambda args: _redis(mod, {prefix: 1}))
    monkeypatch.setattr(mod, "_qdrant_counts", lambda args: _qdrant(mod))
    assert mod.main([]) == 1


def test_non_empty_qdrant_collection_exits_one(mod, monkeypatch):
    coll = mod.qdrant_collections(1024)[0]
    monkeypatch.setattr(mod, "_redis_counts", lambda args: _redis(mod, {}))
    monkeypatch.setattr(mod, "_qdrant_counts", lambda args: _qdrant(mod, {coll: 3}))
    assert mod.main([]) == 1


def test_present_but_empty_qdrant_collection_is_empty(mod, monkeypatch):
    coll = mod.qdrant_collections(1024)[0]
    monkeypatch.setattr(mod, "_redis_counts", lambda args: _redis(mod, {}))
    monkeypatch.setattr(mod, "_qdrant_counts", lambda args: _qdrant(mod, {coll: 0}))
    assert mod.main([]) == 0


def test_redis_unreachable_is_not_empty(mod, monkeypatch):
    def boom(args):
        raise mod.Unreachable("redis: connection refused")

    monkeypatch.setattr(mod, "_redis_counts", boom)
    monkeypatch.setattr(mod, "_qdrant_counts", lambda args: _qdrant(mod))
    assert mod.main([]) not in (0, None)


def test_qdrant_unreachable_is_not_empty(mod, monkeypatch):
    def boom(args):
        raise mod.Unreachable("qdrant: connection refused")

    monkeypatch.setattr(mod, "_redis_counts", lambda args: _redis(mod, {}))
    monkeypatch.setattr(mod, "_qdrant_counts", boom)
    assert mod.main([]) not in (0, None)


def test_non_empty_beats_unreachable(mod, monkeypatch):
    def boom(args):
        raise mod.Unreachable("qdrant down")

    monkeypatch.setattr(mod, "_redis_counts", lambda args: _redis(mod, {EXPECTED_PREFIXES[0]: 2}))
    monkeypatch.setattr(mod, "_qdrant_counts", boom)
    assert mod.main([]) == 1


class _ScanOnlyRedis:
    """Fake redis client: KEYS is forbidden (blocks the server), SCAN is the only path."""

    def __init__(self, keys):
        self._keys = keys

    def ping(self):
        return True

    def dbsize(self):
        return len(self._keys)

    def keys(self, *a, **k):  # pragma: no cover - must never run
        raise AssertionError("KEYS used; must SCAN")

    def scan_iter(self, match=None, count=None):
        import fnmatch

        return iter([k for k in self._keys if fnmatch.fnmatchcase(k, match)])


def test_redis_counting_uses_scan_and_counts_each_prefix(mod):
    client = _ScanOnlyRedis(
        [
            "mukthiguru:cache:t:1",
            "mukthiguru:semcache:t:shared:index",
            "mukthiguru:semcache:t:shared:2",
            "cache:first_person_exact:en:abc",
            "mukthiguru:lock:x",
        ]
    )
    out = mod.count_redis(client)
    assert out["dbsize"] == 5
    assert out["patterns"]["mukthiguru:cache:*"] == 1
    assert out["patterns"]["mukthiguru:semcache:*"] == 2
    assert out["patterns"]["cache:first_person_exact:*"] == 1


def test_qdrant_404_is_absent_and_connection_error_is_unreachable(mod):
    def fake_http(url, method="GET", body=None, api_key=None, timeout=10):
        if "/collections/gone/" in url:
            raise mod.HttpStatus(404)
        if "down" in url:
            raise OSError("refused")
        return {"result": {"count": 7}}

    mod._http_json = fake_http
    assert mod.count_qdrant("http://q:6333", ["gone", "here"], None) == {
        "gone": "absent",
        "here": 7,
    }
    with pytest.raises(mod.Unreachable):
        mod.count_qdrant("http://down:6333", ["here"], None)


def test_flush_cache_covers_every_prefix_the_verifier_checks(mod):
    flush = _load(_FLUSH, "flush_cache_prefix_check")
    assert set(mod.REDIS_PATTERNS) <= set(flush._REDIS_QUERY_PATTERNS), (
        "verify-cache-empty checks prefixes that flush-cache never clears; "
        "the verifier would fail forever after a successful flush"
    )


def test_flush_cache_covers_every_qdrant_collection_the_verifier_checks(mod):
    flush = _load(_FLUSH, "flush_cache_collection_check")
    assert set(mod.qdrant_collections(1024)) <= set(flush._cache_collection_names(1024))


def test_makefile_target_exists_and_propagates_status():
    makefile = (_REPO / "Makefile").read_text()
    assert "\nverify-cache-empty:" in makefile
    target = makefile.split("\nverify-cache-empty:", 1)[1].split("\n\n", 1)[0]
    assert "verify_cache_empty.py" in target
    assert "2>/dev/null" not in target
    assert "|| true" not in target
