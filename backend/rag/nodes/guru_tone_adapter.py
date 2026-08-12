"""Deprecated post-generation tone adapter.

The response pipeline now composes voice during grounded generation. This
compatibility class remains for imports and legacy integrations, but it never
rewrites a completed answer: a second creative pass cannot reliably preserve
claim boundaries, citations, or the distinction between a quotation and a
paraphrase.
"""
from __future__ import annotations

from typing import Any


class GuruToneAdapterNode:
    """Return the supplied factual draft unchanged for legacy callers."""

    def __init__(
        self,
        llm_service: Any = None,
        guru_brain_service: Any = None,
        guru_kg_service: Any = None,
        persona_discriminator: Any = None,
    ) -> None:
        self.llm_service = llm_service
        self.guru_brain_service = guru_brain_service
        self.guru_kg_service = guru_kg_service
        self.persona_discriminator = persona_discriminator

    async def transform_tone(
        self,
        state: dict[str, Any] | None = None,
        user_query: str | None = None,
        factual_draft: str | None = None,
        guru_name: str | None = None,
        teacher_id: str | None = None,
    ) -> dict[str, Any]:
        del user_query, guru_name, teacher_id
        output = dict(state or {})
        output["final_answer"] = factual_draft or output.get("final_answer") or output.get("answer") or ""
        return output
