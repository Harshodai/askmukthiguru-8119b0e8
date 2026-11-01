# DORMANT (2026-11-01 wiring audit, plan §12): no call site in the request path; not shipped. Speculative LLM drafting contradicts the verbatim-only serving rule; do not wire.
"""Speculative stream orchestrator integrating sentence buffering, claim verification, and verbatim guard."""

import logging
from typing import List, AsyncGenerator, Dict, Any, Optional

from app.generation.sentence_buffer import SentenceBoundaryBuffer
from app.verification.claim_verifier import PipelinedClaimVerifier
from app.verification.verbatim_guard import FirstPersonVerbatimGuard

logger = logging.getLogger(__name__)


class SpeculativeStreamOrchestrator:
    """Orchestrates dual-stage generation and pipelined verification:
    - Buffers streaming tokens into sentences (`SentenceBoundaryBuffer`).
    - Verifies each sentence against context chunks (`PipelinedClaimVerifier`).
    - Enforces first-person verbatim quotes (`FirstPersonVerbatimGuard`).
    - Streams verified sentences out with zero pause.
    """

    def __init__(
        self,
        verifier: Optional[PipelinedClaimVerifier] = None,
        verbatim_guard: Optional[FirstPersonVerbatimGuard] = None,
    ) -> None:
        self.verifier = verifier or PipelinedClaimVerifier()
        self.verbatim_guard = verbatim_guard or FirstPersonVerbatimGuard()

    async def process_stream(
        self,
        token_stream: AsyncGenerator[str, None],
        context_chunks: List[str],
        is_first_person: bool = False,
        source_spans: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Processes an incoming token stream, buffers sentences, verifies them, and yields verified chunks."""
        buffer = SentenceBoundaryBuffer()

        if is_first_person and not source_spans:
            # Zero text generation on the first-person route (invariant 15): no clip, no answer.
            return

        if is_first_person:
            # For first-person, bypass LLM stream and yield verbatim guarded text directly
            enforced = self.verbatim_guard.enforce_verbatim("", source_spans, is_first_person=True)
            yield {
                "sentence": enforced["enforced_text"],
                "is_faithful": True,
                "hallucination_score": 0.0,
                "is_verbatim": True,
            }
            return

        async for token in token_stream:
            completed_sentences = buffer.add_token(token)
            for sentence in completed_sentences:
                verification = self.verifier.verify_sentence(sentence, context_chunks)
                if verification["is_faithful"]:
                    yield {
                        "sentence": sentence,
                        "is_faithful": True,
                        "hallucination_score": verification["hallucination_score"],
                        "is_verbatim": False,
                    }
                else:
                    # Redact or replace unfaithful sentence
                    logger.warning(f"Redacting unfaithful sentence: '{sentence}' (score: {verification['hallucination_score']})")
                    yield {
                        "sentence": "[Redacted due to verification threshold]",
                        "is_faithful": False,
                        "hallucination_score": verification["hallucination_score"],
                        "is_verbatim": False,
                    }

        # Flush remaining buffer
        remaining = buffer.flush()
        for sentence in remaining:
            verification = self.verifier.verify_sentence(sentence, context_chunks)
            if verification["is_faithful"]:
                yield {
                    "sentence": sentence,
                    "is_faithful": True,
                    "hallucination_score": verification["hallucination_score"],
                    "is_verbatim": False,
                }
            else:
                yield {
                    "sentence": "[Redacted due to verification threshold]",
                    "is_faithful": False,
                    "hallucination_score": verification["hallucination_score"],
                    "is_verbatim": False,
                }
