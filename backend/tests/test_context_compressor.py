from unittest.mock import MagicMock

import pytest
from services.context_compressor import ContextCompressor


def test_compressor_disabled_returns_input():
    compressor = ContextCompressor(enabled=False)
    text = "some very long text " * 50
    assert compressor.compress(text) == text


def test_compressor_failed_init_returns_input():
    # Simulate failure by not having llmlingua installed
    compressor = ContextCompressor(enabled=True)
    # _compressor will be None because import will fail in test env
    text = "some very long text " * 50
    result = compressor.compress(text)
    # Should fall back to returning the input
    assert result == text


def test_compress_reduces_length_mocked(monkeypatch):
    mock_compressor = MagicMock()
    mock_compressor.compress_prompt.return_value = {
        "compressed_prompt": "shortened text"
    }

    compressor = ContextCompressor.__new__(ContextCompressor)
    compressor.enabled = True
    compressor._compressor = mock_compressor

    text = "The spiritual teachings of Sri Krishnaji suggest that human suffering arises from division. " * 10
    result = compressor.compress(text, target_ratio=0.5)

    assert len(result) < len(text)
    assert result == "shortened text"
    mock_compressor.compress_prompt.assert_called_once()
    # Verify force_tokens are preserved
    call_kwargs = mock_compressor.compress_prompt.call_args.kwargs
    assert "Sri Krishnaji" in call_kwargs.get("force_tokens", [])