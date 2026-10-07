"""Regression test for the 2026-09-24 segfault.

Live crash dump: `Fatal Python error: Segmentation fault`, current thread
inside `onnxruntime`'s `session.run()` via
`EmbeddingService._encode_batch_onnx` <- `LettuceDetectService._score_heuristic`
<- `_score_with_real_detector`, with a SECOND thread concurrently inside
torch's `Linear.forward` under `modeling_modernbert.py` (the shared
LettuceDetect torch module), preceded by
"libgomp: Thread creation failed: Resource temporarily unavailable".

`_shared_predict_lock` already makes the shared torch module exclusive, but
its own `NativeInferenceBusy` fallback branch called
`_score_heuristic(..., use_semantic=True)` by default -- which runs the ONNX
embedding session concurrently with whatever thread currently holds that
lock (that's the only way `NativeInferenceBusy` fires at all). Torch and
ONNX Runtime share the process's native OpenMP thread pool; concurrent
native calls there produced the crash.

This test proves the fix: when the shared-detector lock is busy, the
heuristic fallback must take the lexical-only branch and must never touch
the embedder (no native inference call of any kind).
"""

from __future__ import annotations

import threading

import pytest

from app.config import settings
from services.lettuce_detect_service import LettuceDetectService


class _ExplodingEmbedder:
    """Any call proves the race this test guards against."""

    def encode_batch(self, texts):  # pragma: no cover - must never run
        raise AssertionError(
            "encode_batch() must not be called while the shared torch "
            "detector lock is held by another thread"
        )


@pytest.fixture(autouse=True)
def _enable_real_detector_path(monkeypatch):
    monkeypatch.setattr(settings, "lettucedetect_enabled", True)
    monkeypatch.setattr("services.lettuce_detect_service._predict_lock_timeout", lambda: 0.05)
    yield


def test_shed_under_load_never_calls_embedder():
    """Simulates NativeInferenceBusy: another thread holds the shared lock."""
    service = LettuceDetectService(embedder=_ExplodingEmbedder())
    # A detector object is enough -- predict() must never be reached because
    # the lock is held for the whole call.
    service._load_real_detector = lambda: object()

    LettuceDetectService._shared_predict_lock.acquire()
    try:
        result = service.score_faithfulness("query", "The sky is blue.", "The sky is blue.")
    finally:
        LettuceDetectService._shared_predict_lock.release()

    # Lexical-overlap fallback still gates the answer -- it just never
    # touched the embedder to do it.
    assert isinstance(result, dict)
    assert "is_faithful" in result


def test_concurrent_forward_and_shed_do_not_race():
    """End-to-end: a real forward() holding the lock + a shed-under-load
    call from another thread must never overlap in the embedder."""
    embedder = _ExplodingEmbedder()
    service = LettuceDetectService(embedder=embedder)

    release_forward = threading.Event()
    entered_forward = threading.Event()

    class _SlowDetector:
        def predict(self, **kwargs):
            entered_forward.set()
            release_forward.wait(timeout=2)
            return []

    service._load_real_detector = lambda: _SlowDetector()

    def _hold_lock_and_predict():
        service.score_faithfulness("q", "ctx", "ctx")

    holder = threading.Thread(target=_hold_lock_and_predict)
    holder.start()
    assert entered_forward.wait(timeout=1), "forward() never started"

    # While the holder is mid-forward(), a second caller must shed to the
    # lexical path rather than racing the embedder.
    result = service.score_faithfulness("q2", "The sky is blue.", "The sky is blue.")
    assert isinstance(result, dict)

    release_forward.set()
    holder.join(timeout=2)


def test_predict_failure_fallback_never_calls_embedder():
    """Any other predict() failure must also shed to the lexical-only path."""
    service = LettuceDetectService(embedder=_ExplodingEmbedder())

    class _FailingDetector:
        def predict(self, **kwargs):
            raise RuntimeError("transient native failure")

    service._load_real_detector = lambda: _FailingDetector()
    result = service.score_faithfulness("q", "The sky is blue.", "The sky is blue.")
    assert isinstance(result, dict)
    assert "is_faithful" in result


if __name__ == "__main__":
    test_shed_under_load_never_calls_embedder()
    test_concurrent_forward_and_shed_do_not_race()
    test_predict_failure_fallback_never_calls_embedder()
    print("OK")
