"""T6-03 (MEM-004): User-stated preferences replace the LLM persona.

Tests that l3_persona_generator strictly synthesizes factual user-stated
preferences and practices, avoiding inferred spiritual stages or profiles.
"""

from services.layered_memory.l3_persona_generator import (
    _SYSTEM_PROMPT,
    compile_user_preferences,
)
from services.layered_memory.models import MemoryAtom


def test_system_prompt_forbids_inferred_spiritual_stages_and_profiles():
    """T6-03 / MEM-004: system prompt must strictly forbid inventing spiritual stages or psychological profiles."""
    assert "NEVER infer, speculate on, or invent spiritual stages" in _SYSTEM_PROMPT
    assert "factual, user-stated preferences" in _SYSTEM_PROMPT


def test_compile_user_preferences_extracts_factual_fields():
    """compile_user_preferences groups memory atoms into stated topics, preferences, and practices."""
    atoms = [
        MemoryAtom(
            content="Meditation on breath",
            type="practice",
            priority=90,
            source_message_ids=["m1"],
            scene_name="morning",
            metadata={},
        ),
        MemoryAtom(
            content="Prefers concise guidance",
            type="preference",
            priority=80,
            source_message_ids=["m2"],
            scene_name="chat",
            metadata={},
        ),
        MemoryAtom(
            content="Interested in navigating anxiety",
            type="topic",
            priority=70,
            source_message_ids=["m3"],
            scene_name="chat",
            metadata={},
        ),
    ]

    prefs = compile_user_preferences(atoms)

    assert "Meditation on breath" in prefs["practices_undertaken"]
    assert "Prefers concise guidance" in prefs["explicit_preferences"]
    assert "Interested in navigating anxiety" in prefs["stated_topics"]


def test_compile_user_preferences_ignores_empty_content():
    """Empty or whitespace-only atoms should not produce empty preference items."""
    atoms = [
        MemoryAtom(
            content="   ",
            type="preference",
            priority=10,
            source_message_ids=["m1"],
            scene_name="chat",
            metadata={},
        ),
        MemoryAtom(
            content="Morning stillness",
            type="practice",
            priority=50,
            source_message_ids=["m2"],
            scene_name="morning",
            metadata={},
        ),
    ]

    prefs = compile_user_preferences(atoms)

    assert len(prefs["explicit_preferences"]) == 0
    assert prefs["practices_undertaken"] == ["Morning stillness"]
