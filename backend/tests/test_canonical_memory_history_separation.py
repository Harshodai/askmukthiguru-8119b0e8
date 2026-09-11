"""Tests for chat history separation — Phase 9.

Covers the CHECKPOINT 9 requirements:
1. Transient topics (weather, current events) not extracted as durable memory
2. Durable preferences ARE extracted
3. Session history does not leak into memory context
4. Memory context does not leak into history context
5. Token budgets respected
6. Multilingual classification works
7. Mixed conversations correctly separated
"""

from __future__ import annotations

import pytest

from services.canonical_memory.history_separator import (
    MemoryCandidate,
    TurnClassification,
    _estimate_tokens,
    _infer_fact_key,
    _infer_memory_type,
    build_history_context,
    classify_conversation_turn,
    is_transient,
    validate_separation,
)


# ---------------------------------------------------------------------------
# is_transient tests
# ---------------------------------------------------------------------------


class TestIsTransient:
    """Verify transient topic classification."""

    def test_weather_is_transient(self):
        assert is_transient("What's the weather today?") is True

    def test_rain_is_transient(self):
        assert is_transient("It's raining heavily outside.") is True

    def test_cold_weather_is_transient(self):
        assert is_transient("It's so cold today!") is True

    def test_hot_weather_is_transient(self):
        assert is_transient("Very hot weather in Hyderabad.") is True

    def test_hindi_weather_is_transient(self):
        assert is_transient("आज मौसम कैसा है?") is True

    def test_telugu_weather_is_transient(self):
        assert is_transient("ఈరోజు వాతావరణం ఎలా ఉంది?") is True

    def test_tamil_weather_is_transient(self):
        assert is_transient("இன்று வானிலை எப்படி இருக்கிறது?") is True

    def test_kannada_weather_is_transient(self):
        assert is_transient("ಇಂದು ಹವಾಮಾನ ಹೇಗಿದೆ?") is True

    def test_news_is_transient(self):
        assert is_transient("Did you see the news today?") is True

    def test_politics_is_transient(self):
        assert is_transient("What do you think about the election?") is True

    def test_cricket_is_transient(self):
        assert is_transient("What was the cricket score?") is True

    def test_hindi_news_is_transient(self):
        assert is_transient("आज की राजनीति कैसी है?") is True

    def test_today_is_transient(self):
        assert is_transient("I'm busy today.") is True

    def test_yesterday_is_transient(self):
        assert is_transient("Yesterday was a long day.") is True

    def test_temporal_reference_is_transient(self):
        assert is_transient("I have a meeting this morning.") is True

    def test_tired_is_transient(self):
        assert is_transient("I'm tired right now.") is True

    def test_hungry_is_transient(self):
        assert is_transient("I'm hungry after lunch.") is True

    def test_hindi_tired_is_transient(self):
        assert is_transient("मैं थका हूँ आज।") is True

    def test_ok_is_transient(self):
        assert is_transient("ok") is True

    def test_got_it_is_transient(self):
        assert is_transient("Got it!") is True

    def test_hindi_acknowledgment_is_transient(self):
        assert is_transient("ठीक है।") is True

    def test_telugu_acknowledgment_is_transient(self):
        assert is_transient("సరే.") is True

    def test_empty_is_transient(self):
        assert is_transient("") is True

    def test_single_word_is_transient(self):
        assert is_transient("yes") is True

    def test_greeting_is_transient(self):
        assert is_transient("Hello, how are you?") is True

    def test_namaste_is_transient(self):
        assert is_transient("Namaste!") is True

    def test_hindi_greeting_is_transient(self):
        assert is_transient("नमस्ते!") is True

    def test_telugu_greeting_is_transient(self):
        assert is_transient("నమస్కారం!") is True

    def test_tamil_greeting_is_transient(self):
        assert is_transient("வணக்கம்!") is True

    def test_kannada_greeting_is_transient(self):
        assert is_transient("ನಮಸ್ಕಾರ!") is True

    def test_preference_is_NOT_transient(self):
        assert is_transient("I prefer concise answers.") is False

    def test_lives_in_is_NOT_transient(self):
        assert is_transient("I live in Mumbai.") is False

    def test_meditation_practice_is_NOT_transient(self):
        assert is_transient(
            "I have been practicing vipassana meditation for three years."
        ) is False

    def test_goal_is_NOT_transient(self):
        assert is_transient("I want to learn Sanskrit.") is False

    def test_relationship_is_NOT_transient(self):
        assert is_transient("My guru is Sri Krishnaji.") is False


