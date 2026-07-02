import pytest
from unittest.mock import AsyncMock, MagicMock
from ingest.quality_gate import DeterministicChecker, DataQualityGate, LLMQualityScorer, StagingQueue


def test_deterministic_checker_good_content():
    checker = DeterministicChecker()
    text = (
        "Sri Preethaji teaches us about the beautiful state of consciousness. "
        "Through Ekam and meditation, one can transcend suffering states and experience "
        "oneness with the universe. Soul sync sadhana is a daily practice for inner peace."
    )
    passed, penalty, reasons = checker.check(text)
    assert passed
    assert penalty == 0
    assert len(reasons) == 0


def test_deterministic_checker_short_text():
    checker = DeterministicChecker()
    text = "Short text."
    passed, penalty, reasons = checker.check(text)
    assert not passed
    assert "too short" in reasons[0].lower()


def test_deterministic_checker_repetition():
    checker = DeterministicChecker()
    text = "thank you thank you thank you thank you thank you thank you thank you thank you thank you thank you " * 5
    passed, penalty, reasons = checker.check(text)
    assert not passed
    assert any("repetitive" in r.lower() for r in reasons)


def test_deterministic_checker_no_spiritual_keywords():
    checker = DeterministicChecker()
    # Coherent text but completely unrelated to spirituality/philosophy
    text = (
        "The computer network uses a dynamic routing algorithm to route packets between "
        "different servers. We configured the load balancer to distribute the HTTP traffic "
        "evenly across all available Docker containers in the cluster."
    )
    passed, penalty, reasons = checker.check(text)
    # It might still pass T1 but with keyword penalty
    assert penalty > 0
    assert any("no spiritual" in r.lower() for r in reasons)


@pytest.mark.asyncio
async def test_llm_quality_scorer():
    llm_service = AsyncMock()
    # Mock LLM response for valid JSON
    llm_service.generate.return_value = """
    {
      "score": 85,
      "verdict": "PASS",
      "is_spiritual": true,
      "coherence": "high",
      "reasons": ["Coherent discourse on beautiful state"]
    }
    """
    scorer = LLMQualityScorer(llm_service)
    score, reasons = await scorer.score("Valid text about meditation", "http://test.url")
    assert score == 85
    assert "Coherent discourse on beautiful state" in reasons


@pytest.mark.asyncio
async def test_data_quality_gate_orchestrator_pass():
    llm_service = AsyncMock()
    llm_service.generate.return_value = """
    {
      "score": 90,
      "verdict": "PASS",
      "is_spiritual": true,
      "coherence": "high",
      "reasons": []
    }
    """
    supabase = MagicMock()
    gate = DataQualityGate(llm_service=llm_service, supabase_client=supabase, quality_threshold=70)
    
    text = (
        "Sri Krishnaji guides seekers on Ekam teachings. We learn about karma, dharma, "
        "and attaining beautiful states of being. The four sacred secrets show the path."
    )
    result = await gate.run(text, source_url="http://youtube.com/watch?v=123")
    assert result.passed
    assert result.score >= 70
    assert result.staging_id is None
    # Ensure staging insert wasn't called
    supabase.table.assert_not_called()


@pytest.mark.asyncio
async def test_data_quality_gate_orchestrator_fail_and_stage():
    llm_service = AsyncMock()
    llm_service.generate.return_value = """
    {
      "score": 30,
      "verdict": "FAIL",
      "is_spiritual": false,
      "coherence": "medium",
      "reasons": ["Unrelated gaming video"]
    }
    """
    
    # Mock supabase insert return
    supabase = MagicMock()
    insert_mock = MagicMock()
    insert_mock.execute.return_value = MagicMock(data=[{"id": "test-uuid-1234"}])
    supabase.table.return_value.insert.return_value = insert_mock
    
    gate = DataQualityGate(llm_service=llm_service, supabase_client=supabase, quality_threshold=70)
    
    text = "Coherent but non-spiritual text about playing video games and streaming on twitch."
    result = await gate.run(text, source_url="http://youtube.com/watch?v=abc")
    
    assert not result.passed
    assert result.score < 70
    assert result.staging_id == "test-uuid-1234"
    
    # Verify supabase insert was called with the rejected data
    supabase.table.assert_called_once_with("staging_quality_queue")
    supabase.table.return_value.insert.assert_called_once()
