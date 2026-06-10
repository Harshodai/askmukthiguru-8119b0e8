"""Telemetry event types.

Immutable, hashable dataclasses emitted by the pipeline and consumed
by TelemetryPublisher.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class StageStarted:
    """Emitted when a pipeline stage begins."""

    stage_name: str
    trace_id: str
    input_hash: str | None = None
    timestamp_ns: int = 0


@dataclass(frozen=True)
class StageCompleted:
    """Emitted when a pipeline stage finishes."""

    stage_name: str
    trace_id: str
    input_hash: str | None = None
    output_hash: str | None = None
    latency_ms: int = 0
    status: Literal["success", "cached", "error"] = "success"
    error_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageFailed:
    """Emitted when a pipeline stage raises an exception."""

    stage_name: str
    trace_id: str
    error_type: str
    error_message: str = ""
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthStatus:
    """Periodic health / heartbeat event."""

    service: str
    status: Literal["healthy", "degraded", "unhealthy"] = "healthy"
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)