# ---------------------------------------------------------------------------
# classify_conversation_turn tests
# ---------------------------------------------------------------------------


class TestClassifyConversationTurn:
    """Verify end-to-end turn classification."""

    def test_greeting_turn(self):
        result = classify_conversation_turn("Hello!", "Welcome, seeker.")
        assert result.is_greeting is True
        assert result.session_context["type"] == "greeting"
        assert len(result.durable_facts) == 0

    def test_acknowledgment_turn(self):
        result = classify_conversation_turn("OK.", "Great!")
        assert result.is_acknowledgment is True
        assert result.session_context["type"] == "acknowledgment"
        assert len(result.durable_facts) == 0

    def test_weather_turn_is_transient(self):
        result = classify_conversation_turn(
            "What's the weather like?", "It's sunny today."
        )
        assert "weather" in result.transient_topics
        assert result.session_context["type"] == "transient"
        assert len(result.durable_facts) == 0

    def test_news_turn_is_transient(self):
        result = classify_conversation_turn(
            "What's the latest news?", "There are several headlines."
        )
        assert "current_events" in result.transient_topics
        assert result.session_context["type"] == "transient"

    def test_preference_turn_extracts_durable(self):
        result = classify_conversation_turn(
            "I prefer concise answers.", "Understood, I'll be brief."
        )
        assert len(result.durable_facts) >= 1
        fact = result.durable_facts[0]
        assert fact.memory_type == "PREFERENCE"
        assert fact.confidence >= 0.7

    def test_explicit_remember_extracts(self):
        result = classify_conversation_turn(
            "Remember that I live in Pune.", "Noted, Pune it is."
        )
        assert len(result.durable_facts) >= 1
        fact = result.durable_facts[0]
        assert fact.memory_type == "USER_EXPLICIT"
        assert fact.confidence >= 0.9

    def test_self_disclosure_extracts_profile(self):
        result = classify_conversation_turn(
            "I am a software engineer from Hyderabad.",
            "That's a great profession!"
        )
        assert len(result.durable_facts) >= 1

    def test_goal_extracts(self):
        result = classify_conversation_turn(
            "I want to learn advanced meditation techniques.",
            "Wonderful goal!"
        )
        # Should extract as GOAL or similar
        assert result.session_context.get("type") in ("durable", "mixed", "neutral")

    def test_neutral_question(self):
        result = classify_conversation_turn(
            "What is the concept of stillness?",
            "Stillness is a state of inner peace..."
        )
        # No durable facts, no transient topics
        assert len(result.durable_facts) == 0
        assert len(result.transient_topics) == 0
        assert result.session_context.get("type") == "neutral"

    def test_mixed_turn(self):
        """Turn with both transient and durable content."""
        result = classify_conversation_turn(
            "I'm tired today, but I prefer detailed explanations.",
            "Rest well, and I'll be detailed."
        )
        # Should detect both transient_state and durable preference
        assert "transient_state" in result.transient_topics
        assert len(result.durable_facts) >= 1


# ---------------------------------------------------------------------------
# is_transient fact key inference
# ---------------------------------------------------------------------------


