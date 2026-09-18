"""The LettuceDetect model must be loaded ONCE per process, not per instance.

Measured live 2026-09-17: three requests logged
"Faithfulness scorer exceeded 8.0s deadline; returning unverified verdict"
while every COMPLETED scoring took 1.5-3.3ms. The gap was not inference — it
was the ModernBERT load. `_real_detector` was an instance attribute, so the
startup warm-up in app/main.py loaded the model into a throwaway
LettuceDetectService while the pipeline's own instance still paid the full
load on its first real request.

That deadline fails CLOSED: each timeout returned is_faithful=False, which
rejected a grounded answer and triggered a regeneration — doubling that
request's latency AND its token cost. Ingestion compounds it, building many
instances per run (the same lesson as OpenRouterService's shared rate limiter).
"""

import pytest

from services.lettuce_detect_service import LettuceDetectService


@pytest.fixture(autouse=True)
def _reset_shared_cache():
    """Each test starts from a cold class-level cache."""
    LettuceDetectService._shared_detector = None
    LettuceDetectService._shared_load_attempted = False
    yield
    LettuceDetectService._shared_detector = None
    LettuceDetectService._shared_load_attempted = False


def test_detector_cache_is_class_level_not_per_instance():
    """A second instance must reuse the first instance's loaded model."""
    sentinel = object()
    LettuceDetectService._shared_detector = sentinel
    LettuceDetectService._shared_load_attempted = True

    # A brand-new instance — as app/main.py's warm-up and the pipeline each
    # create — must see the already-loaded detector, not reload it.
    assert LettuceDetectService()._load_real_detector() is sentinel


def test_load_is_attempted_only_once_across_instances(monkeypatch):
    """A failed load must not be retried by every later instance either.

    Retrying a broken import on every chat turn would reintroduce exactly the
    per-request stall this cache exists to remove.
    """
    calls = {"n": 0}
    real_import = __import__

    def counting_import(name, *args, **kwargs):
        if name == "lettucedetect.models.inference":
            calls["n"] += 1
            raise ImportError("simulated missing package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", counting_import)
    monkeypatch.setattr(
        "services.lettuce_detect_service.settings.lettucedetect_enabled", True, raising=False
    )

    first = LettuceDetectService()._load_real_detector()
    second = LettuceDetectService()._load_real_detector()

    assert first is None and second is None
    assert calls["n"] <= 1, "a failed load must be attempted once per process, not per instance"


def test_concurrent_loads_do_not_return_none_to_the_loser(monkeypatch):
    """A thread arriving mid-load must wait and get the real detector, not None.

    Found 2026-09-18: `_shared_load_attempted` was set True BEFORE the load
    completed. A concurrent thread checking it in that window saw "already
    attempted" and returned `_shared_detector`, which was still None --
    silently downgrading that request's faithfulness check to the heuristic
    scorer with no warning, even though the real load succeeded moments later.
    """
    import threading
    import time

    load_started = threading.Event()
    release_load = threading.Event()

    class _FakeDetector:
        pass

    def slow_snapshot_download(*args, **kwargs):
        load_started.set()
        # Give the second thread a real window to hit the race.
        release_load.wait(timeout=2)
        return "/fake/path"

    monkeypatch.setattr(
        "services.lettuce_detect_service.settings.lettucedetect_enabled", True, raising=False
    )
    fake_module = type(
        "FakeInference", (), {"HallucinationDetector": staticmethod(lambda **kw: _FakeDetector())}
    )()
    monkeypatch.setitem(__import__("sys").modules, "lettucedetect.models.inference", fake_module)
    fake_hub = type("FakeHub", (), {"snapshot_download": staticmethod(slow_snapshot_download)})()
    monkeypatch.setitem(__import__("sys").modules, "huggingface_hub", fake_hub)

    results: list = [None, None]

    def _load_in_thread(index: int):
        results[index] = LettuceDetectService()._load_real_detector()

    t1 = threading.Thread(target=_load_in_thread, args=(0,))
    t1.start()
    assert load_started.wait(timeout=2), "first thread never started its load"

    t2 = threading.Thread(target=_load_in_thread, args=(1,))
    t2.start()
    time.sleep(0.05)  # let t2 reach _load_real_detector and block on the lock
    release_load.set()

    t1.join(timeout=2)
    t2.join(timeout=2)

    assert isinstance(results[0], _FakeDetector)
    assert results[1] is results[0], "second thread must get the loaded detector, not None"


def test_warmup_target_and_pipeline_share_one_load():
    """app/main.py warms a throwaway instance; the pipeline must benefit."""
    sentinel = object()
    LettuceDetectService._shared_detector = sentinel
    LettuceDetectService._shared_load_attempted = True

    warmup_instance = LettuceDetectService()
    pipeline_instance = LettuceDetectService(embedder=object())

    assert warmup_instance._load_real_detector() is pipeline_instance._load_real_detector()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
