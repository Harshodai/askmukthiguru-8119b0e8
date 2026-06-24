"""TelemetryPublisher — event subscriber pattern

Publishing is fully asynchronous and non-blocking.  Sinks are invoked
concurrently; slow sinks cannot block the pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import time

from anyio import Lock as AsyncLock
from app.telemetry.events import HealthStatus, StageCompleted, StageFailed, StageStarted
from app.telemetry.sinks import ConsoleSink, TelemetrySink

logger = logging.getLogger(__name__)


class TelemetryPublisher:
    """Singleton event publisher that fans out to registered sinks."""

    _instance: "TelemetryPublisher | None" = None
    _lock = AsyncLock()

    def __new__(cls, *args, **kwargs):  # noqa: ARG004
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._sinks: list[TelemetrySink] = []
        self._initialized = True

    def register_sink(self, sink: TelemetrySink) -> None:
        """Add a sink to the broadcast list."""
        self._sinks.append(sink)

    def remove_sink(self, sink: TelemetrySink) -> None:
        """Remove a sink from the broadcast list (idempotent)."""
        try:
            self._sinks.remove(sink)
        except ValueError:
            pass

    async def publish(self, event: StageStarted | StageCompleted | StageFailed | HealthStatus) -> None:
        """Fan-out event to all sinks concurrently."""
        if not self._sinks:
            return
        results = await asyncio.gather(
            *[self._safe_emit(sink, event) for sink in self._sinks],
            return_exceptions=True,
        )
        for exc in results:
            if isinstance(exc, Exception):
                logger.warning(f"Telemetry sink error: {exc}")

    async def _safe_emit(self, sink: TelemetrySink, event: StageStarted | StageCompleted | StageFailed | HealthStatus) -> None:
        """Wrap sink.write in a timeout so a stalled sink cannot block."""
        try:
            await asyncio.wait_for(sink.write(event), timeout=1.0)
        except asyncio.TimeoutError:
            logger.warning(f"Telemetry sink {sink} timed out after 1s")

    # Convenience helpers
    async def stage_start(self, stage: str, trace_id: str, input_hash: str | None = None) -> int:
        """Emit StageStarted and return current monotonic ns."""
        ts = int(time.monotonic() * 1e9)
        await self.publish(StageStarted(stage_name=stage, trace_id=trace_id, input_hash=input_hash, timestamp_ns=ts))
        return ts

    async def stage_complete(self, stage: str, trace_id: str, *, latency_ms: int, status: str = "success", error_type: str | None = None, metadata: dict | None = None) -> None:
        """Emit StageCompleted."""
        await self.publish(
            StageCompleted(
                stage_name=stage,
                trace_id=trace_id,
                latency_ms=latency_ms,
                status=status,  # type: ignore[arg-type]
                error_type=error_type,
                metadata=metadata or {},
            )
        )

    async def stage_fail(self, stage: str, trace_id: str, *, error_type: str, error_message: str = "", latency_ms: int = 0, metadata: dict | None = None) -> None:
        """Emit StageFailed."""
        await self.publish(
            StageFailed(
                stage_name=stage,
                trace_id=trace_id,
                error_type=error_type,
                error_message=error_message,
                latency_ms=latency_ms,
                metadata=metadata or {},
            )
        )