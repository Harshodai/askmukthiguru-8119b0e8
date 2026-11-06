"""T6-03 (MEM-004): User-stated preferences replace the LLM persona.

Tests that l3_persona_generator strictly synthesizes factual user-stated
preferences and practices, avoiding inferred spiritual stages or profiles.
"""

import asyncio

import services.layered_memory.l3_persona_generator as l3
from services.layered_memory.l3_persona_generator import (
    compile_user_preferences,
    generate_persona,
)
from services.layered_memory.models import MemoryAtom


# MEM-004 remainder: the persona is compiled from user-stated atoms with no LLM,
# so the former test of the LLM system prompt wording is replaced by these.
def _atom(content, type_):
    return MemoryAtom(
        content=content,
        type=type_,
        priority=50,
        source_message_ids=["m"],
        scene_name="chat",
        metadata={},
    )


def test_generate_persona_makes_no_llm_call(monkeypatch):
    def _no_client(*_a, **_k):
        raise AssertionError("generate_persona must not build an LLM client")

    monkeypatch.setattr(l3, "_build_client", _no_client, raising=False)
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _no_client)
    persona = asyncio.run(
        generate_persona(
            [_atom("Prefers concise guidance", "preference"), _atom("Soul Sync", "practice")],
            existing_persona="LLM text: user is at an advanced spiritual stage",
        )
    )
    assert "Prefers concise guidance" in persona
    assert "Soul Sync" in persona
    assert "advanced spiritual stage" not in persona


def test_generate_persona_only_restates_atoms():
    atoms = [_atom("Interested in navigating anxiety", "topic"), _atom("x", "preference")]
    persona = asyncio.run(generate_persona(atoms))
    body = [ln[2:] for ln in persona.splitlines() if ln.startswith("- ")]
    assert sorted(body) == sorted(a.content for a in atoms)


def test_generate_persona_without_atoms_keeps_existing():
    assert asyncio.run(generate_persona([], existing_persona="old")) == "old"
    assert asyncio.run(generate_persona([])) == ""


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
