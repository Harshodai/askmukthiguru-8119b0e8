"""Junk class rejected at the ingest door: LLM-refusal artifacts and
third-party channel content (e.g. news coverage) documented in
backend/CLAUDE.md as having leaked into the corpus.

Regression coverage for the DeterministicChecker.check()/DataQualityGate.run()
extension in ingest/quality_gate.py and the shared classifiers in
services/provenance.py.
"""

import pytest

from ingest.quality_gate import DataQualityGate, DeterministicChecker
from services.provenance import (
    ChunkProvenance,
    classify_chunk_provenance,
    is_junk_text,
    is_third_party_channel,
)

LLM_REFUSAL_ARTIFACT = (
    "Therefore, it cannot be situated within the document's context.] "
    "The Magnificent black bird will do this for the entire summer. " * 3
)

GOOD_TEACHING = (
    "When you sit in stillness and observe the breath, you begin to see how "
    "thoughts arise and pass without needing to be followed. This is the "
    "beginning of freedom from the suffering state, moving toward the "
    "beautiful state through simple, sustained awareness of the present moment." * 2
)


def test_deterministic_checker_rejects_junk_artifact():
    checker = DeterministicChecker()
    passed, penalty, reasons = checker.check(
        LLM_REFUSAL_ARTIFACT, source_url="https://youtube.com/x"
    )
    assert passed is False
    assert penalty == 100
    assert any("junk" in r.lower() or "artifact" in r.lower() for r in reasons)


def test_deterministic_checker_rejects_third_party_channel():
    checker = DeterministicChecker()
    passed, penalty, reasons = checker.check(
        GOOD_TEACHING, source_url="https://youtube.com/x", speaker="Times Now"
    )
    assert passed is False
    assert penalty == 100
    assert any("third-party" in r.lower() for r in reasons)


def test_deterministic_checker_passes_good_teaching_from_known_channel():
    checker = DeterministicChecker()
    passed, _penalty, _reasons = checker.check(
        GOOD_TEACHING, source_url="https://youtube.com/x", speaker="Ekam / O&O Academy"
    )
    assert passed is True


@pytest.mark.asyncio
async def test_data_quality_gate_rejects_junk_and_third_party():
    gate = DataQualityGate(enabled=True)  # no LLM scorer -> Tier 1 only

    junk_result = await gate.run(LLM_REFUSAL_ARTIFACT, "https://youtube.com/x")
    assert junk_result.passed is False

    news_result = await gate.run(GOOD_TEACHING, "https://youtube.com/x", speaker="Times Now")
    assert news_result.passed is False

    ok_result = await gate.run(
        GOOD_TEACHING, "https://youtube.com/x", speaker="Sri Preethaji & Sri Krishnaji"
    )
    assert ok_result.passed is True


def test_provenance_classifier_agrees_with_gate():
    """The gate's rejection reasons and the retrieval-time classifier must
    agree on what counts as junk/third-party — same shared source in
    services/provenance.py, checked here so they can't silently drift."""
    assert is_junk_text(LLM_REFUSAL_ARTIFACT) is True
    assert is_third_party_channel(speaker="Times Now") is True

    result = classify_chunk_provenance(raptor_level=0, speaker="Times Now", text=GOOD_TEACHING)
    assert result.provenance == ChunkProvenance.THIRD_PARTY_PROSE

    result = classify_chunk_provenance(raptor_level=0, text=LLM_REFUSAL_ARTIFACT)
    assert result.provenance == ChunkProvenance.JUNK
