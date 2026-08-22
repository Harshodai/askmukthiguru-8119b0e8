"""StageRunner — runs an ordered list of Stages against a PipelineContext.

Replicates the ``_stage`` telemetry emission between stages. Short-circuits
on the first non-None ``PipelineResult``. The terminal stage (ResultAssembly)
always returns a result, so a fully-run pipeline yields a PipelineResult.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


class StageRunner:
    """Run stages in order; short-circuit on first non-None result."""

    @staticmethod
    async def run(
        stages: list[Stage],
        ctx: PipelineContext,
        coordinator: object | None = None,
    ) -> PipelineResult | None:
        """Run each stage. ``coordinator`` (the PipelineCoordinator) is used
        only for per-stage telemetry emission via its ``_stage`` helper.
        If absent, telemetry is skipped (useful for isolated unit tests)."""
        from app.release_manifest import get_release_manifest

        try:
            release_id = get_release_manifest().release_id
        except Exception:
            release_id = "unknown"

        for stage in stages:
            start_ns = time.time_ns()
            stage_name = str(getattr(stage, "name", stage.__class__.__name__))[:64]
            # Snapshot the sticky per-stage fields before running so telemetry
            # reflects only what THIS stage changed. CacheUpdateStage relies on
            # last_stage_status (e.g. "error"/"cached") persisting across stages,
            # so the sticky fields must never be reset here.
            prev_status = getattr(ctx, "last_stage_status", "success") or "success"
            prev_metadata = getattr(ctx, "last_stage_metadata", None)
            try:
                result = await stage.run(ctx)
                duration_ms = max(0.0, round((time.time_ns() - start_ns) / 1_000_000, 2))
                status = str(getattr(ctx, "last_stage_status", "success") or "success")[:32]
                metadata = getattr(ctx, "last_stage_metadata", None)
                logger.info(
                    "PIPELINE_STAGE_TIMING trace_id=%s stage=%s status=%s duration_ms=%.2f",
                    getattr(ctx, "trace_id", "unknown"),
                    stage_name,
                    status,
                    duration_ms,
                )
                if status == prev_status and metadata is prev_metadata:
                    status = "success"
                    metadata = None

                if hasattr(ctx, "stage_telemetry"):
                    ctx.stage_telemetry.append(
                        {
                            "stage": stage_name,
                            "status": status,
                            "duration_ms": duration_ms,
                            "error_code": None,
                            "release_id": release_id,
                            "metadata": metadata,
                        }
                    )

                if coordinator is not None:
                    await coordinator._stage(
                        stage_name,
                        ctx.trace_id,
                        start_ns=start_ns,
                        status=status,
                        metadata=metadata,
                    )
                if result is not None:
                    return result
            except Exception as exc:
                duration_ms = max(0.0, round((time.time_ns() - start_ns) / 1_000_000, 2))
                logger.warning(
                    "PIPELINE_STAGE_TIMING trace_id=%s stage=%s status=error duration_ms=%.2f",
                    getattr(ctx, "trace_id", "unknown"),
                    stage_name,
                    duration_ms,
                )
                err_type_name = type(exc).__name__
                error_code = (
                    "".join(c for c in err_type_name if c.isalnum() or c == "_")[:64] or "Exception"
                )
                # Keep any context metadata as failure context for diagnostics.
                metadata = getattr(ctx, "last_stage_metadata", None)

                if hasattr(ctx, "stage_telemetry"):
                    ctx.stage_telemetry.append(
                        {
                            "stage": stage_name,
                            "status": "error",
                            "duration_ms": duration_ms,
                            "error_code": error_code,
                            "release_id": release_id,
                            "metadata": metadata,
                        }
                    )

                if coordinator is not None:
                    await coordinator._stage(
                        stage_name,
                        ctx.trace_id,
                        start_ns=start_ns,
                        status="error",
                        error_type=error_code,
                        metadata=metadata,
                    )
                raise
        return None
