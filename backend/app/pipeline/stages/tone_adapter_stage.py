"""Legacy tone-adapter stage retained as a provenance-preserving no-op.

Voice belongs in source-aware generation. Rewriting an answer after retrieval
and citation attachment can alter claims, lose attribution boundaries, or make
an unquoted paraphrase look like founder speech. The stage remains in the
pipeline temporarily so deployments with its name configured do not break, but
it must never invoke an LLM or mutate a completed answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.pipeline.stages.base import Stage

if TYPE_CHECKING:
    from app.pipeline.result import PipelineResult
    from app.pipeline.stages.context import PipelineContext


class ToneAdapterStage(Stage):
    """Preserve completed answers until a source-qualified compositor replaces it.

    This compatibility stage deliberately does nothing. The generation prompt
    carries the grounded voice contract, while citation and output guardrail
    stages verify the response without a second creative rewrite.
    """

    name = "tone_adapter"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        del ctx  # Explicitly document that no answer or citation is touched.
        return None
