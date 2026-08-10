"""P1-BE-4 — PipelineCoordinator circuit check via the public provider probe.

Regression: ``_is_circuit_open`` reached into ``container.ollama._service._circuit``
(private-state traversal) — a provider refactor renamed the attribute silently
and the guard stopped firing. Now the coordinator calls the public
``LLMProvider.is_circuit_open()`` probe, which defaults to False on providers
without a breaker.

Covers the coordinator's contract with stub providers (no real services):
  * stub with is_circuit_open() -> True  -> circuit treated as OPEN
  * stub with is_circuit_open() -> False -> circuit CLOSED, normal path
  * legacy-shaped stub WITHOUT the method -> treated as not open (fail-open)
"""

from unittest.mock import MagicMock

import pytest

from app.pipeline.pipeline_coordinator import PipelineCoordinator


class _StubProvider:
    """Minimal LLMProvider-shaped stub with a scriptable circuit probe."""

    def __init__(self, is_open: bool):
        self._is_open = is_open

    def is_circuit_open(self) -> bool:
        return self._is_open


class _LegacyProvider:
    """Old-shaped stub that never grew the public probe (no is_circuit_open)."""


def _coordinator_with(provider) -> PipelineCoordinator:
    container = MagicMock()
    container.ollama = provider
    coord = PipelineCoordinator(container)
    # Coordinator constructor reads container.coalescer — stub it directly.
    coord.coalescer = MagicMock()
    return coord


def test_open_circuit_detected_via_public_probe():
    """Provider reports is_circuit_open() == True -> coordinator says OPEN."""
    coord = _coordinator_with(_StubProvider(is_open=True))
    assert coord._is_circuit_open() is True


def test_closed_circuit_detected_via_public_probe():
    """Provider reports is_circuit_open() == False -> coordinator says CLOSED."""
    coord = _coordinator_with(_StubProvider(is_open=False))
    assert coord._is_circuit_open() is False


def test_legacy_provider_without_probe_treated_as_not_open():
    """A provider shape without is_circuit_open() must degrade to CLOSED
    (fail-open) — never raise, never break the pipeline."""
    coord = _coordinator_with(_LegacyProvider())
    assert coord._is_circuit_open() is False


def test_probe_exception_degrades_to_not_open():
    """A throwing probe must not take the pipeline down — degrade to CLOSED."""

    class _BrokenProvider:
        def is_circuit_open(self):
            raise RuntimeError("breaker state unavailable")

    coord = _coordinator_with(_BrokenProvider())
    assert coord._is_circuit_open() is False


def test_circuit_open_result_is_error_result():
    """The short-circuit result for an open circuit is a blocked ERROR result
    with the circuit-breaker reason."""
    coord = _coordinator_with(_StubProvider(is_open=True))
    result = coord._circuit_open_result(is_benchmark=False, start_time=0.0)
    assert result.blocked is True
    assert result.intent == "ERROR"
    assert result.block_reason == "circuit_breaker_open"


if __name__ == "__main__":
    # ponytail: one runnable self-check — run pytest on this module.
    raise SystemExit(pytest.main([__file__, "-v"]))
