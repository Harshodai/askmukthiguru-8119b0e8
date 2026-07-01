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
        ctx: "PipelineContext",
        coordinator: object | None = None,
    ) -> PipelineResult | None:
        """Run each stage. ``coordinator`` (the PipelineCoordinator) is used
        only for per-stage telemetry emission via its ``_stage`` helper.
        If absent, telemetry is skipped (useful for isolated unit tests)."""
        for stage in stages:
            start_ns = time.time_ns()
            try:
                result = await stage.run(ctx)
            except Exception:
                if coordinator is not None:
                    import sys
                    err = sys.exc_info()[0]
                    await coordinator._stage(
                        stage.name, ctx.trace_id, start_ns=start_ns, status="error",
                        error_type=type(err).__name__ if err is not None else "Exception",
                    )
                raise
            status = getattr(ctx, "last_stage_status", "success") or "success"
            metadata = getattr(ctx, "last_stage_metadata", None)
            if coordinator is not None:
                await coordinator._stage(
                    stage.name, ctx.trace_id, start_ns=start_ns, status=status, metadata=metadata
                )
            if result is not None:
                return result
        return None