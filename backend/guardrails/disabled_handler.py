from __future__ import annotations

from typing import Any

from guardrails.base import BaseGuardrailHandler


class DisabledGuardrailHandler(BaseGuardrailHandler):
    """Pass-through guardrail handler that performs no checks."""

    async def _handle_input(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return {"blocked": False, "reason": None, "response": None}

    async def _handle_output(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return {"blocked": False, "reason": None, "moderated_response": None}