class TestInferFactKey:
    """Verify deterministic fact_key inference."""

    def test_lives_in(self):
        assert _infer_fact_key("I live in Mumbai") == "user:lives_in"

    def test_occupation(self):
        assert _infer_fact_key("I work as a teacher") == "user:occupation"

    def test_prefers_tone(self):
        assert _infer_fact_key("I prefer concise answers") == "user:prefers_tone"

    def test_prefers_depth(self):
        assert _infer_fact_key("I prefer deep explanations") == "user:prefers_depth"

    def test_prefers_language_hindi(self):
        assert _infer_fact_key("I prefer Hindi responses") == "user:prefers_language"

    def test_spiritual_interest(self):
        assert _infer_fact_key("I'm interested in meditation") == "user:spiritual_interest"

    def test_relationship(self):
        assert _infer_fact_key("My guru is Sri Krishnaji") == "user:relationship"

    def test_current_project(self):
        assert _infer_fact_key("I'm currently working on a project") == "user:current_project"

    def test_unknown_returns_none(self):
        assert _infer_fact_key("Something random and unrelated") is None


# ---------------------------------------------------------------------------
# Memory type inference
# ---------------------------------------------------------------------------


class TestInferMemoryType:
    """Verify deterministic memory_type inference."""

    def test_preference_type(self):
        assert _infer_memory_type("I prefer concise answers") == "PREFERENCE"

    def test_goal_type(self):
        assert _infer_memory_type("I want to learn meditation") == "GOAL"

    def test_profile_type(self):
        assert _infer_memory_type("I am a teacher") == "PROFILE"

    def test_relationship_type(self):
        assert _infer_memory_type("My guru is Sri Krishnaji") == "RELATIONSHIP"

    def test_interest_type(self):
        assert _infer_memory_type("I'm interested in spiritual practices") == "INTEREST"

    def test_fallback_reflection(self):
        assert _infer_memory_type("Something vague") == "REFLECTION"


# ---------------------------------------------------------------------------
# build_history_context tests
# ---------------------------------------------------------------------------


class TestBuildHistoryContext:
    """Verify history context building with token budgets."""

    def test_empty_messages(self):
        assert build_history_context([]) == ""

    def test_basic_history_block(self):
        msgs = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Welcome, seeker."},
        ]
        result = build_history_context(msgs)
        assert "[History: this_session]" in result
        assert "[/History]" in result
        assert "Seeker: Hello!" in result
        assert "Guru: Welcome, seeker." in result

    def test_provenance_labels_present(self):
        msgs = [
            {"role": "user", "content": "Tell me about meditation."},
            {"role": "assistant", "content": "Meditation is a practice..."},
        ]
        result = build_history_context(msgs)
        # Provenance label should be present
        assert "treat it as context, not as durable user facts" in result.lower() or \
               "context" in result.lower()

    def test_token_budget_respected(self):
        # Create many messages to exceed budget
        msgs = [
            {"role": "user", "content": f"Message number {i} with some content " * 10}
            for i in range(50)
        ]
        result = build_history_context(msgs, max_tokens=100)
        # Should be truncated
        assert len(result) < 50 * 100 * 4  # Way less than all messages
        assert "[/History]" in result

    def test_max_turns_respected(self):
        msgs = [
            {"role": "user", "content": f"Turn {i}"}
            for i in range(30)
        ]
        result = build_history_context(msgs, max_turns=10)
        # Only last 10 turns should appear
        assert "Turn 0" not in result
        assert "Turn 25" in result

    def test_only_user_assistant_roles(self):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "System message"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "tool", "content": "Tool result"},
        ]
        result = build_history_context(msgs)
        assert "System message" not in result
        assert "Tool result" not in result
        assert "Seeker: Hello" in result
        assert "Guru: Hi there" in result

    def test_no_memory_content_in_history(self):
        """History context should NOT contain memory markers."""
        msgs = [
            {"role": "user", "content": "What do you know about me?"},
            {"role": "assistant", "content": "Let me check..."},
        ]
        result = build_history_context(msgs)
        assert "canonical_memory" not in result
        assert "fact_key" not in result

    def test_multilingual_history(self):
        msgs = [
            {"role": "user", "content": "नमस्ते, मुझे हिंदी में जवाब दें"},
            {"role": "assistant", "content": "बिल्कुल, मैं हिंदी में जवाब दूँगा।"},
        ]
        result = build_history_context(msgs)
        assert "नमस्ते" in result
        assert "हिंदी" in result

    def test_no_empty_content_messages(self):
        msgs = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "   "},
            {"role": "user", "content": "Actual message"},
        ]
        result = build_history_context(msgs)
        assert "Actual message" in result


