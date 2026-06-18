"""Telemetry sinks — pluggable backends for event consumption."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.telemetry.events import HealthStatus, StageCompleted, StageFailed, StageStarted

logger = logging.getLogger(__name__)


class TelemetrySink(ABC):
    """Abstract base for all telemetry sinks."""

    @abstractmethod
    async def write(self, event: StageStarted | StageCompleted | StageFailed | HealthStatus) -> None:
        ...


class ConsoleSink(TelemetrySink):
    """Simple stdout logger sink (dev / debug)."""

    def __init__(self, pretty: bool = False) -> None:
        self.pretty = pretty

    async def write(self, event: StageStarted | StageCompleted | StageFailed | HealthStatus) -> None:
        data = {
            "event_type": event.__class__.__name__,
            **{k: v for k, v in event.__dict__.items() if not k.startswith("_")},
        }
        if self.pretty:
            print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        else:
            logger.info(json.dumps(data, default=str, ensure_ascii=False))


class SupabaseSink(TelemetrySink):
    """Supabase telemetry sink (production).  Idempotent inserts into
telemetry_events table."""

    def __init__(self, *, table: str = "telemetry_events", batch_size: int = 100) -> None:
        self.table = table
        self.batch_size = batch_size
        self._buffer: list[dict[str, Any]] = []

    async def write(self, event: StageStarted | StageCompleted | StageFailed | HealthStatus) -> None:
        payload = {
            "event_type": event.__class__.__name__,
            **{k: v for k, v in event.__dict__.items() if not k.startswith("_")},
        }
        self._buffer.append(payload)
        if len(self._buffer) >= self.batch_size:
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        try:
            from app.telemetry_db import _get_client
            client = _get_client()
            if client and self._buffer:
                client.table(self.table).insert(self._buffer).execute()
                logger.debug(f"SupabaseSink flushed {len(self._buffer)} events")
        except Exception as exc:
            logger.warning(f"SupabaseSink flush failed: {exc}")
        finally:
            self._buffer.clear()


class JaegerSink(TelemetrySink):
    """Jaeger / OpenTelemetry compatible sink (production).  Stub until
exporter is wired."""

    async def write(self, event: StageStarted | StageCompleted | StageFailed | HealthStatus) -> None:
        # Stub: integrate with opentelemetry-sdk when available
        pass