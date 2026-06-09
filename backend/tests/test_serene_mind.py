from unittest.mock import AsyncMock

import pytest

from services.serene_mind_engine import DistressAssessment, DistressLevel, SereneMindEngine
from services.user_profile_service import ConversationMemory


@pytest.mark.asyncio
async def test_analyze_distress_trend_empty_history():
    engine = SereneMindEngine()
    user_profile_mock = AsyncMock()
    user_profile_mock.get_recent_memories.return_value = []

    current_assessment = DistressAssessment(level=DistressLevel.NONE, confidence=0.0)
    result = await engine.analyze_distress_trend("user123", current_assessment, user_profile_mock)
    assert result is None


@pytest.mark.asyncio
async def test_analyze_distress_trend_insufficient_data():
    engine = SereneMindEngine()
    user_profile_mock = AsyncMock()

    # Only 2 data points (less than 3)
    memory = ConversationMemory(
        session_id="session1",
        user_id="user123",
        started_at=100.0,
        messages=[],
        key_insights=[],
        emotional_arc=[
            {"timestamp": 100.0, "distress_level": 1, "topic": "stress"},
            {"timestamp": 101.0, "distress_level": 2, "topic": "stress"},
        ],
        follow_up_suggestions=[],
    )
    user_profile_mock.get_recent_memories.return_value = [memory]

    current_assessment = DistressAssessment(level=DistressLevel.NONE, confidence=0.0)
    result = await engine.analyze_distress_trend("user123", current_assessment, user_profile_mock)
    assert result is None


@pytest.mark.asyncio
async def test_analyze_distress_trend_consistently_elevated():
    engine = SereneMindEngine()
    user_profile_mock = AsyncMock()

    # 3 data points, average distress = 2.0 (>= 1.5)
    memory = ConversationMemory(
        session_id="session1",
        user_id="user123",
        started_at=100.0,
        messages=[],
        key_insights=[],
        emotional_arc=[
            {"timestamp": 100.0, "distress_level": 2, "topic": "stress"},
            {"timestamp": 101.0, "distress_level": 2, "topic": "stress"},
            {"timestamp": 102.0, "distress_level": 2, "topic": "stress"},
        ],
        follow_up_suggestions=[],
    )
    user_profile_mock.get_recent_memories.return_value = [memory]

    current_assessment = DistressAssessment(
        level=DistressLevel.NONE, confidence=0.0, language_detected="ta"
    )
    result = await engine.analyze_distress_trend("user123", current_assessment, user_profile_mock)
    assert result is not None
    assert result.level == DistressLevel.MODERATE
    assert result.recommended_response_type == "meditation"
    assert result.language_detected == "ta"
    assert "Proactive trigger" in result.detected_signals[0]


@pytest.mark.asyncio
async def test_analyze_distress_trend_escalating():
    engine = SereneMindEngine()
    user_profile_mock = AsyncMock()

    # Escalation: average goes from 1.0 (first half) to 2.5 (second half) -> escalation_rate = 1.5 >= 0.5
    # average distress = 1.8 (>= MILD = 1.0)
    memory = ConversationMemory(
        session_id="session1",
        user_id="user123",
        started_at=100.0,
        messages=[],
        key_insights=[],
        emotional_arc=[
            {"timestamp": 100.0, "distress_level": 1, "topic": "stress"},
            {"timestamp": 101.0, "distress_level": 1, "topic": "stress"},
            {"timestamp": 102.0, "distress_level": 2, "topic": "stress"},
            {"timestamp": 103.0, "distress_level": 3, "topic": "stress"},
        ],
        follow_up_suggestions=[],
    )
    user_profile_mock.get_recent_memories.return_value = [memory]

    current_assessment = DistressAssessment(level=DistressLevel.NONE, confidence=0.0)
    result = await engine.analyze_distress_trend("user123", current_assessment, user_profile_mock)
    assert result is not None
    assert result.level == DistressLevel.MODERATE


@pytest.mark.asyncio
async def test_analyze_distress_trend_high_frequency():
    engine = SereneMindEngine()
    user_profile_mock = AsyncMock()

    # 4 data points (>= MIN_POINTS + 1 = 4)
    # moderate_plus_count = 3 out of 4 (frequency = 0.75 >= 0.6)
    memory = ConversationMemory(
        session_id="session1",
        user_id="user123",
        started_at=100.0,
        messages=[],
        key_insights=[],
        emotional_arc=[
            {"timestamp": 100.0, "distress_level": 2, "topic": "stress"},
            {"timestamp": 101.0, "distress_level": 0, "topic": "stress"},
            {"timestamp": 102.0, "distress_level": 2, "topic": "stress"},
            {"timestamp": 103.0, "distress_level": 3, "topic": "stress"},
        ],
        follow_up_suggestions=[],
    )
    user_profile_mock.get_recent_memories.return_value = [memory]

    current_assessment = DistressAssessment(level=DistressLevel.NONE, confidence=0.0)
    result = await engine.analyze_distress_trend("user123", current_assessment, user_profile_mock)
    assert result is not None
    assert result.level == DistressLevel.MODERATE


@pytest.mark.asyncio
async def test_analyze_distress_trend_recent_severe():
    engine = SereneMindEngine()
    user_profile_mock = AsyncMock()

    # max(levels) = 3 (SEVERE)
    # avg_distress = 1.33 (>= MILD = 1.0)
    memory = ConversationMemory(
        session_id="session1",
        user_id="user123",
        started_at=100.0,
        messages=[],
        key_insights=[],
        emotional_arc=[
            {"timestamp": 100.0, "distress_level": 0, "topic": "stress"},
            {"timestamp": 101.0, "distress_level": 1, "topic": "stress"},
            {"timestamp": 102.0, "distress_level": 3, "topic": "stress"},
        ],
        follow_up_suggestions=[],
    )
    user_profile_mock.get_recent_memories.return_value = [memory]

    current_assessment = DistressAssessment(level=DistressLevel.NONE, confidence=0.0)
    result = await engine.analyze_distress_trend("user123", current_assessment, user_profile_mock)
    assert result is not None
    assert result.level == DistressLevel.MODERATE


@pytest.mark.asyncio
async def test_analyze_distress_trend_disabled_config(monkeypatch):
    engine = SereneMindEngine()
    user_profile_mock = AsyncMock()

    from app.config import settings

    monkeypatch.setattr(settings, "proactive_serene_mind_enabled", False)

    memory = ConversationMemory(
        session_id="session1",
        user_id="user123",
        started_at=100.0,
        messages=[],
        key_insights=[],
        emotional_arc=[
            {"timestamp": 100.0, "distress_level": 2, "topic": "stress"},
            {"timestamp": 101.0, "distress_level": 2, "topic": "stress"},
            {"timestamp": 102.0, "distress_level": 2, "topic": "stress"},
        ],
        follow_up_suggestions=[],
    )
    user_profile_mock.get_recent_memories.return_value = [memory]

    current_assessment = DistressAssessment(level=DistressLevel.NONE, confidence=0.0)
    result = await engine.analyze_distress_trend("user123", current_assessment, user_profile_mock)
    assert result is None