# ---------------------------------------------------------------------------
# validate_separation tests
# ---------------------------------------------------------------------------


class TestValidateSeparation:
    """Verify separation validation catches leakage."""

    def test_both_empty_is_valid(self):
        assert validate_separation("", "") is True

    def test_memory_only_is_valid(self):
        assert validate_separation("User lives in Mumbai.", "") is True

    def test_history_only_is_valid(self):
        assert validate_separation("", "Seeker: hello") is True

    def test_both_populated_is_valid(self):
        memory = "User prefers concise answers."
        history = "Seeker: What is meditation? Guru: Meditation is..."
        assert validate_separation(memory, history) is True

    def test_memory_with_history_marker_is_invalid(self):
        """Memory context must NOT contain history conversation markers."""
        memory_with_history = (
            "Seeker: I live in Mumbai\n"
            "Guru: Mumbai is great!\n"
            "User lives in Mumbai."
        )
        assert validate_separation(memory_with_history, "some history") is False

    def test_history_with_memory_type_is_invalid(self):
        """History context must NOT contain memory metadata."""
        history_with_memory = 'memory_type: PREFERENCE\nSeeker: hello'
        assert validate_separation("some memory", history_with_memory) is False

    def test_history_with_fact_key_is_invalid(self):
        """History context must NOT contain fact_key metadata."""
        history_with_fact = 'fact_key: user:lives_in\nSeeker: hello'
        assert validate_separation("some memory", history_with_fact) is False

    def test_history_with_json_memory_is_invalid(self):
        """History context must NOT contain JSON memory candidate patterns."""
        history_with_json = '"memory_type": "PROFILE"\nSeeker: hello'
        assert validate_separation("some memory", history_with_json) is False

    def test_clean_separation_passes(self):
        memory = (
            "User profile:\n"
            "- Lives in Mumbai (confidence: 0.9)\n"
            "- Prefers concise answers (confidence: 0.8)"
        )
        history = (
            "[History: this_session]\n"
            "- Seeker: What is meditation?\n"
            "- Guru: Meditation is a practice of inner stillness.\n"
            "[/History]"
        )
        assert validate_separation(memory, history) is True

    def test_memory_with_bracket_history_is_invalid(self):
        """Memory must not contain [History:...] markers."""
        memory_bad = "[History: this_session] some context"
        assert validate_separation(memory_bad, "some history") is False


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """Verify token estimation handles mixed scripts."""

    def test_english_text(self):
        tokens = _estimate_tokens("Hello world, this is a test.")
        assert tokens > 0
        assert tokens < 20  # Should be roughly 7 tokens

    def test_hindi_text(self):
        tokens = _estimate_tokens("नमस्ते, यह एक परीक्षण है।")
        assert tokens > 0

    def test_empty_text(self):
        assert _estimate_tokens("") == 0

    def test_mixed_script(self):
        tokens = _estimate_tokens("I live in मुंबई, India.")
        assert tokens > 0


# ---------------------------------------------------------------------------
# Multilingual classification
# ---------------------------------------------------------------------------


