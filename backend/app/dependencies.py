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
Mukthi Guru — FastAPI Dependency Injection (BACK-COMPAT SHIM)

Historical composition root. The implementation has been split into
focused modules:

  - app.container         — ServiceContainer (data-holder + builder stages)
  - app.builder           — ContainerBuilder re-export
  - app.health            — ContainerHealthChecker (non-blocking probes)
  - app.lifecycle         — ContainerLifecycle + close_container()

This module re-exports every public symbol so that all existing
`from app.dependencies import X` imports across the codebase keep
working unchanged. Do NOT add new logic here; new code should import
from the focused modules directly.
"""

import threading

from app.container import (
    _NoopTranslationProvider,
    _REQUIRED_SINGLETONS,
    ServiceContainer,
    _create_llm_service,
)
from app.builder import ContainerBuilder

# Re-exported for legacy callers that touched health/cleanup internals.
from app.health import ContainerHealthChecker
from app.lifecycle import ContainerLifecycle, close_container

import logging

logger = logging.getLogger(__name__)


# Module-level singleton with thread-safe initialization
_container: ServiceContainer | None = None
_container_lock = threading.Lock()

# Startup state — set by background_init after heavy services are ready
startup_complete: bool = False
startup_error: str | None = None


def get_container() -> ServiceContainer:
    """
    Get or create the service container singleton.

    Thread-safe: uses a lock to ensure only one ServiceContainer is created
    even if multiple threads call this concurrently.

    Uses ContainerBuilder (Builder Pattern) for step-by-step, layered
    construction of the service container.
    """
    global _container
    if _container is not None:
        return _container
    with _container_lock:
        # Double-checked locking: re-check inside the lock
        if _container is None:
            _container = ContainerBuilder().build()
    return _container


def startup() -> None:
    """Initialize the service container on application startup."""
    get_container()
    logger.info("Service container ready")


def shutdown() -> None:
    """Cleanup on application shutdown - releases service resources."""
    global _container
    with _container_lock:
        if _container is not None:
            _container.close()
            _container = None
    logger.info("Service container shutdown")


__all__ = [
    "ServiceContainer",
    "ContainerBuilder",
    "ContainerHealthChecker",
    "ContainerLifecycle",
    "close_container",
    "_NoopTranslationProvider",
    "_REQUIRED_SINGLETONS",
    "_create_llm_service",
    "get_container",
    "startup",
    "shutdown",
    "startup_complete",
    "startup_error",
]


if __name__ == "__main__":
    # Self-check: shim imports cleanly and exposes the legacy API.
    assert ServiceContainer is not None
    assert callable(get_container)
    print("C2 OK")