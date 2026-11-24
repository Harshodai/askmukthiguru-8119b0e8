import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from rag.nodes.generation import verify_verbatim_spans, _polish_and_weave_clips


def test_verify_verbatim_spans_exact_match():
    source_docs = [
        {"text": "When you observe without judgment, the fear naturally dissolves into calm awareness."}
    ]
    original = "The teaching states: 'When you observe without judgment, the fear naturally dissolves into calm awareness.'"
    polished = "As Sri Krishnaji teaches: \"When you observe without judgment, the fear naturally dissolves into calm awareness.\" This shift brings inner peace."

    valid, result = verify_verbatim_spans(polished, source_docs, original)
    assert valid is True
    assert result == polished


def test_verify_verbatim_spans_detects_tampering_and_reverts():
    source_docs = [
        {"text": "When you observe without judgment, the fear naturally dissolves into calm awareness."}
    ]
    original = "The teaching states: 'When you observe without judgment, the fear naturally dissolves into calm awareness.'"
    # Tampered quote (e.g. LLM substituted "anxiety disappears" instead of "fear naturally dissolves")
    tampered_polished = "Sri Krishnaji teaches: \"When you observe without judgment, the anxiety disappears forever.\" This shift brings inner peace."

    valid, result = verify_verbatim_spans(tampered_polished, source_docs, original)
    assert valid is False
    assert result == original


@pytest.mark.asyncio
async def test_polish_and_weave_clips_cleans_trailing_debris():
    source_docs = [
        {"text": "The Four Sacred Secrets is available on Amazon India."}
    ]
    question = "Where can I find the book?"
    # Draft answer with trailing broken fragment
    draft_answer = (
        "You can find and read \"The Four Sacred Secrets\" by Sri Preethaji & Sri Krishnaji on amazon.in at\n\n"
        "_Apart from words in quotation marks, this is a summary of the teachings in our own words, not a direct quote._"
    )

    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(
        return_value="You can find and read \"The Four Sacred Secrets\" by Sri Preethaji & Sri Krishnaji on amazon.in."
    )

    result = await _polish_and_weave_clips(draft_answer, source_docs, question, provider=mock_llm, timeout_s=10.0)

    assert "on amazon.in." in result
    assert "on amazon.in at" not in result
    # Disclaimer re-attached properly
    assert "_Apart from words in quotation marks" in result


@pytest.mark.asyncio
async def test_polish_and_weave_clips_timeout_fallback():
    source_docs = [{"text": "Teaching content."}]
    question = "What is peace?"
    draft_answer = "This is a substantive answer explaining that peace comes from inner observation."

    mock_llm = MagicMock()
    async def _slow_call(*args, **kwargs):
        await asyncio.sleep(0.5)
        return "Polished result"

    mock_llm.generate_fast = _slow_call

    # Very small timeout should trigger fallback safely
    result = await _polish_and_weave_clips(draft_answer, source_docs, question, provider=mock_llm, timeout_s=0.05)
    assert result == draft_answer


@pytest.mark.asyncio
async def test_polish_and_weave_clips_skips_crisis_and_refusals():
    source_docs = [{"text": "Teaching."}]
    question = "Help me"
    crisis_answer = "Please connect directly with verified, confidential crisis support: Tele-MANAS (India): 14416."

    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(return_value="Should not be called")

    result = await _polish_and_weave_clips(crisis_answer, source_docs, question, provider=mock_llm)
    assert result == crisis_answer
    mock_llm.generate_fast.assert_not_called()
