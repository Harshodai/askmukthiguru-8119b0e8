"""Process-wide bound on concurrent native (ONNX / torch) model inference.

Why this exists (AMK-B-002, AMK-C-001, verified 2026-09-18):

``max_concurrent_chat`` admits N chat requests, and each one independently
runs BGE-M3 embedding, the ONNX INT8 reranker and the LettuceDetect
ModernBERT NLI pass. Those are native allocations outside Python's heap and
outside anything the asyncio-level limiter can see. At N=6 — *below* the
configured ceiling of 8 — the box died two different ways:

* ``[ONNXRuntimeError] : 6 : RUNTIME_EXCEPTION : ... std::bad_alloc`` from the
  reranker, then a ``faulthandler`` multi-thread dump with
  ``modeling_modernbert`` / ``lettucedetect`` / ``_encode_batch_onnx`` frames
  (the process aborted).
* ``Exited (137)`` with ``OOMKilled: false`` — the *host* kernel's global OOM
  killer, not the container cgroup, picked the backend because it was the
  largest process.

Both are the same failure: nothing bounded how many attention buffers could
be live at once. Per-call batching (``OnnxReranker.predict``) bounds the
largest *single* allocation; it does not bound how many of them coexist.

This gate is that bound. It is a ``threading.BoundedSemaphore`` rather than an
``asyncio.Semaphore`` because every call site is synchronous code running in
an ``asyncio.to_thread`` worker, and a threading primitive is not bound to an
event loop (so it survives the TestClient / multi-loop pattern that forces
``chat.py`` to rebuild its own semaphore).

Latency cost is deliberate and is the correct trade: the ranking in this
codebase is misattribution > refusal > latency. Waiting 200ms for an
inference slot is strictly better than killing every in-flight request.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class NativeInferenceBusy(RuntimeError):
    """No inference slot became available within the configured timeout.

    Raised rather than silently degrading: a caller that has a real fallback
    (LettuceDetect's heuristic scorer) catches this deliberately; a caller
    that does not (embedding) must surface it, because returning a wrong-shaped
    or absent vector violates the embedding-dimension contract.
    """


_gate: Optional[threading.BoundedSemaphore] = None
_gate_size: int = 0
_gate_lock = threading.Lock()


def _get_gate() -> tuple[threading.BoundedSemaphore, int]:
    """Build the semaphore once, sized from settings.

    Rebuilt only if the configured size changes (config hot-reload via
    ``config_watcher``), never per call.
    """
    global _gate, _gate_size
    size = max(1, int(settings.native_inference_max_concurrent))
    with _gate_lock:
        if _gate is None or _gate_size != size:
            _gate = threading.BoundedSemaphore(size)
            _gate_size = size
            logger.info("Native inference gate sized to %d concurrent slots", size)
        return _gate, _gate_size


@contextmanager
def native_inference(op: str) -> Iterator[None]:
    """Hold one native-inference slot for the duration of the block.

    :param op: short label for metrics/logs, e.g. ``"embed_onnx"``.
    :raises NativeInferenceBusy: no slot within ``native_inference_wait_timeout``.
    """
    gate, size = _get_gate()
    timeout = float(settings.native_inference_wait_timeout)

    waited_start = time.monotonic()
    acquired = gate.acquire(timeout=timeout)
    waited = time.monotonic() - waited_start

    if not acquired:
        _record_rejected(op)
        raise NativeInferenceBusy(
            f"native inference slot for {op!r} not available within {timeout:.0f}s "
            f"(gate size {size}); shed load rather than risk an OOM kill"
        )

    _record_wait(op, waited)
    if waited > 1.0:
        logger.warning(
            "Native inference gate: %s waited %.2fs for a slot (size=%d) — "
            "concurrency is above what this box can serve without queueing",
            op,
            waited,
            size,
        )
    try:
        yield
    finally:
        gate.release()


def _record_wait(op: str, waited: float) -> None:
    try:
        from app.metrics import NATIVE_INFERENCE_WAIT_SECONDS

        NATIVE_INFERENCE_WAIT_SECONDS.labels(op=op).observe(waited)
    except Exception:  # pragma: no cover - metrics must never break inference
        pass


def _record_rejected(op: str) -> None:
    try:
        from app.metrics import NATIVE_INFERENCE_REJECTED_TOTAL

        NATIVE_INFERENCE_REJECTED_TOTAL.labels(op=op).inc()
    except Exception:  # pragma: no cover
        pass


def gate_state() -> dict:
    """Current gate occupancy, surfaced in /api/health alongside backpressure."""
    gate, size = _get_gate()
    # BoundedSemaphore has no public counter; _value is the remaining slots.
    remaining = getattr(gate, "_value", size)
    return {
        "max_concurrent": size,
        "in_flight": max(0, size - int(remaining)),
        "saturated": int(remaining) <= 0,
    }


if __name__ == "__main__":
    import concurrent.futures

    peak = 0
    live = 0
    lock = threading.Lock()

    def work() -> None:
        global peak, live
        with native_inference("selftest"):
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.05)
            with lock:
                live -= 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda _: work(), range(32)))

    _, size = _get_gate()
    assert peak <= size, f"gate breached: peak={peak} > size={size}"
    assert live == 0, f"slot leaked: {live} still held"
    assert gate_state()["in_flight"] == 0
    print(f"native inference gate self-check ok: size={size}, peak={peak}/32 threads")
