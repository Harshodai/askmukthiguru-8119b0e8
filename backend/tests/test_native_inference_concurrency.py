"""Concurrency safety of the native ML inference paths (AMK-B-002).

The backend was killed twice under a 6-request burst. The audit recorded the
cause as native memory-allocation pressure. It was not: the live crash dump on
2026-09-18 read

    Fatal Python error: Segmentation fault
    Current thread ...:
      File ".../torch/nn/modules/linear.py", line 134 in forward
      File ".../transformers/models/modernbert/modeling_modernbert.py", ...
      File ".../lettucedetect/detectors/transformer.py", line 385 in predict
      File "/app/services/lettuce_detect_service.py", line 388 ...

at 4.1GB of a 6GB limit with ``OOMKilled: false``. One shared torch module
(``LettuceDetectService._shared_detector`` is a ClassVar) was being run from
several request threads at once.

These tests pin the two invariants that follow, without loading torch:

1. a shared torch module is never entered concurrently, and
2. the process-wide memory gate actually bounds concurrency.

``embedding_service.rerank`` already carried the comment "PyTorch CrossEncoder
fallback: not thread-safe, serialize" — the rule was known, two call sites just
missed it. A regression here is a segfault in production, which no unit test
can catch after the fact, so it is checked at the lock, not at the model.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config import settings
from services.native_inference_gate import (
    NativeInferenceBusy,
    gate_state,
    native_inference,
)


class ReentrancyDetector:
    """Records whether it was ever entered by two threads at once."""

    def __init__(self, hold: float = 0.02) -> None:
        self.hold = hold
        self.concurrent_entries = 0
        self.max_observed = 0
        self._live = 0
        self._lock = threading.Lock()

    def __call__(self, *args, **kwargs):
        with self._lock:
            self._live += 1
            self.max_observed = max(self.max_observed, self._live)
            if self._live > 1:
                self.concurrent_entries += 1
        try:
            time.sleep(self.hold)
            return []
        finally:
            with self._lock:
                self._live -= 1


def test_gate_bounds_concurrency_below_thread_count():
    peak = 0
    live = 0
    lock = threading.Lock()

    def work(_):
        nonlocal peak, live
        with native_inference("test_op"):
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.02)
            with lock:
                live -= 1

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(work, range(48)))

    assert peak <= settings.native_inference_max_concurrent
    assert live == 0
    assert gate_state()["in_flight"] == 0


def test_gate_sheds_rather_than_queueing_forever(monkeypatch):
    """An exhausted gate raises instead of blocking indefinitely."""
    monkeypatch.setattr(settings, "native_inference_max_concurrent", 1)
    monkeypatch.setattr(settings, "native_inference_wait_timeout", 0.05)

    held = threading.Event()
    release = threading.Event()

    def hold_slot():
        with native_inference("holder"):
            held.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold_slot, daemon=True)
    holder.start()
    assert held.wait(timeout=5)
    try:
        with pytest.raises(NativeInferenceBusy):
            with native_inference("blocked"):
                pass
    finally:
        release.set()
        holder.join(timeout=5)


def test_shared_torch_detector_is_never_run_concurrently(monkeypatch):
    """The LettuceDetect module is exclusive — this is the segfault guard."""
    from services.lettuce_detect_service import LettuceDetectService

    monkeypatch.setattr(settings, "native_inference_max_concurrent", 8)
    monkeypatch.setattr(settings, "lettucedetect_enabled", True, raising=False)

    probe = ReentrancyDetector()
    detector = type("FakeDetector", (), {"predict": staticmethod(probe)})()

    service = LettuceDetectService()

    def score(_):
        service._score_with_real_detector(
            detector,
            "what is the beautiful state?",
            "The Beautiful State is calm, joy and connection.",
            "It is a state of calm and joy.",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(score, range(24)))

    assert probe.concurrent_entries == 0, (
        f"shared torch module entered concurrently {probe.concurrent_entries}x "
        f"(max {probe.max_observed} threads inside forward) — this is the "
        "segfault that took the backend down under load"
    )


def test_reranker_torch_fallback_is_never_run_concurrently(monkeypatch):
    """The PyTorch CrossEncoder path in reranker_service is exclusive too."""
    from services.reranker_service import RerankerService

    monkeypatch.setattr(settings, "native_inference_max_concurrent", 8)

    probe = ReentrancyDetector()
    service = RerankerService()
    service._fallback_reranker = type("FakeCE", (), {"predict": staticmethod(probe)})()
    # False => PyTorch CrossEncoder, the path that must serialize.
    service._reranker_outputs_probs = False

    docs = [{"text": "a teaching", "score": 0.5}]

    def run(_):
        service._run_cross_encoder("query", docs, 0.0, time.time())

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(run, range(24)))

    assert probe.concurrent_entries == 0, (
        f"torch CrossEncoder entered concurrently {probe.concurrent_entries}x — "
        "same defect class as the LettuceDetect segfault"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
