"""
Mukthi Guru — Dependency Health Matrix with φ-Accural Failure Detection

Tracks health of external dependencies (Qdrant, Redis, Supabase, OpenRouter, Sarvam)
using a φ-Accural failure detector. This is more accurate than fixed-timeout
heartbeats because it accounts for variance in arrival times.

φ-Accural Algorithm:
  - Sample heartbeat arrival times over a sliding window
  - Compute mean μ and standard deviation σ of inter-arrival times
  - φ = -log₁₀(P_later(real failure)) where P_later is the probability
    that a heartbeat arrives later than the current gap
  - φ > 3 (threshold) → 0.1% false positive probability → mark unhealthy

Circuit States:
  - CLOSED (φ < 1): Healthy, all traffic flows
  - HALF_OPEN (1 ≤ φ < 3): Degraded, probe traffic only
  - OPEN (φ ≥ 3): Unhealthy, traffic blocked with backoff

Usage:
    monitor = HealthMonitor.get_instance()
    monitor.record_heartbeat("qdrant", success=True)
    if monitor.is_healthy("qdrant"):
        # proceed with operation
    else:
        # use fallback
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Optional

from app.config import settings
from app.metrics import DEPENDENCY_HEALTH, DEPENDENCY_PHI

logger = logging.getLogger(__name__)

_PHI_THRESHOLD = 3.0
_HB_WINDOW_SIZE = 20
_HB_INTERVAL_SAMPLE = 5.0


class AccrualFailureDetector:
    """φ-Accural failure detector for a single dependency.

    Maintains a sliding window of heartbeat inter-arrival times and
    computes φ = -log₁₀(P(real failure)) on each check.
    """

    def __init__(self, name: str, threshold: float = _PHI_THRESHOLD) -> None:
        self.name = name
        self.threshold = threshold
        self._lock = threading.Lock()
        self._arrivals: list[float] = []
        self._intervals: list[float] = []
        self._last_heartbeat: Optional[float] = None
        self._phi: float = 0.0
        self._healthy: bool = True
        self._consecutive_failures: int = 0

    def record_heartbeat(self, arrived_at: float, success: bool) -> None:
        with self._lock:
            if not success:
                self._consecutive_failures += 1
                if self._last_heartbeat is not None:
                    gap = arrived_at - self._last_heartbeat
                    self._intervals.append(gap)
                    if len(self._intervals) > _HB_WINDOW_SIZE:
                        self._intervals.pop(0)
                self._last_heartbeat = arrived_at
                self._arrivals.append(arrived_at)
                if len(self._arrivals) > _HB_WINDOW_SIZE:
                    self._arrivals.pop(0)
                self._recompute()
                return

            self._consecutive_failures = 0
            if self._last_heartbeat is not None:
                gap = arrived_at - self._last_heartbeat
                self._intervals.append(gap)
                if len(self._intervals) > _HB_WINDOW_SIZE:
                    self._intervals.pop(0)

            self._last_heartbeat = arrived_at
            self._arrivals.append(arrived_at)
            if len(self._arrivals) > _HB_WINDOW_SIZE:
                self._arrivals.pop(0)

            self._recompute()

    def _recompute(self) -> None:
        if len(self._intervals) < 2:
            self._phi = 0.0
            self._healthy = True
            self._update_metrics()
            return

        mean = sum(self._intervals) / len(self._intervals)
        variance = sum((x - mean) ** 2 for x in self._intervals) / len(self._intervals)
        stddev = max(math.sqrt(variance), 0.001)

        gap = time.time() - (self._last_heartbeat or time.time())
        if gap <= mean:
            self._phi = 0.0
        else:
            deviation = (gap - mean) / stddev
            prob = self._normal_cdf(-deviation)
            prob = max(prob, 1e-10)
            self._phi = -math.log10(prob)

        self._healthy = self._phi < self.threshold
        self._update_metrics()

    def _normal_cdf(self, x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _update_metrics(self) -> None:
        try:
            DEPENDENCY_PHI.labels(name=self.name).set(self._phi)
            DEPENDENCY_HEALTH.labels(name=self.name).set(1.0 if self._healthy else 0.0)
        except Exception:
            pass

    @property
    def is_healthy(self) -> bool:
        if self._consecutive_failures >= 3:
            return False
        return self._healthy

    @property
    def phi(self) -> float:
        return self._phi

    @property
    def state(self) -> str:
        if self._phi >= self.threshold:
            return "OPEN"
        if self._phi >= 1.0:
            return "HALF_OPEN"
        return "CLOSED"

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures


class HealthMonitor:
    """Singleton health matrix tracking all external dependencies."""

    _instance: Optional["HealthMonitor"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "HealthMonitor":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._detectors: dict[str, AccrualFailureDetector] = {}
        self._init_detectors()

    def _init_detectors(self) -> None:
        for name in ("qdrant", "redis", "supabase", "openrouter", "sarvam"):
            self._detectors[name] = AccrualFailureDetector(name=name)

    def record_heartbeat(self, name: str, success: bool) -> None:
        detector = self._detectors.get(name)
        if detector is None:
            return
        detector.record_heartbeat(time.time(), success)

    def is_healthy(self, name: str) -> bool:
        detector = self._detectors.get(name)
        if detector is None:
            return True
        return detector.is_healthy

    def get_phi(self, name: str) -> float:
        detector = self._detectors.get(name)
        if detector is None:
            return 0.0
        return detector.phi

    def get_state(self, name: str) -> str:
        detector = self._detectors.get(name)
        if detector is None:
            return "CLOSED"
        return detector.state

    def get_consecutive_failures(self, name: str) -> int:
        detector = self._detectors.get(name)
        if detector is None:
            return 0
        return detector.consecutive_failures

    @property
    def health_summary(self) -> dict:
        return {
            name: {
                "healthy": det.is_healthy,
                "phi": round(det.phi, 3),
                "state": det.state,
                "consecutive_failures": det.consecutive_failures,
            }
            for name, det in self._detectors.items()
        }
