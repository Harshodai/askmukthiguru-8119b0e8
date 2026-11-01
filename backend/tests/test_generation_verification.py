"""Tests for sentence buffering, claim verifier, verbatim guard, and speculative stream orchestration."""

import pytest
import asyncio
from typing import AsyncGenerator

from app.config import settings
from app.generation.sentence_buffer import SentenceBoundaryBuffer
from app.verification.claim_verifier import PipelinedClaimVerifier
from app.verification.verbatim_guard import FirstPersonVerbatimGuard
from app.generation.speculative_stream import SpeculativeStreamOrchestrator


def test_sentence_boundary_buffer() -> None:
    buffer = SentenceBoundaryBuffer()

    # Test token accumulation and sentence emission
    s1 = buffer.add_token("Hello world. This is ")
    assert s1 == ["Hello world."]

    s2 = buffer.add_token("a test! And another? Hindi sentence। Next line\n")
    assert s2 == ["This is a test!", "And another?", "Hindi sentence।", "Next line"]

    s3 = buffer.add_token("Done.")
    assert s3 == ["Done."]

    s4 = buffer.flush()
    assert s4 == []


def test_claim_verifier_faithfulness() -> None:
    verifier = PipelinedClaimVerifier(threshold=0.65)

    context = ["The master taught about inner peace and meditation in silence."]

    # Faithful sentence
    result_faithful = verifier.verify_sentence(
        "The master spoke about inner peace and meditation.", context
    )
    assert result_faithful["is_faithful"] is True
    assert result_faithful["hallucination_score"] <= 0.65

    # Unfaithful / hallucinated sentence
    result_unfaithful = verifier.verify_sentence(
        "Aliens landed in New York City with quantum lasers.", context
    )
    assert result_unfaithful["is_faithful"] is False
    assert result_unfaithful["hallucination_score"] > 0.65


def test_first_person_verbatim_guard() -> None:
    guard = FirstPersonVerbatimGuard()

    source_spans = ["Silence is the ultimate language of truth.", "Do not seek outside."]
    llm_draft = "Here is what the master said: Silence is the ultimate language of truth. Do not seek outside."

    enforced = guard.enforce_verbatim(llm_draft, source_spans, is_first_person=True)
    assert (
        enforced["enforced_text"]
        == "Silence is the ultimate language of truth. Do not seek outside."
    )
    assert enforced["is_verbatim"] is True
    assert enforced["modifications_made"] is True


@pytest.mark.asyncio
async def test_speculative_stream_orchestrator(monkeypatch) -> None:
    monkeypatch.setattr(settings, "speculative_generation_enabled", True)

    async def mock_token_stream() -> AsyncGenerator[str, None]:
        tokens = [
            "This ",
            "is ",
            "a ",
            "faithful ",
            "sentence. ",
            "Aliens ",
            "landed ",
            "on ",
            "Mars. ",
        ]
        for t in tokens:
            yield t
            await asyncio.sleep(0.01)

    verifier = PipelinedClaimVerifier(threshold=0.65)
    orchestrator = SpeculativeStreamOrchestrator(verifier=verifier)

    context = ["This is a faithful sentence about science and earth."]

    results = []
    async for item in orchestrator.process_stream(
        mock_token_stream(), context, is_first_person=False
    ):
        results.append(item)

    assert len(results) >= 2
    assert results[0]["sentence"] == "This is a faithful sentence."
    assert results[0]["is_faithful"] is True
    assert results[1]["is_faithful"] is False
    assert results[1]["sentence"] == "[Redacted due to verification threshold]"


def test_claim_without_context_is_not_faithful() -> None:
    verdict = PipelinedClaimVerifier().verify_sentence("Peace is found within.", [])
    assert verdict["is_faithful"] is False
    assert verdict["reason"] == "no_context_provided"


def test_speculative_generation_is_off_by_default_and_unreachable_from_the_app() -> None:
    import pathlib
    import re

    from app.config import Settings

    assert Settings.model_fields["speculative_generation_enabled"].default is False
    app_root = pathlib.Path(__file__).resolve().parents[1] / "app"
    importers = [
        str(p.relative_to(app_root))
        for p in app_root.rglob("*.py")
        if re.search(
            r"^\s*(?:from|import)\s+app\.generation\.speculative_stream",
            p.read_text(encoding="utf-8"),
            re.M,
        )
        and "generation" not in p.parts
    ]
    assert importers == []


@pytest.mark.asyncio
async def test_disabled_flag_yields_nothing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "speculative_generation_enabled", False)

    async def tokens() -> AsyncGenerator[str, None]:
        yield "Peace is within. "

    out = [
        x
        async for x in SpeculativeStreamOrchestrator().process_stream(
            tokens(), ["Peace is within."]
        )
    ]
    assert out == []
