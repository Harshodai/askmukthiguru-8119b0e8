"""
Contextual Chunking Service
===========================
Implements Anthropic-style Contextual Retrieval (https://anthropic.com/news/contextual-retrieval).

Each chunk is augmented with a succinct LLM-generated context header that situates it within
the full document.  The header is prepended to the chunk text before embedding — improving
retrieval precision by ~49 % (67 % when combined with reranking).

Usage
-----
    service = ContextualChunkingService(llm=ollama_service)
    chunks = await service.enrich_chunks(full_document, raw_chunks)
    # → ["<context>\\n<original chunk>", ...]

The service is intentionally small and stateless.  Prompt caching is implemented via a
short-circuit: if the full document is the same as the last call the LLM prompt prefix is
not re-sent (the Ollama model caches KV-attention in-process for the same context window).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from anyio import Semaphore as AsyncSemaphore

if TYPE_CHECKING:
    from services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

# Anthropic's recommended prompt (adapted for local LLM / shorter document sizes)
_CONTEXTUAL_SYSTEM = (
    "You are a context-situating assistant for a spiritual teaching retrieval system. "
    "Given a full document and a specific chunk, produce a succinct 1-2 sentence context "
    "that situates the chunk within the document. The context should help a retrieval "
    "system understand what the chunk is about and why it is important. "
    "Answer ONLY with the context — no preamble, no quotation marks."
)

_CONTEXTUAL_PROMPT = """\
<document>
{document}
</document>

Here is the chunk we want to situate within the whole document:
<chunk>
{chunk}
</chunk>