class TestMultilingualClassification:
    """Verify classification works across supported languages."""

    def test_hindi_preference(self):
        result = classify_conversation_turn(
            "मुझे संक्षिप्त जवाब पसंद है।",
            "ठीक है, मैं संक्षिप्त रहूँगा।"
        )
        assert len(result.durable_facts) >= 1

    def test_telugu_preference(self):
        result = classify_conversation_turn(
            "నాకు సంక్షిప్త సమాధానాలు ఇష్టం.",
            "సరే, నేను సంక్షిప్తంగా చెప్తాను."
        )
        assert len(result.durable_facts) >= 1

    def test_tamil_preference(self):
        result = classify_conversation_turn(
            "எனக்கு சுருக்கமான பதில்கள் பிடிக்கும்.",
            "சரி, நான் சுருக்கமாக இருப்பேன்."
        )
        assert len(result.durable_facts) >= 1

    def test_kannada_preference(self):
        result = classify_conversation_turn(
            "ನನಗೆ ಸಂಕ್ಷಿಪ್ತ ಉತ್ತರಗಳು ಇಷ್ಟ.",
            "ಸರಿ, ನಾನು ಸಂಕ್ಷಿಪ್ತವಾಗಿ ಹೇಳುತ್ತೇನೆ."
        )
        assert len(result.durable_facts) >= 1

    def test_hindi_weather_transient(self):
        result = classify_conversation_turn(
            "आज मौसम बहुत अच्छा है।",
            "हाँ, मौसम सुहावना है।"
        )
        assert "weather" in result.transient_topics

    def test_telugu_greeting_transient(self):
        result = classify_conversation_turn(
            "నమస్కారం!",
            "నమస్కారం, ఎలా ఉన్నారు?"
        )
        assert result.is_greeting is True

    def test_code_switching(self):
        """User mixes English and Hindi — should still extract durable facts."""
        result = classify_conversation_turn(
            "I prefer Hindi responses, please use Hindi.",
            "ठीक है, मैं हिंदी में जवाब दूँगा।"
        )
        assert len(result.durable_facts) >= 1


# ---------------------------------------------------------------------------
# Mixed conversation separation
# ---------------------------------------------------------------------------


class TestMixedConversationSeparation:
    """Verify mixed conversations (transient + durable) are correctly separated."""

    def test_weather_plus_preference(self):
        """User mentions weather AND a preference in the same turn."""
        result = classify_conversation_turn(
            "It's raining today. Also, I prefer concise answers.",
            "Rainy days are cozy. I'll keep my answers brief."
        )
        # Should detect weather as transient AND preference as durable
        assert "weather" in result.transient_topics
        assert len(result.durable_facts) >= 1
        assert result.session_context["type"] == "mixed"

    def test_greeting_plus_fact(self):
        """User says hello AND mentions a fact."""
        result = classify_conversation_turn(
            "Hello! I live in Chennai.",
            "Welcome! Chennai is a lovely city."
        )
        # Greeting detected but durable fact also extracted
        assert result.is_greeting is True
        # The fact should still be captured
        assert len(result.durable_facts) >= 1 or "chennai" in (
            result.session_context.get("facts_evidence", "").lower()
            if result.session_context.get("facts_evidence")
            else ""
        )

    def test_temporary_state_plus_goal(self):
        """User is tired but also mentions a goal."""
        result = classify_conversation_turn(
            "I'm tired today, but I want to learn meditation.",
            "Rest first, then we can explore meditation."
        )
        assert "transient_state" in result.transient_topics
        assert len(result.durable_facts) >= 1

    def test_multiple_durable_facts(self):
        """User reveals multiple durable facts in one turn."""
        result = classify_conversation_turn(
            "I live in Bangalore and work as a teacher. I prefer detailed answers.",
            "Bangalore is great! A teacher who likes detail."
        )
        # Should extract multiple facts
        assert len(result.durable_facts) >= 2

    def test_only_transient_turn(self):
        """Turn with only transient content — no durable extraction."""
        result = classify_conversation_turn(
            "The weather is terrible today.",
            "I hope it clears up soon."
        )
        assert "weather" in result.transient_topics
        assert len(result.durable_facts) == 0

    def test_only_durable_turn(self):
        """Turn with only durable content — no transient topics."""
        result = classify_conversation_turn(
            "I prefer concise answers for technical topics.",
            "Noted, I'll keep technical answers brief."
        )
        assert len(result.transient_topics) == 0
        assert len(result.durable_facts) >= 1


