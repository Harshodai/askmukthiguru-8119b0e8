"""P0 (INGESTION_SAFETY Rule 1): PropositionService must gate every LLM-produced
proposition through find_artifact() before it can reach Qdrant.

Before this fix, extract_propositions() applied only length checks (>20/>30
chars), so chain-of-thought leaks ("The user wants me to..."), provider
graceful-degradation canned strings, and ASR loops passed straight into
chunk content. The downstream select_clean() in _embed_and_index can drop a
whole contaminated chunk, but per-proposition gating here preserves the clean
lines instead of losing the chunk. If every line is contaminated, the
original text is returned (never chunk loss).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from services.proposition_service import PropositionService


def _service_with_response(response: str) -> PropositionService:
    llm = AsyncMock()
    llm.generate.return_value = response
    return PropositionService(llm)


def test_contaminated_propositions_dropped_clean_kept():
    response = (
        "- Sri Krishnaji teaches that awareness dissolves suffering completely.\n"
        "- The user wants me to decompose this teaching into smaller parts for analysis.\n"
        "- I am experiencing a temporary connectivity issue with the model service today."
    )
    svc = _service_with_response(response)
    out = asyncio.run(svc.extract_propositions("Teaching about awareness dissolving suffering."))
    assert out == ["Sri Krishnaji teaches that awareness dissolves suffering completely."]


def test_all_contaminated_falls_back_to_original_text():
    response = (
        "- The user wants me to decompose this teaching into smaller parts for analysis.\n"
        "- The user has provided a long transcript that needs proposition splitting now."
    )
    text = "Original chunk about awareness and suffering that must be preserved."
    svc = _service_with_response(response)
    out = asyncio.run(svc.extract_propositions(text))
    assert out == [text]


if __name__ == "__main__":
    test_contaminated_propositions_dropped_clean_kept()
    test_all_contaminated_falls_back_to_original_text()
    print("OK")


def test_proposition_chunking_is_retired_regardless_of_setting(monkeypatch):
    """D3: no setting value re-enables proposition chunking."""
    from app.config import settings

    svc = _service_with_response("- unused")
    for value in (True, "always", "true", "auto"):
        monkeypatch.setattr(settings, "use_proposition_chunking", value, raising=False)
        assert svc.should_apply_propositions("x" * 100000) is False
