"""Unit tests for intelligent_metadata_extractor.py."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.intelligent_metadata_extractor import (
    IntelligentMetadata,
    IntelligentMetadataExtractor,
)


@pytest.mark.asyncio
async def test_extract_metadata_success():
    mock_llm = MagicMock()
    mock_response = json.dumps({
        "primary_teacher_id": "krishnaji",
        "attributed_teacher_ids": ["krishnaji", "preethaji"],
        "speakers": ["Sri Krishnaji"],
        "practices": ["Soul Sync"],
        "core_themes": ["truth_of_suffering", "consciousness"],
        "context_header": "Sri Krishnaji speaks on moving beyond suffering into conscious connection.",
        "confidence": 0.98,
        "rationale": "Direct discourse on karma and awakening.",
    })
    mock_llm.generate = AsyncMock(return_value=mock_response)

    extractor = IntelligentMetadataExtractor(llm_service=mock_llm)
    meta = await extractor.extract_metadata(
        chunk_text="Suffering is not your natural state; awakening is.",
        title="Awakening to Oneness",
        speaker="Sri Krishnaji",
        source_url="https://youtube.com/watch?v=123",
    )

    assert meta.primary_teacher_id == "krishnaji"
    assert "krishnaji" in meta.attributed_teacher_ids
    assert "preethaji" in meta.attributed_teacher_ids
    assert "Sri Krishnaji" in meta.speakers
    assert "Soul Sync" in meta.practices
    assert meta.context_header.startswith("Sri Krishnaji speaks")


@pytest.mark.asyncio
async def test_extract_metadata_handles_markdown_codeblocks():
    mock_llm = MagicMock()
    mock_response = """```json
    {
      "primary_teacher_id": "preethaji",
      "attributed_teacher_ids": ["preethaji"],
      "speakers": ["Sri Preethaji"],
      "practices": ["Serene Mind"],
      "core_themes": ["beautiful_state"],
      "context_header": "Sri Preethaji explains the neurobiology of calm.",
      "confidence": 0.95
    }
    ```"""
    mock_llm.generate = AsyncMock(return_value=mock_response)

    extractor = IntelligentMetadataExtractor(llm_service=mock_llm)
    meta = await extractor.extract_metadata(
        chunk_text="Calm is your superpower when leading in times of uncertainty.",
        title="Calm Is Your Superpower",
    )

    assert meta.primary_teacher_id == "preethaji"
    # Even for solo Preethaji, Ekam teachings maintain joint availability for retrieval
    assert "preethaji" in meta.attributed_teacher_ids
    assert "krishnaji" in meta.attributed_teacher_ids


@pytest.mark.asyncio
async def test_extract_metadata_contamination_safety_fallback():
    # Simulate a contaminated response (e.g. CoT reasoning leak)
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="<think>Let me reason about this chunk...</think>")

    extractor = IntelligentMetadataExtractor(llm_service=mock_llm)
    meta = await extractor.extract_metadata(
        chunk_text="Mindfulness and peaceful observation.",
        title="Peace in Relationship",
    )

    # Should safely fall back to deterministic domain heuristics
    assert meta.rationale == "heuristic_fallback"
    assert meta.primary_teacher_id == "ekam"
    assert "preethaji" in meta.attributed_teacher_ids
    assert "krishnaji" in meta.attributed_teacher_ids


@pytest.mark.asyncio
async def test_extract_metadata_llm_failure_fallback():
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(side_effect=RuntimeError("Provider timeout"))

    extractor = IntelligentMetadataExtractor(llm_service=mock_llm)
    meta = await extractor.extract_metadata(
        chunk_text="Teaching by Sri Krishnaji.",
        title="Discourse with Krishnaji",
    )

    assert meta.rationale == "heuristic_fallback"
    assert meta.primary_teacher_id == "krishnaji"