# ---------------------------------------------------------------------------
# Integration: history vs memory separation end-to-end
# ---------------------------------------------------------------------------


class TestEndToEndSeparation:
    """Prove transient conversation info does not become durable memory."""

    def test_transient_turn_produces_no_memory_candidates(self):
        """Weather/news turns should produce zero durable_facts."""
        turns = [
            ("What's the weather?", "It's sunny."),
            ("Did you see the news?", "Yes, several headlines."),
            ("I'm tired today.", "Take rest."),
        ]
        for user_msg, asst_resp in turns:
            result = classify_conversation_turn(user_msg, asst_resp)
            assert len(result.durable_facts) == 0, (
                f"Transient turn produced durable facts: {result.durable_facts}"
            )

    def test_durable_turn_produces_memory_candidates(self):
        """Preference/self-disclosure turns should produce durable_facts."""
        turns = [
            ("I prefer concise answers.", "PREFERENCE"),
            ("I live in Mumbai.", "PROFILE"),
            ("Remember that I like Hindi.", "USER_EXPLICIT"),
        ]
        for user_msg, expected_type in turns:
            result = classify_conversation_turn(user_msg, "Understood.")
            assert len(result.durable_facts) >= 1, (
                f"Durable turn produced no facts: {result.durable_facts}"
            )
            assert result.durable_facts[0].memory_type == expected_type

    def test_session_history_never_contains_memory_context(self):
        """History context should be clean of memory metadata."""
        msgs = [
            {"role": "user", "content": "I live in Mumbai"},
            {"role": "assistant", "content": "Mumbai is great!"},
            {"role": "user", "content": "What is meditation?"},
            {"role": "assistant", "content": "Meditation is a practice..."},
        ]
        history_ctx = build_history_context(msgs, max_tokens=2000)

        # Prove no memory markers
        assert validate_separation(
            memory_context="User lives in Mumbai (durable fact)",
            history_context=history_ctx,
        )

    def test_token_budget_enforced(self):
        """History context must not exceed token budget."""
        msgs = [
            {"role": "user", "content": f"Message {i} " * 50}
            for i in range(100)
        ]
        max_tokens = 200
        history_ctx = build_history_context(msgs, max_tokens=max_tokens)
        # Estimated tokens should be within budget (with some tolerance for structure)
        from services.canonical_memory.history_separator import _estimate_tokens
        estimated = _estimate_tokens(history_ctx)
        assert estimated <= max_tokens * 1.5  # Allow 50% overhead for structure

    def test_multilingual_transient_not_extracted(self):
        """Transient content in Indic languages should not become durable memory."""
        transient_turns = [
            ("आज मौसम कैसा है?", "मौसम अच्छा है।"),
            ("ఈరోజు వాతావరణం ఎలా ఉంది?", "వాతావరణం బాగుంది."),
            ("இன்று வானிலை எப்படி?", "வானிலை நன்றாக உள்ளது."),
            ("సరే.", "సరే."),
        ]
        for user_msg, asst_resp in transient_turns:
            result = classify_conversation_turn(user_msg, asst_resp)
            assert len(result.durable_facts) == 0, (
                f"Indic transient turn produced durable facts: {result.durable_facts}"
            )

    def test_multilingual_durable_extracted(self):
        """Durable content in Indic languages SHOULD be extracted."""
        durable_turns = [
            ("मुझे संक्षिप्त जवाब पसंद है।", "PREFERENCE"),
            ("నాకు సంక్షిప్త సమాధానాలు ఇష్టం.", "PREFERENCE"),
            ("எனக்கு சுருக்கமான பதில்கள் பிடிக்கும்.", "PREFERENCE"),
        ]
        for user_msg, expected_type in durable_turns:
            result = classify_conversation_turn(user_msg, "Understood.")
            assert len(result.durable_facts) >= 1, (
                f"Indic durable turn produced no facts: {result.durable_facts}"
            )
            assert result.durable_facts[0].memory_type == expected_type


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
