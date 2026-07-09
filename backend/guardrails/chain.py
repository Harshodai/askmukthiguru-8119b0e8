from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from guardrails.base import BaseGuardrailHandler
from guardrails.disabled_handler import DisabledGuardrailHandler
from guardrails.lightweight_handler import LightweightGuardrailHandler
from guardrails.llama_guard_handler import LlamaGuardHandler
from guardrails.nemo_handler import NeMoGuardrailHandler
from guardrails.rejection_handler import RejectionClassifierHandler

logger = logging.getLogger(__name__)


class GuardrailsChain:
    """
    Orchestrator that sets up and runs the Chain of Responsibility for Guardrails.

    Implements the GuardrailsService contract.
    """

    def __init__(self) -> None:
        self._audit_logger = logging.getLogger("guardrails.audit")
        provider = settings.guardrails_provider.lower()
        self._provider_name = provider
        self._head: BaseGuardrailHandler

        if provider == "disabled":
            logger.info("Guardrails DISABLED via config (not recommended for production)")
            self._head = DisabledGuardrailHandler()
        elif provider == "llama_guard":
            lightweight = LightweightGuardrailHandler()
            llama = LlamaGuardHandler()
            rejection = RejectionClassifierHandler()
            nemo = NeMoGuardrailHandler()

            if not llama.is_available and not rejection.is_available:
                self._provider_name = "lightweight"
                logger.info("Neither LlamaGuard nor RejectionClassifier available -> falling back to [Lightweight] only")
                self._head = lightweight
            else:
                current = lightweight
                if llama.is_available:
                    current.set_next(llama)
                    current = llama
                    logger.info("LlamaGuard available — adding to chain")
                if rejection.is_available:
                    current.set_next(rejection)
                    current = rejection
                    logger.info("RejectionClassifier available — adding to chain")
                if nemo.is_available:
                    current.set_next(nemo)
                    logger.info("NeMo also available — chain extended")
                if llama.is_available:
                    self._provider_name = "llama_guard"
                elif rejection.is_available:
                    self._provider_name = "rejection_classifier"
                else:
                    self._provider_name = "lightweight"
                self._head = lightweight
        elif provider == "rejection_classifier":
            lightweight = LightweightGuardrailHandler()
            rejection = RejectionClassifierHandler()
            nemo = NeMoGuardrailHandler()

            if rejection.is_available:
                lightweight.set_next(rejection)
                self._provider_name = "rejection_classifier"
                logger.info("Guardrails Chain: [Lightweight] -> [RejectionClassifier] active")
                if nemo.is_available:
                    rejection.set_next(nemo)
                    logger.info("NeMo also available — chain: [Lightweight] -> [RejectionClassifier] -> [NeMo]")
            else:
                self._provider_name = "lightweight"
                logger.info("RejectionClassifier unavailable -> falling back to [Lightweight] only")

            self._head = lightweight
        elif provider == "nemo":
            lightweight = LightweightGuardrailHandler()
            nemo = NeMoGuardrailHandler()

            if nemo.is_available:
                lightweight.set_next(nemo)
                self._provider_name = "nemo"
                logger.info("Guardrails Chain: [Lightweight] -> [NeMo] configured and active")
            else:
                self._provider_name = "lightweight"
                logger.info(
                    "Guardrails Chain: NeMo unavailable -> falling back to [Lightweight] only"
                )

            self._head = lightweight
        else:  # "lightweight" or other
            self._provider_name = "lightweight"
            self._head = LightweightGuardrailHandler()
            logger.info("Guardrails Chain: [Lightweight] active")

    async def check_input(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Check input against the chain of guardrails."""
        if self._provider_name == "disabled":
            return {"blocked": False, "reason": None, "response": None}

        result = await self._head.check_input(message, **kwargs)
        if result.get("blocked"):
            self._audit_logger.info(
                f"Input blocked: {result.get('reason')} - message: {message[:100]}"
            )
        return result

    async def check_output(self, answer: str | None, **kwargs: Any) -> dict[str, Any]:
        """Check output against the chain of guardrails."""
        if self._provider_name == "disabled" or answer is None:
            return {"blocked": False, "reason": None, "moderated_response": None}

        result = await self._head.check_output(answer, **kwargs)
        if result.get("blocked"):
            self._audit_logger.info(
                f"Output blocked: {result.get('reason')} - answer: {answer[:100]}"
            )
        return result

    @property
    def is_available(self) -> bool:
        """Returns True if any guardrail check is active (not disabled)."""
        return self._provider_name != "disabled"

    @property
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'nemo', 'lightweight', 'disabled')."""
        return self._provider_name
