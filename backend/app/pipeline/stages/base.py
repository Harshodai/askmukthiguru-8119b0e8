"""Stage ABC — pure-function pipeline stage contract.

Each stage runs in isolation against a PipelineContext, returning a
PipelineResult to short-circuit the pipeline or None to continue.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pipeline.result import PipelineResult
    from app.pipeline.stages.context import PipelineContext


class Stage(ABC):
    """A single pipeline stage. ``run`` returns ``None`` to continue,
    or a ``PipelineResult`` to short-circuit the remaining stages."""

    name: str = "stage"

    @abstractmethod
    async def run(self, ctx: "PipelineContext") -> "PipelineResult | None":
        """Execute the stage. Return PipelineResult to short-circuit, None to continue."""
        raise NotImplementedError