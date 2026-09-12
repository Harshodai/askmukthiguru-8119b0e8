"""Local conftest for canonical_memory tests.

Overrides the root conftest's autouse fixtures that import ``app.main``
(and its heavy dependency chain) so that pure unit tests run without
triggering the full application import graph.
"""
import pytest


@pytest.fixture(autouse=True)
def _restore_event_loop():
    """No-op override — canonical_memory tests don't need event-loop mgmt."""
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """No-op override — canonical_memory tests don't touch rate limiters."""
    yield


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """No-op override — canonical_memory tests don't use app.dependency_overrides."""
    yield
