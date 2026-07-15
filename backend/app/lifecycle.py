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
Mukthi Guru — Container lifecycle.

Startup and shutdown orchestration for the ServiceContainer singleton.
The cleanup logic moved verbatim from ServiceContainer.close(); the
container's close() method delegates here.

Design Pattern: Singleton Container + thread-safe initialization.
"""

import logging
import threading

from app.container import ServiceContainer

logger = logging.getLogger(__name__)


def close_container(container: ServiceContainer) -> None:
    """
    Explicitly release resources held by services.

    Calls cleanup methods on services that implement them.
    Errors are logged but do not prevent other services from closing.

    Iteration order is LIFO (reverse of initialization) so that
    dependent services are released before their dependencies.
    """
    # LIFO order: rag_graph → ingestion → guardrails → ocr → ollama → embedding → qdrant
    for name in (
        "rag_graph",
        "ingestion",
        "guardrails",
        "ocr",
        "ollama",
        "embedding",
        "qdrant",
        "user_profile",
        "krutrim",
    ):
        svc = getattr(container, name, None)
        if svc is None:
            continue
        for method_name in ("close", "shutdown", "disconnect"):
            method = getattr(svc, method_name, None)
            if callable(method):
                try:
                    method()
                    logger.debug(f"Closed {name} via {method_name}()")
                except Exception as exc:
                    logger.warning(f"Error closing {name}.{method_name}(): {exc}")
                break  # Only call the first available cleanup method

    if container._neo4j_driver is not None:
        try:
            container._neo4j_driver.close()
            logger.debug("Closed shared neo4j_driver")
        except Exception as exc:
            logger.warning(f"Error closing shared neo4j_driver: {exc}")
        container._neo4j_driver = None

    logger.info("All services closed")


class ContainerLifecycle:
    """
    Startup/shutdown coordinator for the module-level ServiceContainer
    singleton (thread-safe).

    The singleton accessor (get_container) lives in app.dependencies so
    existing imports keep working; this class wraps the startup/shutdown
    verbs for callers that want them as an object.
    """

    _lock = threading.Lock()

    def __init__(self) -> None:
        # Defer import to avoid circulars — dependencies.py imports this module.
        from app.dependencies import _container as _current  # noqa: F401  (probe only)
        # Nothing else to wire; state lives in dependencies.py for back-compat.

    async def startup(self, container: ServiceContainer | None = None) -> ServiceContainer:
        """Initialize (or reuse) the service container singleton."""
        from app.dependencies import get_container

        c = container if container is not None else get_container()
        logger.info("Service container ready")
        return c

    async def shutdown(self, container: ServiceContainer | None = None) -> None:
        """Cleanup on application shutdown — releases service resources."""
        if container is not None:
            close_container(container)
            logger.info("Service container shutdown (explicit instance)")
            return

        from app.dependencies import shutdown as _dep_shutdown

        _dep_shutdown()


if __name__ == "__main__":
    # Self-check: module imports cleanly and helpers are accessible.
    assert callable(close_container)
    assert ContainerLifecycle is not None
    print("C2 OK")