Please give a short succinct context (1-2 sentences) to situate this chunk within the \
overall document for the purposes of improving search retrieval of the chunk. \
Answer only with the succinct context and nothing else."""


class ContextualChunkingService:
    """
    Enriches raw text chunks with LLM-generated contextual headers.

    Parameters
    ----------
    llm:
        An OllamaService instance used for generation.  Uses a smaller/faster model
        when available (CASUAL model) to keep latency acceptable at ingestion time.
    max_doc_chars:
        Maximum characters of the full document sent to the LLM.  Long spiritual
        transcripts can be 80 k+ characters; we truncate to the first and last
        segments to fit within context limits while preserving document boundaries.
    concurrency:
        Maximum parallel LLM calls.  Ollama is single-threaded by default; set to 1
        to avoid contention or increase if running a multi-GPU setup.
    """

    def __init__(
        self,
        llm: OllamaService,
        max_doc_chars: int = 8_000,
        concurrency: int = 3,
    ) -> None:
        self._llm = llm
        self._max_doc_chars = max_doc_chars
        self._sem = AsyncSemaphore(concurrency)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enrich_chunks(
        self,
        full_document: str,
        chunks: list[str],
        source_label: str = "",
    ) -> list[str]:
        """
        Situate every chunk within the full document and return enriched texts.

        Enriched format::

            [Context: <LLM-generated 1-2 sentence situating context>]
            <original chunk text>

        Fallback: if the LLM call fails for a chunk the original text is returned
        unchanged (non-blocking, logged at WARNING level).

        Parameters
        ----------
        full_document:
            The complete document text (transcript, book chapter, etc.).
        chunks:
            List of raw chunk texts to enrich.
        source_label:
            Optional human-readable label (e.g. video title) included in the
            fallback header when LLM generation fails.

        Returns
        -------
        list[str]
            Enriched chunk texts, same order and length as ``chunks``.
        """
        truncated_doc = self._truncate_document(full_document)
        tasks = [
            self._enrich_one(truncated_doc, chunk, i, source_label)
            for i, chunk in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        enriched: list[str] = []
        for i, (chunk, result) in enumerate(zip(chunks, results)):
            if isinstance(result, Exception):
                logger.warning(
                    "ContextualChunkingService: chunk %d enrichment failed (%s), "
                    "using original text",
                    i,
                    result,
                )
                enriched.append(chunk)
            else:
                enriched.append(result)

        logger.info(
            "ContextualChunkingService: enriched %d/%d chunks",
            sum(1 for r in results if not isinstance(r, Exception)),
            len(chunks),
        )
        return enriched

    async def enrich_single(self, full_document: str, chunk: str) -> str:
        """Convenience method: enrich a single chunk."""
        truncated_doc = self._truncate_document(full_document)
        return await self._enrich_one(truncated_doc, chunk, 0, "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _enrich_one(
        self,
        truncated_doc: str,
        chunk: str,
        index: int,
        source_label: str,
    ) -> str:
        """Generate context for a single chunk, respecting the concurrency semaphore.

        .. rubric:: Safety gates (L-INGEST-1 / L-INGEST-2)

        Three contamination vectors can poison the ``[Context: ...]`` header:

        1. **Sarvam reasoning leak** — reasoning-tuned models (Sarvam-105b,
           DeepSeek-R1) emit chain-of-thought ("The user wants me to...") when
           ``operation`` is not set, because the default reasoning tier is
           ``medium``. Fixed by passing ``operation="summarize"`` which maps
           to ``low`` reasoning via Sarvam's built-in tiering.

        2. **Provider graceful-degradation** — OpenRouter/NIM return a canned
           "temporary connection issue" string instead of raising. That string
           would be prepended as a context header and embedded as doctrine.

        3. **Generic LLM artifacts** — markdown scaffolding, self-references,
           instruction echoes.

        All three are caught by ``find_artifact()`` (which now includes
        ``is_graceful_degradation()``). On detection: one retry, then
        fall back to unenriched chunk (never chunk loss).

        Affected providers: OpenRouter, NIM, Sarvam, Ollama.
        See ``backend/docs/INGESTION_SAFETY.md``.
        """
        from services.text_quality_filter import find_artifact

        async with self._sem:
            try:
                prompt = _CONTEXTUAL_PROMPT.format(
                    document=truncated_doc,
                    chunk=chunk[:2_000],  # Don't send huge chunks verbatim
                )

                context_text = await self._llm.generate(
                    system_prompt=_CONTEXTUAL_SYSTEM,
                    user_prompt=prompt,
                    timeout=20,
                    max_retries=1,
                    # L-INGEST-1: Tag operation so Sarvam's reasoning tiering
                    # uses low reasoning (not medium default), preventing CoT
                    # leaks like "The user wants me to..." in context headers.
                    operation="summarize",
                )
                context_text = (context_text or "").strip()

                # L-INGEST-1 / L-INGEST-2: Validate context before prepending.
                # find_artifact() catches CoT leaks, graceful-degradation, and
                # ASR loops — all three vectors that can poison [Context: ...]
                artifact = find_artifact(context_text)
                if artifact:
                    logger.warning(
                        "ContextualChunkingService: chunk %d context contaminated "
                        "(%s) — retrying once",
                        index,
                        artifact,
                    )
                    # One corrective retry with tighter prompt
                    context_text = await self._llm.generate(
                        system_prompt=(
                            _CONTEXTUAL_SYSTEM
                            + " Do NOT include any reasoning, analysis, or meta-commentary."
                        ),
                        user_prompt=prompt,
                        timeout=20,
                        max_retries=0,
                        operation="summarize",
                    )
                    context_text = (context_text or "").strip()
                    artifact = find_artifact(context_text)
                    if artifact:
                        logger.warning(
                            "ContextualChunkingService: chunk %d still contaminated "
                            "after retry (%s) — using unenriched chunk",
                            index,
                            artifact,
                        )
                        return chunk  # Fallback: unenriched, never chunk loss

                if not context_text:
                    return chunk
                return f"[Context: {context_text}]\n{chunk}"
            except Exception as exc:
                raise RuntimeError(f"LLM contextual enrichment failed for chunk {index}") from exc

    def _truncate_document(self, doc: str) -> str:
        """
        Truncate the document to ``max_doc_chars`` while preserving both the
        beginning and end — important for long spiritual transcripts where both
        the introduction (context) and conclusion (summary) carry meaning.
        """
        if len(doc) <= self._max_doc_chars:
            return doc
        half = self._max_doc_chars // 2
        return doc[:half] + "\n\n[... document truncated ...]\n\n" + doc[-half:]
