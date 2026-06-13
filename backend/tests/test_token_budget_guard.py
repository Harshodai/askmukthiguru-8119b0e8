import pytest
from unittest.mock import AsyncMock, MagicMock
from app.config import Settings
from services.llm.sarvam_provider import SarvamProvider
from services.llm.openrouter_provider import OpenRouterProvider
from services.llm.ollama_provider import OllamaProvider

@pytest.fixture
def mock_settings(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "max_tokens_per_request", 10)
    return settings

@pytest.mark.asyncio
async def test_sarvam_provider_token_budget_exceeded(mock_settings):
    mock_service = MagicMock()
    mock_service.generate = AsyncMock(return_value="mock response")
    
    provider = SarvamProvider(mock_service)
    
    # A short prompt within 10 tokens (approx 7-8 words) should pass
    res = await provider.generate(system_prompt="System", user_prompt="Short prompt")
    assert res == "mock response"
    
    # A long prompt exceeding 10 tokens should raise ValueError
    with pytest.raises(ValueError) as excinfo:
        await provider.generate(
            system_prompt="System",
            user_prompt="This is a very long prompt that contains way too many words and will definitely exceed the token limit set for this test case."
        )
    assert "TokenBudgetExceeded" in str(excinfo.value)

@pytest.mark.asyncio
async def test_openrouter_provider_token_budget_exceeded(mock_settings):
    mock_service = MagicMock()
    mock_service.generate = AsyncMock(return_value="mock response")
    
    provider = OpenRouterProvider(mock_service)
    
    # A short prompt within 10 tokens should pass
    res = await provider.generate(system_prompt="System", user_prompt="Short prompt")
    assert res == "mock response"
    
    # A long prompt exceeding 10 tokens should raise ValueError
    with pytest.raises(ValueError) as excinfo:
        await provider.generate(
            system_prompt="System",
            user_prompt="This is a very long prompt that contains way too many words and will definitely exceed the token limit set for this test case."
        )
    assert "TokenBudgetExceeded" in str(excinfo.value)
