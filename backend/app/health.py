from __future__ import annotations

import os as _os
import sys as _sys
_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _SCRIPT_DIR in _sys.path:
    _sys.path.remove(_SCRIPT_DIR)
_BACKEND = _os.path.dirname(_SCRIPT_DIR)
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

"""
Mukthi Guru — Container health checker.

Non-blocking health probe for the services held by ServiceContainer.
Moved verbatim from ServiceContainer.health_status() so the container
class stays a thin data-holder; the container delegates to this class.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class ContainerHealthChecker:
    """Stateless health-check helper for a ServiceContainer."""

    async def check(self, container) -> dict:
        """
        Check health of all container services (non-blocking).

        Runs blocking checks (Qdrant, OCR) in the event loop's thread
        pool and awaits async checks directly. Returns a flat dict of
        service-name → health signal, preserving the legacy schema.
        """
        loop = asyncio.get_running_loop()

        # Run blocking checks independently so one failure does not mask another.
        try:
            qdrant_ok = await loop.run_in_executor(None, container.qdrant.health_check)
        except Exception:
            qdrant_ok = False
        try:
            qdrant_count = await loop.run_in_executor(None, container.qdrant.count)
        except Exception:
            qdrant_count = 0
        try:
            ocr_ok = await loop.run_in_executor(None, container.ocr.health_check)
        except Exception:
            ocr_ok = False

        try:
            ollama_ok = await container.ollama.health_check()
        except Exception:
            ollama_ok = False

        return {
            "qdrant": qdrant_ok,
            "ollama": ollama_ok,
            "guardrails": container.guardrails.is_available,
            "guardrails_provider": container.guardrails.provider_name,
            "semantic_cache": container.semantic_cache.is_available if container.semantic_cache else False,
            "lightrag_degraded": container.lightrag_degraded,
            "embedding": True,
            "qdrant_count": qdrant_count,
            "ocr": ocr_ok,
        }


if __name__ == "__main__":
    # Self-check: module imports cleanly and the class is accessible.
    checker = ContainerHealthChecker()
    assert hasattr(checker, "check")
    print("C2 OK")