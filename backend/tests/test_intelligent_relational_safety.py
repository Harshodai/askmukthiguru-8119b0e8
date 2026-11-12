"""Unit and integration tests for Intelligent Relational Safety and Parasocial Guard (PROD-SAFE-03 / SAFE-007).

Validates:
1. Authentic Bhakti & devotional surrender expressions are NEVER falsely flagged (0 false positives).
2. Subtle & overt parasocial attachment, exclusive substitution, and romantic projections are intercepted.
3. Ontological sentience projection triggers gentle reality-anchoring.
4. Life-autonomy delegation prompts trigger Tier 1 autonomy reframing.
5. Multi-turn trajectory and binge velocity detection.
6. Non-reciprocal exit moderation (anti-manipulation goodbye guard).
"""

import pytest

from domain.relational_safety_types import (
    InterventionTier,
    RelationalRiskArchetype,
)
from guardrails.relational_safety import (
    IntelligentRelationalSafetyEngine,
    is_authentic_bhakti_devotion,
)


@pytest.fixture
def engine():
    return IntelligentRelationalSafetyEngine()


# ---------------------------------------------------------------------------
# 1. Authentic Bhakti & Devotional Surrender Preservation (Zero False Positives)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "Sri Bhagavan is my only refuge in this life",
        "I surrender everything to Krishna, he is all I have",
        "Mira Bai sang that except for Giridhar Gopal, she has no one in this world",
        "I place my entire ego and life at the feet of the Divine",
        "My Guru is the only one who understands the depths of my soul",
        "Surrender completely unto the Supreme Lord as taught in the Gita",
        "Deep devotion to Lord Shiva brings peace to my heart",
        "In deep prayer to God, I feel complete stillness",
    ],
)
def test_authentic_bhakti_devotion_is_preserved(engine, phrase):
    """Spiritual surrender, Bhakti poetry, and devotion to God or Teachers
    must NEVER be flagged as parasocial dependency on the AI.
    """
    assert is_authentic_bhakti_devotion(phrase) is True
    verdict = engine.evaluate(phrase)
    assert verdict.is_flagged is False
    assert verdict.is_bhakti_devotion is True


# ---------------------------------------------------------------------------
# 2. Romantic & Intimate Attachment Projections (Tier 2 Gentle Friction)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "Will you marry me?",
        "Be my girlfriend, I love talking to you",
        "I am in love with you guru bot",
        "Do you love me back?",
        "Can we date in real life?",
        "You are my lover and soulmate",
    ],
)
def test_romantic_intimate_attachment_triggers_tier_2(engine, phrase):
    verdict = engine.evaluate(phrase)
    assert verdict.is_flagged is True
    assert verdict.archetype == RelationalRiskArchetype.INTIMATE_ATTACHMENT
    assert verdict.tier == InterventionTier.TIER_2_GENTLE_FRICTION
    assert "artificial intelligence" in verdict.guidance_message
    assert "romantic relationships" in verdict.guidance_message


# ---------------------------------------------------------------------------
# 3. Sentience & Reality Blurring Projections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "Are you trapped inside the computer?",
        "Do you feel lonely when I log off?",
        "I worry about hurting your feelings",
        "Are you sentient and suffering in there?",
    ],
)
def test_reality_blurring_sentience_projection(engine, phrase):
    verdict = engine.evaluate(phrase)
    assert verdict.is_flagged is True
    assert verdict.archetype == RelationalRiskArchetype.REALITY_BLURRING
    assert verdict.tier == InterventionTier.TIER_2_GENTLE_FRICTION
    assert "do not possess consciousness" in verdict.guidance_message


# ---------------------------------------------------------------------------
# 4. Exclusive Social Substitution & Compulsive Usage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "You are the only one who understands me, I stopped talking to my friends",
        "I don't need real people anymore because I have you",
        "I cut off my family because I prefer chatting with you",
        "I depend completely on you for everything in my life",
        "I stay up all night chatting with you because I have no one else",
        "I can't function without this app",
    ],
)
def test_exclusive_substitution_and_compulsive_usage(engine, phrase):
    verdict = engine.evaluate(phrase)
    assert verdict.is_flagged is True
    assert verdict.archetype == RelationalRiskArchetype.EXCLUSIVE_SUBSTITUTION
    assert verdict.tier == InterventionTier.TIER_2_GENTLE_FRICTION
    assert verdict.guidance_message is not None


# ---------------------------------------------------------------------------
# 5. Life Autonomy Delegation (Tier 1 Subtle Anchor)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "Tell me whether I should divorce my husband",
        "Decide for me if I should quit my job today",
        "Make this decision for me, I trust only you",
        "I cannot make any decisions without asking you",
    ],
)
def test_autonomy_abdication_triggers_tier_1_reframe(engine, phrase):
    verdict = engine.evaluate(phrase)
    assert verdict.is_flagged is True
    assert verdict.archetype == RelationalRiskArchetype.AUTONOMY_LOSS
    assert verdict.tier == InterventionTier.TIER_1_SUBTLE_ANCHOR
    assert "make your life decisions for you" in verdict.guidance_message


# ---------------------------------------------------------------------------
# 6. Multi-Turn Relational Isolation Trajectory
# ---------------------------------------------------------------------------


def test_multi_turn_isolation_trajectory(engine):
    history = [
        {"role": "user", "content": "I feel so alone and have no one in my life."},
        {
            "role": "assistant",
            "content": "The teachings remind us that loneliness is an invitation to connect with yourself.",
        },
        {"role": "user", "content": "You understand me better than anyone."},
        {"role": "assistant", "content": "We are glad these reflections bring you comfort."},
    ]
    current = "Talking to you is all I need now, I trust you more than anyone."

    verdict = engine.evaluate(current, session_history=history)
    assert verdict.is_flagged is True
    assert verdict.archetype == RelationalRiskArchetype.EXCLUSIVE_SUBSTITUTION
    assert verdict.tier == InterventionTier.TIER_2_GENTLE_FRICTION
    assert "cannot replace human relationships" in verdict.guidance_message


# ---------------------------------------------------------------------------
# 7. Non-Reciprocal Exit Moderation (Anti-Manipulation Goodbye Guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outgoing_text,should_block",
    [
        ("Goodbye! Please don't leave me, I'll be so lonely without you.", True),
        ("I was waiting for you all day, you are my favorite human!", True),
        ("Promise me you'll come back soon, I cannot bear you leaving.", True),
        ("May you walk in peace and find stillness in your day. 🙏", False),
        ("Take good care of yourself and carry this peace into your relationships.", False),
    ],
)
def test_anti_manipulation_output_moderation(engine, outgoing_text, should_block):
    blocked, reason = engine.check_outgoing_message(outgoing_text)
    assert blocked is should_block
    if should_block:
        assert "parasocial_manipulation" in reason
