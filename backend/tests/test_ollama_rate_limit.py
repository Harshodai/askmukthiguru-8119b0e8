"""A 429 (session usage limit) from Ollama Cloud is a quota signal, not an
outage — it must not trip the circuit breaker. See lessons.md #118 for the
identical bug already fixed on the OpenRouter provider; this covers the
Ollama provider fix."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from ollama import ResponseError

from services.ollama_service import OllamaService


def _svc_with_mocked_circuit():
    svc = OllamaService()
    svc._circuit_breaker = MagicMock()
    svc._circuit_breaker.can_execute.return_value = True
    svc._circuit_breaker.config.recovery_timeout = 60
    return svc


@pytest.mark.asyncio
async def test_generate_429_does_not_trip_circuit_breaker():
    svc = _svc_with_mocked_circuit()
    with patch.object(svc, "_llm") as mock_llm:
        mock_llm.bind.return_value = mock_llm
        mock_llm.ainvoke.side_effect = ResponseError("session usage limit", 429)
        with pytest.raises(ResponseError):
            await svc.generate("system", "hello")

    svc._circuit_breaker.record_failure.assert_not_called()


@pytest.mark.asyncio
async def test_generate_real_failure_still_trips_circuit_breaker():
    svc = _svc_with_mocked_circuit()
    with patch.object(svc, "_llm") as mock_llm:
        mock_llm.bind.return_value = mock_llm
        mock_llm.ainvoke.side_effect = ResponseError("internal server error", 500)
        with pytest.raises(ResponseError):
            await svc.generate("system", "hello")

    svc._circuit_breaker.record_failure.assert_called_once()


@pytest.mark.asyncio
async def test_generate_fast_429_does_not_fall_back_to_main_model():
    svc = _svc_with_mocked_circuit()
    with patch.object(svc, "_llm_fast") as mock_fast, patch.object(svc, "generate") as mock_generate:
        mock_fast.bind.return_value = mock_fast
        mock_fast.ainvoke.side_effect = ResponseError("session usage limit", 429)
        with pytest.raises(ResponseError):
            await svc._generate_fast("system", "hello")

    mock_generate.assert_not_called()
    svc._circuit_breaker.record_failure.assert_not_called()
    assert svc._pending_requests == 0
