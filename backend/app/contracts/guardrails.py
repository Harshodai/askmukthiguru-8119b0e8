"""Guardrails Service Protocol — defines the contract for input/output validation.

Supports multiple providers (NeMo, Lightweight regex, Disabled) via a
unified interface so callers don‘t depend on implementation details.
"""

from __future__ import annotations

from typing import Any, Protocol


class GuardrailsService(Protocol):
    """Unified interface for guardrail providers."""

    # ── Properties --------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """Whether the guardrail service is currently operational."""
        ...

    @property
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'nemo', 'lightweight', 'disabled')."""
        ...

    # ── Core check methods -----------------------------------------------

    async def check_input(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Validate user input before it enters the pipeline.

        Returns:
            {
                "blocked": bool,
                "reason": str | None,
                "response": str | None,      # replacement text if blocked
            }
        """
        ...

    async def check_output(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Validate model output before it is sent to the user.

        Returns:
            {
                "blocked": bool,
                "reason": str | None,
                "moderated_response": str | None,
            }
        """
        ...
