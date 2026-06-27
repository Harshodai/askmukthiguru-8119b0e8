from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseGuardrailHandler:
    """Base class for all guardrail handlers in the Chain of Responsibility."""

    def __init__(self) -> None:
        self._next_handler: Optional[BaseGuardrailHandler] = None

    def set_next(self, handler: BaseGuardrailHandler) -> BaseGuardrailHandler:
        """Set the next handler in the chain."""
        self._next_handler = handler
        return handler

    async def check_input(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Validate input. If blocked, returns result; else forwards to next handler."""
        result = await self._handle_input(text, **kwargs)
        if result.get("blocked"):
            return result
        if self._next_handler:
            return await self._next_handler.check_input(text, **kwargs)
        return result

    async def check_output(self, text: str | None, **kwargs: Any) -> dict[str, Any]:
        """Validate output. If blocked, returns result; else forwards to next handler."""
        if text is None:
            return {"blocked": False, "reason": None, "moderated_response": None}
        result = await self._handle_output(text, **kwargs)
        if result.get("blocked"):
            return result
        if self._next_handler:
            return await self._next_handler.check_output(text, **kwargs)
        return result

    async def _handle_input(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Override in subclasses to perform specific input checks."""
        return {"blocked": False, "reason": None, "response": None}

    async def _handle_output(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Override in subclasses to perform specific output checks."""
        return {"blocked": False, "reason": None, "moderated_response": None}
