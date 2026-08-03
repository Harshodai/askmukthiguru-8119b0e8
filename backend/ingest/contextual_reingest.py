"""Contextual re-ingestion from spiritual_wisdom into spiritual_wisdom_contextual.

Reads source payloads from the existing Qdrant collection, reconstructs each
source document, re-chunks it with boundary-aware chunking, situates every chunk
with a local Ollama-generated contextual header, and writes the new chunks into
a dedicated `_contextual` collection with identical dense+sparse vector and
payload index configuration.

Design choices:
- Local Ollama only, primary/fallback model swap inside a thin wrapper.
- Embeddings reuse the project's bge-m3 EmbeddingService (1024-dim dense+sparse).
- Deterministic point IDs make the task idempotent.
- Progress is resumed via scripts/ingestion/ingestion_state.json.
- Runtime Ollama health/model check prevents silent stalls.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiohttp
import urllib.request
from qdrant_client import QdrantClient

from app.config import settings
from ingest.boundary_chunker import BoundaryChunker
from ingest.deduplication import LSHNearDupIndex
from services.contextual_chunking_service import ContextualChunkingService
from services.embedding_service import EmbeddingService
from services.ollama_service import OllamaService
from services.qdrant.client import QdrantClientManager
from services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE_COLLECTION: str = settings.qdrant_collection
_TARGET_SUFFIX: str = "_contextual"
_SOURCE_VERSION_BUMP: int = 2
_CHUNK_TYPE: str = "contextual"

# Parent-child ("small-to-big") sizing. The child is the stored/searched chunk;
# the parent is what `rag/nodes/retrieval.py` swaps in before generation, so the
# LLM reads a passage instead of a fragment.
#
# Blue built parents with RecursiveCharacterTextSplitter(chunk_size=500) and got
# a median parent of 320 characters — smaller than many of its own children,
# which makes the swap a no-op at best. Sizing here follows the small-to-big
# literature (child 50-200 tokens, parent 500-1500 tokens): at roughly 4 chars
# per token that is a 2,000-6,000 char parent. Parents are built from whole
# consecutive chunks, so no sentence is split across a parent boundary.
_PARENT_MIN_CHARS: int = 2000
_PARENT_MAX_CHARS: int = 6000

# Per-chunk provenance inherited from the ORIGINAL payload a chunk's text came
# from, rather than from payloads[0]. `title` and `page_range` vary WITHIN a
# source for PageIndex-parsed books (The_Four_Sacred_Secrets.pdf carries a
# distinct section title and page range per node), so stamping every chunk with
# the first payload's values mis-cites all 1,171 of its points to one chapter.
# `cluster_id` is deliberately NOT inherited: it is a RAPTOR clustering id scoped
# to the collection that produced it, and `navigate_knowledge_tree` filters leaf
# search by it. Copying blue's leaf cluster ids into a re-chunked collection whose
# summaries raptor.py has yet to rebuild would filter correct chunks out against
# clusters that no longer describe them. `node_id` is a PageIndex *section* id —
# a property of the document, so it migrates.
_INHERITED_PER_CHUNK: tuple[str, ...] = ("title", "page_range", "node_id")

# Sources whose text is already edited prose, so LLM "transcript correction" can
# only damage it. See _correct_full_text.
_NO_LLM_CORRECTION_TYPES: frozenset[str] = frozenset({"book", "pdf", "article", "web"})

# Coverage floors for _assert_coverage. A re-ingest transforms a document; it does
# not summarize one. Losing >15% of a teaching means a stage malfunctioned, not
# that the teaching was verbose. 0.85 is deliberately loose enough to absorb
# legitimate losses (the quality gate rejecting a genuine ASR loop, whitespace
# normalisation) and tight enough to have caught the 2026-08-01 incident, where
# the corrector returned 35% of the input and every existing gate passed it.
_MIN_STAGE_COVERAGE: float = 0.85
_WARN_STAGE_COVERAGE: float = 0.95
# Tied to SemanticChunker's min_chunk_chars=300: below roughly that size the
# chunker cannot preserve coverage even when working correctly.
_MIN_DOC_CHARS_FOR_COVERAGE: int = 500
def _resolve_state_file() -> Path:
    """Locate the resume checkpoint, working both in the repo and in the image.

    `parents[2]` is the repo root when this file lives at
    `backend/ingest/contextual_reingest.py` — but inside the image `backend/` IS
    `/app`, so the same expression resolves to `/` and the checkpoint path
    becomes `/scripts/ingestion/…`, which does not exist and is not writable.
    The 2026-08-02 re-ingest hit exactly that: every save logged
    "Permission denied" as a WARNING and continued, so no source was ever
    recorded as processed and a resumed run would redo all of them. This is the
    same path-resolution trap CLAUDE.md documents for OKF_DIR.

    Order: explicit env override, then the repo layout, then the image layout,
    then a writable temp fallback so a checkpoint always has somewhere to land.
    """
    override = os.environ.get("REINGEST_STATE_FILE")
    if override:
        return Path(override)

    here = Path(__file__).resolve()
    for candidate in (
        here.parents[2] / "scripts" / "ingestion",   # repo: backend/ingest/… -> repo root
        here.parents[1] / "scripts" / "ingestion",   # image: /app/ingest/…   -> /app
    ):
        if candidate.parent.is_dir():
            return candidate / "ingestion_state.json"
    return Path(tempfile.gettempdir()) / "ingestion_state.json"


_STATE_FILE: Path = _resolve_state_file()
_STATE_KEY: str = "contextual_reingest_processed_sources"
# Per-section resume for multi-section sources. A 25-section book runs for hours;
# a single write at the end means a crash in section 24 discards all of it.
_STATE_KEY_SECTIONS: str = "contextual_reingest_processed_sections"


def _ollama_model_available_sync(base_url: str, model: str, timeout: float = 10.0) -> bool:
    """Synchronous check that Ollama is reachable and *model* is in its tag list."""
    import json as _json
    import socket as _socket

    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            if resp.status != 200:
                return False
            data = _json.loads(resp.read().decode("utf-8"))
            names = {m.get("name", "") for m in data.get("models", [])}
            return model in names
    except (_socket.timeout, urllib.error.URLError, ConnectionError, Exception) as exc:
        logger.debug("Ollama availability check failed for %s/%s: %s", url, model, exc)
        return False


class _OpenRouterContextualizer:
    """OpenRouter-backed contextualizer with the same surface as the Ollama one.

    Gated as an approved dev-only exception (requires ALLOW_OPENROUTER_REINGEST=1 in prod).
    Note: Document and chunk text are sent to the hosted OpenRouter endpoint.
    Default provider remains local Ollama so production inference makes zero external API calls.

    Selected by ``reingest_llm_provider=openrouter``. Model defaults to
    ``google/gemma-3-12b-it``, chosen by measurement rather than list price: a
    full re-ingest is one call per chunk, so seconds-per-chunk dominates the
    bill. Measured on real corpus chunks, gemma ran 2.09s/chunk against
    qwen3.7-flash's 8.78s while using 42% fewer tokens, which cancels qwen's
    lower per-token price outright.

    Reasoning models are a deliberate exclusion. ``openai/gpt-5-nano`` returned
    ``None`` content in the same bake-off — the budget went to hidden thinking
    tokens. Chain-of-thought leaking into chunk text is what contaminated 30.2%
    of this corpus, so the ingestion path should not run a model that emits it.
    """

    _ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        skip_health_check: bool = False,
    ) -> None:
        if settings.is_production and os.environ.get("ALLOW_OPENROUTER_REINGEST", "").strip().lower() not in {"1", "true", "yes"}:
            raise RuntimeError(
                "_OpenRouterContextualizer is a dev-only exception and disabled in production. "
                "Inference must remain local with no external API calls. Chunk and document text are sent to the hosted endpoint."
            )

        self._model = model or settings.reingest_openrouter_model or "google/gemma-3-12b-it"
        self._api_key = api_key or settings.openrouter_api_key or ""
        if not skip_health_check and not self._api_key:
            # Fail fast rather than burn an hours-long job on 401s.
            raise RuntimeError(
                "REINGEST_LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is unset. "
                "Set it in the environment (never in a tracked file)."
            )

    @property
    def service(self) -> "_OpenRouterContextualizer":
        """Return self so ContextualChunkingService can call .generate()."""
        return self

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        timeout: float = 30.0,
        max_retries: int = 1,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> str:
        import httpx

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": 256,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        last_exc: Optional[Exception] = None
        for attempt in range(max(1, max_retries + 1)):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(self._ENDPOINT, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                content = (data["choices"][0]["message"].get("content") or "").strip()
                if not content:
                    # A reasoning model that spent its budget on hidden thinking
                    # returns empty content. Surface it — silently writing an
                    # empty context header would degrade every chunk it touched.
                    # Do NOT diagnose this as "it is a reasoning model" — that
                    # claim was in this message and was wrong: on 2026-08-02
                    # gemma-3-12b-it returned HTTP 200 on 278 requests and empty
                    # content on 12 of them. Empty content is usually transient
                    # (provider hiccup, truncated stream), and only sometimes a
                    # model-class problem. State the observation, not a guess.
                    raise RuntimeError(
                        f"OpenRouter model {self._model} returned HTTP 200 with empty "
                        "content. Usually transient — the caller retries. If it "
                        "persists across retries, check whether this model emits "
                        "reasoning tokens that consume the max_tokens budget."
                    )
                return content
            except Exception as exc:  # noqa: BLE001 - retried, then re-raised
                last_exc = exc
                logger.warning(
                    "OpenRouter contextualizer (%s) failed on attempt %d/%d: %s",
                    self._model, attempt + 1, max_retries + 1, exc,
                )
        raise RuntimeError(
            f"OpenRouter contextualizer failed after {max_retries + 1} attempts: {last_exc}"
        )


class _LocalOllamaContextualizer:
    """Thin wrapper that forces local Ollama and primary/fallback model swap.

    Bypasses the normal OllamaService provider guard so re-ingest can use any
    locally-tagged Ollama model even when OLLAMA_CLOUD_ONLY is true globally.
    The primary model is loaded at construction; if generation fails with an
    Ollama ResponseError, the wrapper swaps to the fallback model and retries
    once. This keeps the re-ingest resilient to transient model retirement.

    Runtime guard: construction checks that the requested base URL/model are
    actually reachable. If neither primary nor fallback is available, the
    engine fails fast with an actionable message instead of retrying silently.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        existing_service: Optional[OllamaService] = None,
        skip_health_check: bool = False,
    ) -> None:
        self._base_url = base_url or settings.ollama_base_url or "http://localhost:11434"
        self._primary_model = primary_model or os.environ.get("OLLAMA_REINGEST_MODEL", "gemini-3-flash-preview:cloud")
        self._fallback_model = fallback_model or os.environ.get("OLLAMA_REINGEST_FALLBACK_MODEL", "deepseek-v4-flash:cloud")
        self._service = existing_service
        self._current_model = self._primary_model
        self._using_fallback = False

        if not skip_health_check:
            primary_ok = _ollama_model_available_sync(self._base_url, self._primary_model)
            if primary_ok:
                return
            fallback_ok = _ollama_model_available_sync(self._base_url, self._fallback_model)
            if fallback_ok:
                logger.warning(
                    "Primary re-ingest model %s unavailable at %s; falling back to %s",
                    self._primary_model,
                    self._base_url,
                    self._fallback_model,
                )
                self._current_model = self._fallback_model
                return
            raise RuntimeError(
                f"Contextual re-ingest requires Ollama at {self._base_url} with model "
                f"{self._primary_model} or fallback {self._fallback_model}. "
                "Set OLLAMA_REINGEST_MODEL / OLLAMA_REINGEST_FALLBACK_MODEL to available tags, "
                "or ensure Ollama is reachable."
            )

    @property
    def service(self) -> "_LocalOllamaContextualizer":
        """Return self so ContextualChunkingService can call .generate()."""
        return self

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        timeout: float = 30.0,
        max_retries: int = 1,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> str:
        """Generate via raw Ollama AsyncClient, with optional fallback swap."""
        from ollama import AsyncClient, ResponseError as OllamaResponseError

        async def _call(model: str) -> str:
            client = AsyncClient(host=self._base_url)
            response = await asyncio.wait_for(
                client.generate(
                    model=model,
                    prompt=user_prompt,
                    system=system_prompt,
                    options={"temperature": 0.3, "num_predict": 256},
                ),
                timeout=timeout,
            )
            return response.get("response", "")

        last_exc: Optional[Exception] = None
        for attempt in range(max(1, max_retries + 1)):
            try:
                return await _call(self._current_model)
            except OllamaResponseError as exc:
                last_exc = exc
                if exc.status_code == 410:
                    # Model retired — permanently swap to fallback.
                    if not self._using_fallback:
                        logger.warning(
                            "Contextualizer primary model %s retired; switching to fallback %s",
                            self._current_model,
                            self._fallback_model,
                        )
                        self._using_fallback = True
                        self._current_model = self._fallback_model
                        continue
                logger.warning(
                    "Contextualizer model %s failed on attempt %d/%d: %s",
                    self._current_model,
                    attempt + 1,
                    max_retries + 1,
                    exc,
                )
            except asyncio.TimeoutError as exc:
                last_exc = exc
                logger.warning(
                    "Contextualizer model %s timed out on attempt %d/%d",
                    self._current_model,
                    attempt + 1,
                    max_retries + 1,
                )
        raise RuntimeError(
            f"Contextual enrichment failed for model {self._current_model}"
        ) from last_exc


class ContextualReingestEngine:
    """Re-ingest existing Qdrant sources into the contextual collection."""

    def __init__(
        self,
        source_collection: Optional[str] = None,
        target_collection: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
        contextualizer: Optional[_LocalOllamaContextualizer] = None,
        qdrant_client: Optional[QdrantClient] = None,
        state_file: Optional[Path] = None,
    ) -> None:
        self._source_collection = source_collection or _DEFAULT_SOURCE_COLLECTION
        self._target_collection = target_collection or f"{self._source_collection}{_TARGET_SUFFIX}"

        # Reuse injected services when available; otherwise lazily create.
        self._embedding = embedding_service
        self._contextualizer = contextualizer
        self._external_qdrant = qdrant_client

        self._state_file = state_file or _STATE_FILE
        self._state: dict[str, Any] = self._load_state()

        # Lazy-created clients
        self._qdrant: Optional[QdrantClient] = None
        self._target_service_instance: Optional[QdrantService] = None
        self._dedup_index: Optional[LSHNearDupIndex] = None
        self._dedup_index_seeded: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def dry_run(
        self,
        source_url: Optional[str] = None,
        limit: int = 1,
        skip_health_check: bool = False,
    ) -> dict[str, Any]:
        """Preview what would be re-ingested without writing to Qdrant.

        Health check is skipped during dry-run for fast previews; the real
        re-ingest task runs it before any LLM work.
        """
        # Force lazy initialization of the contextualizer (and health check)
        # so callers get a clear error if Ollama is not ready.
        self._contextualizer_service(skip_health_check=skip_health_check)
        sources = self._list_source_groups(source_url=source_url, limit=limit)
        previews = []
        total_chunks = 0
        for src_url, payloads in sources.items():
            full_text = self._reconstruct_full_text(payloads)
            raw_chunks = self._rechunk(full_text, payloads)
            contextual = await self._contextualize(full_text, raw_chunks, src_url)
            total_chunks += len(contextual)
            previews.append(
                {
                    "source_url": src_url,
                    "title": payloads[0].get("title", "") if payloads else "",
                    "original_chunk_count": len(payloads),
                    "new_chunk_count": len(contextual),
                    "sample_header": (contextual[0].split("\n", 1)[0] if contextual else ""),
                    "sample_chunk": (contextual[0][:300] if contextual else ""),
                }
            )
        return {
            "dry_run": True,
            "target_collection": self._target_collection,
            "sources_previewed": len(previews),
            "total_new_chunks": total_chunks,
            "previews": previews,
        }

    async def reingest(
        self,
        source_url: Optional[str] = None,
        limit: Optional[int] = None,
        skip_processed: bool = True,
    ) -> dict[str, Any]:
        """Re-ingest sources into the contextual collection."""
        # Fail fast if Ollama is not available — never queue a hours-long job
        # that will stall on the first LLM call.
        self._contextualizer_service(skip_health_check=False)
        self._ensure_target_collection()

        processed: set[str] = set(self._state.get(_STATE_KEY, [])) if skip_processed else set()
        sources = self._list_source_groups(source_url=source_url, limit=limit)

        # Build a dict of all candidate sources so we can report skipped ones.
        all_sources = dict(sources)
        # Filter already processed unless a specific source is requested.
        if source_url is None and skip_processed:
            sources = {k: v for k, v in sources.items() if k not in processed}
            skipped_sources = len(all_sources) - len(sources)
        else:
            skipped_sources = 0

        total_sources = 0
        total_chunks = 0
        failed_sources: list[dict[str, str]] = []

        for src_url, payloads in sources.items():
            try:
                chunks_written = await self._reingest_source(src_url, payloads)
                total_sources += 1
                total_chunks += chunks_written
                processed.add(src_url)
                self._state.setdefault(_STATE_KEY, []).append(src_url)
                self._save_state()
            except Exception as exc:
                logger.exception("Contextual re-ingest failed for %s", src_url)
                failed_sources.append({"source_url": src_url, "error": str(exc)})

        return {
            "status": "ok",
            "target_collection": self._target_collection,
            "sources_processed": total_sources,
            "chunks_written": total_chunks,
            "skipped": skipped_sources,
            "failed_sources": failed_sources,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, Any]:
        if not self._state_file.exists():
            return {}
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load ingestion state file %s: %s", self._state_file, exc)
            return {}

    def _save_state(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            # Deduplicate state list
            existing = self._state.get(_STATE_KEY, [])
            if isinstance(existing, list):
                self._state[_STATE_KEY] = list(dict.fromkeys(existing))
            self._state_file.write_text(
                json.dumps(self._state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Could not save ingestion state file %s: %s", self._state_file, exc)

    def _client(self) -> QdrantClient:
        if self._qdrant is None:
            if self._external_qdrant:
                self._qdrant = self._external_qdrant
            else:
                manager = QdrantClientManager(collection=self._source_collection)
                self._qdrant = manager.client
        return self._qdrant

    def _ensure_target_collection(self) -> None:
        self._target_service().init_collection()

    def _target_service(self) -> QdrantService:
        """QdrantService facade bound to the contextual target collection.

        All writes (and the source-level delete) for this migration flow
        through services/qdrant_service.py — the approved storage boundary —
        not the raw Qdrant client. When an external client was injected
        (tests / batch runners), it is forwarded here too, so collection
        initialization, deletes, and upserts all hit the same Qdrant endpoint
        instead of a client rebuilt from application settings.
        """
        if self._target_service_instance is None:
            self._target_service_instance = QdrantService(
                collection=self._target_collection,
                client=self._external_qdrant,
            )
        return self._target_service_instance

    def _embedder(self) -> EmbeddingService:
        if self._embedding is None:
            self._embedding = EmbeddingService()
        return self._embedding

    def _contextualizer_service(self, skip_health_check: bool = False):
        """Ollama by default; OpenRouter when ``REINGEST_LLM_PROVIDER=openrouter``.

        A full re-ingest is one LLM call per chunk, so throughput dominates cost
        here. A 2026-08-01 bake-off on real corpus chunks (scored with
        ``text_quality_filter.find_artifact``) measured, per chunk:
        gemma-3-12b-it 2.09s / 0 artifacts, nova-lite 6.28s / 0, qwen3.7-flash
        8.78s / 0 — and gpt-5-nano returned *null content*, a reasoning model
        spending its budget on hidden thinking tokens, which is the exact class
        of model whose output poisoned this corpus in the first place.
        """
        if self._contextualizer is None:
            provider = (settings.reingest_llm_provider or "").strip().lower()
            if provider == "openrouter":
                self._contextualizer = _OpenRouterContextualizer(
                    skip_health_check=skip_health_check
                )
            else:
                self._contextualizer = _LocalOllamaContextualizer(
                    skip_health_check=skip_health_check
                )
        return self._contextualizer

    def _get_dedup_index(self) -> Optional[LSHNearDupIndex]:
        """Lazy MinHash-LSH index of already-accepted raw chunk texts (§6.4).

        The gurus deliver the same core teaching across hundreds of talks, so
        the identical raw chunk text (or a near-identical variant) shows up
        under many source_urls. Deduplicating the *raw* chunks (before the
        contextualizer LLM call) drops those repeats early: fewer LLM calls,
        fewer embeddings, and a green collection without duplicate teachings.
        Contextualized text is NOT used for similarity — the per-document
        context prefix would mask true duplicates.
        """
        if self._dedup_index is None:
            self._dedup_index = LSHNearDupIndex(threshold=settings.ingestion_dedup_threshold)
        return self._dedup_index

    def _seed_dedup_index_from_target(self) -> None:
        """Index chunk texts already in the target collection (resume-safe)."""
        try:
            client = self._client()
            offset: Optional[Any] = None
            page_size = 1000
            while True:
                records, next_offset = client.scroll(
                    collection_name=self._target_collection,
                    limit=page_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for rec in records:
                    payload = rec.payload or {}
                    text = payload.get("parent_text") or payload.get("text", "")
                    if text:
                        self._get_dedup_index().add(text, {"authority_tier": payload.get("authority_tier", "primary")})
                if next_offset is None:
                    break
                offset = next_offset
        except Exception as exc:
            logger.warning("Could not seed dedup index from target collection: %s", exc)

    def _dedup_raw_chunks(self, raw_chunks: list[str]) -> list[str]:
        """Drop raw chunks that are near-duplicates of already-accepted chunks."""
        if not settings.ingestion_deduplication_enabled:
            return raw_chunks
        if not self._dedup_index_seeded:
            self._seed_dedup_index_from_target()
            self._dedup_index_seeded = True
        kept: list[str] = []
        dropped = 0
        for chunk in raw_chunks:
            if self._get_dedup_index().is_near_duplicate(chunk):
                dropped += 1
                continue
            self._get_dedup_index().add(chunk, {"authority_tier": "primary"})
            kept.append(chunk)
        if dropped:
            logger.info("Cross-source dedup: dropped %d duplicate chunks", dropped)
        return kept

    def _list_source_groups(
        self,
        source_url: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Scroll source payloads grouped by source_url."""
        client = self._client()
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        offset: Optional[Any] = None
        page_size = 1000
        overall_limit = limit

        while True:
            records, next_offset = client.scroll(
                collection_name=self._source_collection,
                limit=page_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for rec in records:
                payload = rec.payload or {}
                src = payload.get("source_url", "")
                if not src:
                    continue
                if source_url is not None and src != source_url:
                    continue
                payload["_id"] = str(rec.id)
                groups[src].append(payload)

            offset = next_offset
            if offset is None or len(records) == 0:
                break

        if overall_limit is not None and len(groups) > overall_limit:
            groups = dict(list(groups.items())[:overall_limit])

        # Drop RAPTOR summaries before reconstruction, then sort.
        #
        # Blue holds two kinds of chunk per source: verbatim transcript
        # ("video_enhanced") and abstractive RAPTOR summaries ("summary",
        # raptor_level > 0). They share the same chunk_index space — a source can
        # have BOTH a summary and a transcript chunk at index 0 — so sorting by
        # chunk_index alone interleaves them, and _reconstruct_full_text then
        # splices a machine-written paraphrase into the middle of the guru's own
        # words. That is how "a new generation ion with oneself" and
        # "you are the whole. fter a few months" ended up stored as doctrine on
        # 2026-08-01: summary text welded into transcript at the seams.
        #
        # A re-ingest reconstructs the ORIGINAL TEACHING. Summaries are derived
        # artifacts, rebuilt downstream by raptor.py, and must never be an input
        # to it. The secondary sort key keeps ordering deterministic when two
        # transcript chunks still share an index.
        for src in groups:
            groups[src] = [
                p
                for p in groups[src]
                if p.get("content_type") != "summary" and not (p.get("raptor_level") or 0)
            ]
            groups[src].sort(key=lambda p: (p.get("chunk_index", 0), str(p.get("_id", ""))))
        # A source whose chunks were ALL summaries has no transcript to re-ingest.
        return {src: payloads for src, payloads in groups.items() if payloads}

    @staticmethod
    def _reconstruct_full_text(payloads: list[dict[str, Any]]) -> str:
        """Join source chunks in order to reconstruct the full document."""
        texts = []
        for p in payloads:
            txt = p.get("text", "")
            # Strip the old contextual header if present so re-chunking is clean.
            if txt.startswith("["):
                # Remove first line when it is the old [Source: ...] header.
                first_newline = txt.find("\n")
                if first_newline != -1 and txt[:first_newline].rstrip().endswith("]"):
                    txt = txt[first_newline + 1 :]
            texts.append(txt.strip())
        full_doc = "\n\n".join(t for t in texts if t)
        from services.doctrine_terms import apply_corrections
        return apply_corrections(full_doc)

    @staticmethod
    def _chunk_spans(full_text: str, chunks: list[str]) -> list[tuple[int, int]]:
        """Locate each chunk's character span inside ``full_text``.

        Matching is WHITESPACE-INSENSITIVE. SemanticChunker collapses runs of
        whitespace, and a reconstructed transcript is full of double spaces at
        payload seams, so a literal ``find`` misses every chunk: the 2026-08-02
        live run located 0 of 2 spans and therefore silently ran with late
        chunking fully disabled (``0/2 dense vectors pooled from the document``)
        while every log line and gate reported success. Both callers degrade
        quietly on an empty span — late chunking falls back to standalone
        pooling, and the provenance map falls back to payload 0 — so this failure
        has no symptom other than the numbers being wrong.

        Scans forward from the previous match so repeated sentences map to the
        occurrence the chunker actually emitted, not the first one in the
        document. A chunk that genuinely cannot be found still yields ``(0, 0)``.
        """
        # Normalised copy plus a position map back into the original string, so
        # a match found in normalised space returns real character offsets.
        norm_parts: list[str] = []
        back: list[int] = []
        prev_space = False
        for i, ch in enumerate(full_text):
            if ch.isspace():
                if prev_space:
                    continue
                norm_parts.append(" ")
                prev_space = True
            else:
                norm_parts.append(ch)
                prev_space = False
            back.append(i)
        norm = "".join(norm_parts)

        def _normalize(text: str) -> str:
            return " ".join(text.split())

        spans: list[tuple[int, int]] = []
        cursor = 0
        for chunk in chunks:
            probe = _normalize(chunk)
            if not probe:
                spans.append((0, 0))
                continue
            idx = norm.find(probe, cursor)
            if idx < 0:
                # Anchor on the chunk's opening words — enough to place it even
                # if the chunker altered the tail (a trailing ellipsis, say).
                head = probe[:80]
                idx = norm.find(head, cursor)
                if idx < 0:
                    spans.append((0, 0))
                    continue
            end_norm = min(idx + len(probe), len(norm))
            start = back[idx]
            end = back[end_norm - 1] + 1 if end_norm > 0 else start
            spans.append((start, end))
            cursor = idx + 1
        return spans

    @staticmethod
    def _build_parents(source_url: str, chunks: list[str]) -> list[tuple[str, str]]:
        """Group consecutive chunks into parents; return one (id, text) per chunk.

        Parent ids are derived from the source URL and the parent's ordinal, not
        ``uuid4()``. Blue used uuid4, so re-ingesting a source minted brand-new
        parent ids for the same text and any cached or externally-held reference
        went dangling. A deterministic id makes the re-ingest idempotent, exactly
        like the deterministic point ids it already writes.

        A trailing group shorter than the minimum is merged into the previous
        parent instead of being emitted as a runt — a 200-char "parent" is the
        blue defect this method exists to avoid.
        """
        if not chunks:
            return []

        groups: list[list[int]] = []
        current: list[int] = []
        size = 0
        for i, chunk in enumerate(chunks):
            if current and size + len(chunk) > _PARENT_MAX_CHARS:
                groups.append(current)
                current, size = [], 0
            current.append(i)
            size += len(chunk)
            if size >= _PARENT_MIN_CHARS:
                groups.append(current)
                current, size = [], 0
        if current:
            prev_size = sum(len(chunks[i]) for i in groups[-1]) if groups else 0
            merge_fits = prev_size + size <= _PARENT_MAX_CHARS
            if groups and size < _PARENT_MIN_CHARS and merge_fits:
                groups[-1].extend(current)
            else:
                groups.append(current)

        assigned: list[tuple[str, str]] = [("", "")] * len(chunks)
        for ordinal, group in enumerate(groups):
            parent_id = f"{source_url}#parent-{ordinal}"
            parent_text = "\n\n".join(chunks[i].strip() for i in group)
            for i in group:
                assigned[i] = (parent_id, parent_text)
        return assigned

    @staticmethod
    def _origin_index_map(
        payloads: list[dict[str, Any]],
        spans: list[tuple[int, int]],
        full_text_len: int,
    ) -> list[int]:
        """Map each new chunk to the original payload its text came from.

        Correction and re-chunking both shift absolute offsets, so the match is
        made on FRACTIONAL position within the document: original payload *i*
        owns ``[c_i/T, c_(i+1)/T]`` of the source text, the new chunk owns
        ``[start/L, end/L]`` of the corrected text, and the payload with the
        largest overlap wins. Correction is length-guarded to 90-115% of the
        input (``_MAX_LENGTH_RATIO``), so fractional position is stable to a few
        percent — accurate enough to attribute a chunk to the right book section,
        which is what the inherited fields are for.

        Falls back to index 0 for a chunk whose span could not be located.
        """
        if not payloads:
            return [0] * len(spans)
        lengths = [len(str(p.get("text", "")).strip()) for p in payloads]
        total = sum(lengths)
        if total <= 0 or full_text_len <= 0:
            return [0] * len(spans)

        bounds: list[tuple[float, float]] = []
        cursor = 0
        for length in lengths:
            bounds.append((cursor / total, (cursor + length) / total))
            cursor += length

        mapped: list[int] = []
        for start, end in spans:
            if end <= start:
                mapped.append(0)
                continue
            lo, hi = start / full_text_len, end / full_text_len
            best_i, best_overlap = 0, 0.0
            for i, (b_lo, b_hi) in enumerate(bounds):
                overlap = min(hi, b_hi) - max(lo, b_lo)
                if overlap > best_overlap:
                    best_i, best_overlap = i, overlap
            mapped.append(best_i)
        return mapped

    def _rechunk(self, full_text: str, payloads: list[dict[str, Any]]) -> list[str]:
        """Re-chunk document using Semantic Topic-Shift Chunker."""
        from ingest.semantic_chunker import SemanticChunker
        embedder = getattr(self, "_embedding", None)
        chunker = SemanticChunker(
            embedding_service=embedder,
            min_chunk_chars=300,
            max_chunk_chars=1800,
        )
        return chunker.split(full_text)

    async def _contextualize(
        self,
        full_text: str,
        raw_chunks: list[str],
        source_label: str,
    ) -> list[str]:
        """Use local Ollama to situate each raw chunk within the full document."""
        contextualizer = self._contextualizer_service()
        # Concurrency was hardcoded at 3, sized for a single local Ollama process
        # where more in-flight requests just queue behind one GPU. Against a
        # hosted endpoint the calls are network-bound and 3 leaves the pipeline
        # idle: ~440 chunks at gemma's measured 2.09s each is ~5 minutes of
        # mostly waiting. Default 8; keep it at 3 for local Ollama by setting
        # REINGEST_CONTEXTUALIZER_CONCURRENCY, and lower it if OpenRouter starts
        # returning 429s — a rate-limit mid-run costs more than the parallelism
        # saves (2026-08-01: a 429 lost two complete runs).
        concurrency = max(1, int(settings.reingest_contextualizer_concurrency))
        if (settings.reingest_llm_provider or "").strip().lower() != "openrouter":
            concurrency = min(concurrency, 3)
        service = ContextualChunkingService(
            llm=contextualizer.service,
            max_doc_chars=max(1_000, int(settings.reingest_contextualizer_doc_chars)),
            concurrency=concurrency,
        )
        return await service.enrich_chunks(full_text, raw_chunks, source_label=source_label)

    async def _correct_full_text(
        self, full_text: str, source_url: str, content_type: str = ""
    ) -> str:
        """Run LLM-based transcript proofreading over reconstructed document text.

        Skipped for already-edited sources. The corrector fixes ASR damage —
        missing punctuation, misheard doctrinal terms, run-on speech. A published
        book has none of that, so every call is spend with no upside and one real
        downside: the 2026-08-02 run of `The_Four_Sacred_Secrets.pdf` tripped the
        length guard on **108 of ~106 chunks** (ratios 0.21-0.32) because the
        model summarized the prose instead of proofreading it. The guard held and
        the original text was kept every time, which means ~440 OpenRouter calls
        bought exactly nothing. Dictionary-level doctrinal term correction still
        runs — that is `apply_corrections`, and it is deterministic.
        """
        if (content_type or "").strip().lower() in _NO_LLM_CORRECTION_TYPES:
            logger.info(
                "Skipping LLM correction for %s (content_type=%r is already edited "
                "prose); applying dictionary corrections only",
                source_url, content_type,
            )
            from services.doctrine_terms import apply_corrections
            return apply_corrections(full_text)
        try:
            from ingest.corrector import TranscriptCorrector
            contextualizer = self._contextualizer_service()
            corrector = TranscriptCorrector(contextualizer.service)
            return await corrector.correct_transcript(full_text, source_url=source_url)
        except Exception as exc:
            logger.warning("LLM transcript correction failed for %s (%s); falling back to dictionary cleanup", source_url, exc)
            from services.doctrine_terms import apply_corrections
            return apply_corrections(full_text)

    @staticmethod
    def _assert_coverage(stage: str, source_url: str, before: str, after: str) -> None:
        """Fail loudly when a stage silently drops most of the document.

        Every other gate in this pipeline detects text that is WRONG (LLM
        chain-of-thought, ASR loops, duplicates). Nothing detected text that was
        simply MISSING — and on 2026-08-01 that gap let the corrector return
        stubs that reduced a 22,487-char transcript to 7,876 chars while
        `find_artifact` passed 6/6 and `corpus_audit` reported 0.0% contaminated.
        Truncation leaves no artifact to match; it leaves fluent, on-topic
        doctrine with two thirds of the teaching gone.

        For a doctrine corpus, silently losing a teaching is worse than keeping a
        dirty chunk: a dirty chunk is visible and fixable, a missing one is
        neither. So this raises rather than warns — the source is skipped, logged
        as failed, and stays available for a retry, instead of being written in a
        mutilated form and marked done.
        """
        before_len, after_len = len(before.strip()), len(after.strip())
        if before_len == 0:
            return
        # Below the chunker's own minimum chunk size, coverage cannot hold by
        # construction: SemanticChunker(min_chunk_chars=300) legitimately emits
        # little or nothing for a sub-300-char document, so enforcing a ratio
        # there would fire on correct behaviour. A real doctrine transcript is
        # tens of thousands of characters; anything this small is a fixture or a
        # degenerate source with a different problem.
        if before_len < _MIN_DOC_CHARS_FOR_COVERAGE:
            return
        ratio = after_len / before_len
        if ratio < _MIN_STAGE_COVERAGE:
            raise ValueError(
                f"{stage} dropped {(1 - ratio) * 100:.1f}% of {source_url} "
                f"({before_len} -> {after_len} chars, floor {_MIN_STAGE_COVERAGE:.0%}). "
                "Refusing to ingest a mutilated document."
            )
        if ratio < _WARN_STAGE_COVERAGE:
            logger.warning(
                "%s dropped %.1f%% of %s (%d -> %d chars) — under review threshold %.0f%%",
                stage, (1 - ratio) * 100, source_url, before_len, after_len,
                _WARN_STAGE_COVERAGE * 100,
            )

    @staticmethod
    def _section_groups(
        payloads: list[dict[str, Any]],
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        """Split a source into structural sections, preserving payload order.

        A PageIndex-parsed book carries `node_id` (and a per-section `title` /
        `page_range`) on every chunk; `The_Four_Sacred_Secrets.pdf` has 23 such
        sections across 1,171 payloads. A transcript has none and yields a single
        unit, so this is a no-op for the common case.

        Sections matter for three reasons, all of which the whole-document path
        got wrong:
        1. The contextualizer truncates its "document" to `max_doc_chars`. On a
           424,302-char book that is the first and last few thousand characters —
           **1.9% of the text** — so a chapter-7 chunk was situated against the
           front matter and the back cover. Per-section, the document the model
           reads is the chapter the chunk is actually in.
        2. Chunks must not straddle a chapter boundary. Structure-aware chunking
           constrains boundaries to lie inside a section; a chunk welding the end
           of one chapter to the start of the next is retrievable as neither.
        3. Parents must not straddle one either, for the same reason — and
           `title`/`page_range`/`node_id` become exact instead of inferred by
           fractional overlap.

        Contiguity, not identity, defines a section: a `node_id` that reappears
        after a different one starts a new group rather than merging across the
        document.
        """
        groups: list[tuple[str, list[dict[str, Any]]]] = []
        for payload in payloads:
            key = str(
                payload.get("node_id")
                or payload.get("page_range")
                or payload.get("title")
                or ""
            ).strip()
            if groups and groups[-1][0] == key:
                groups[-1][1].append(payload)
            else:
                groups.append((key, [payload]))
        # A source with no structural markers is one unit — every key is "".
        if len(groups) == 1 or all(not key for key, _ in groups):
            return [("", list(payloads))]
        return groups

    async def _reingest_source(
        self,
        source_url: str,
        payloads: list[dict[str, Any]],
    ) -> int:
        """Re-ingest one source, processing each structural section separately."""
        sections = self._section_groups(payloads)
        if len(sections) > 1:
            logger.info(
                "Contextual re-ingest: %s has %d structural sections — processing "
                "each as its own document so chunks, parents and contextual "
                "headers stay inside a section",
                source_url, len(sections),
            )

        target_service = self._target_service()
        done_all: dict[str, Any] = self._state.setdefault(_STATE_KEY_SECTIONS, {})
        done: list[str] = list(done_all.get(source_url, []))

        # Delete existing points ONCE, before the first section — never between
        # sections, or section 2 would wipe section 1. Skipped when resuming, for
        # the same reason. "Replace, never append" still holds per source; it is
        # just no longer coupled to writing everything in one call.
        if not done and target_service.check_source_exists(source_url):
            logger.info(
                "Contextual re-ingest: deleting existing target points for %s", source_url,
            )
            target_service.delete_by_source(source_url)

        written_total = 0
        next_index = 0
        for ordinal, (key, section_payloads) in enumerate(sections):
            label = f"{source_url}#{key or ordinal}" if len(sections) > 1 else source_url
            if label in done:
                # Recover the index cursor so a resumed run does not reuse point
                # ids already written by the completed sections.
                next_index += len(section_payloads)
                logger.info("Section %s already written — skipping", label)
                continue
            try:
                chunks, metadatas, dense, sparse = await self._ingest_unit(
                    source_url, section_payloads, label
                )
            except ValueError as exc:
                # A mutilated or mixed-pooling SECTION must not abort the other 24.
                logger.error("Section %s failed and was skipped: %s", label, exc)
                continue
            if not chunks:
                logger.warning("Section %s produced no chunks after the quality gate", label)
                done.append(label)
                done_all[source_url] = done
                self._save_state()
                continue

            # chunk_index is globally unique across the source: deterministic point
            # ids are source_url:chunk_index:raptor_level, so per-section numbering
            # restarting at 0 would have every section overwrite the first one.
            for offset, meta in enumerate(metadatas):
                meta["chunk_index"] = next_index + offset
            next_index += len(metadatas)

            written = target_service.upsert_chunks(
                chunks, dense, metadatas, sparse_vectors=sparse,
            )
            written_total += written
            done.append(label)
            done_all[source_url] = done
            self._save_state()
            logger.info(
                "Contextual re-ingest: wrote %d chunks for section %s (%d/%d sections, "
                "%d chunks so far)",
                written, label, len(done), len(sections), written_total,
            )

        if not written_total:
            logger.warning(
                "Contextual re-ingest: every chunk from %s was rejected — this "
                "source needs re-ingestion from origin, not migration", source_url,
            )
            return 0

        logger.info(
            "Contextual re-ingest: wrote %d chunks for %s to %s",
            written_total, source_url, self._target_collection,
        )
        return written_total

    async def _ingest_unit(
        self,
        source_url: str,
        payloads: list[dict[str, Any]],
        unit_label: str,
    ) -> tuple[list[str], list[dict[str, Any]], list[list[float]], list[dict]]:
        """Correct, chunk, contextualize and embed ONE document unit.

        A unit is a whole transcript or a single book section. Returns the
        pieces to write; the caller owns deletion and the upsert so a
        multi-section source is written once, atomically.
        """
        full_text = self._reconstruct_full_text(payloads)
        source_content_type = str((payloads[0] if payloads else {}).get("content_type") or "")
        corrected = await self._correct_full_text(
            full_text, source_url, content_type=source_content_type
        )
        self._assert_coverage("transcript correction", unit_label, full_text, corrected)
        full_text = corrected

        raw_chunks = self._rechunk(full_text, payloads)
        if not raw_chunks:
            logger.info("No chunks produced for %s", source_url)
            return 0
        # Chunking partitions text; it must not lose most of it. Overlap can push
        # the joined length ABOVE the input, which is fine — only a floor applies.
        self._assert_coverage("chunking", unit_label, full_text, "".join(raw_chunks))

        # §6.4 — drop chunks whose teaching already entered the green collection
        # from an earlier source. Runs before the contextualizer LLM call, so
        # duplicates cost zero LLM tokens and zero embeddings.
        raw_chunks = self._dedup_raw_chunks(raw_chunks)
        if not raw_chunks:
            logger.info("All chunks for %s are duplicates of earlier sources; skipping", source_url)
            return 0

        contextual_chunks = await self._contextualize(full_text, raw_chunks, unit_label)
        # Contextualization PREPENDS a header, so output should grow, never shrink.
        # This assertion was missing in the first version of the coverage invariant
        # — I guarded correction and chunking but not the one LLM stage between
        # them and storage, which is precisely the gap the invariant exists to
        # close. A contextualizer that silently returns fewer/empty chunks would
        # otherwise reach the quality gate as unheaded raw text and be rejected
        # there, reported as "contamination" rather than as the upstream LLM
        # failure it actually is.
        self._assert_coverage(
            "contextualization", unit_label, "".join(raw_chunks), "".join(contextual_chunks)
        )

        # Embed in bounded batches. A single encode_batch() over every chunk of a
        # source materialises dense + sparse + ColBERT token vectors for all of
        # them at once: for 332 chunks that peak sits on top of ~2.3 GB of bge-m3
        # weights and OOM-killed the 2026-08-01 pilot container (exit 137) on a
        # 7.75 GB VM. Batching makes peak memory a function of batch size rather
        # than source length, so a long transcript costs time, not the host.
        # encode_batch returns {"dense": [...], "sparse": [...]} — a dict of
        # per-chunk lists, not a list of per-chunk dicts. Merge key-wise so the
        # batched result is indistinguishable from a single large call.
        # Logged at INFO, not debug: on CPU fp32 this is the slowest stage by far
        # (a 2026-08-01 pilot spent 12+ minutes here for one 322-chunk source,
        # 3x the contextualizer's wall time) and it is silent between the "start"
        # and "done" log lines otherwise — the only signal an operator has during
        # that gap is memory drifting up and down, which answers "is it stuck?"
        # but not "how far along is it?". A visible per-batch line with elapsed
        # time and an ETA is cheap and is what was missing while diagnosing this.
        # Character spans of each raw chunk inside the corrected document. Used
        # by late chunking to pool the right token range, and by the provenance
        # map to attribute each chunk to the original payload it came from.
        spans = self._chunk_spans(full_text, raw_chunks)

        embedder = self._embedder()
        batch_size = max(1, int(getattr(settings, "reingest_embed_batch_size", 32)))
        total = len(contextual_chunks)
        n_batches = (total + batch_size - 1) // batch_size
        embed_start = time.monotonic()
        embeddings: dict[str, list] = {}
        for batch_num, i in enumerate(range(0, total, batch_size), start=1):
            part = embedder.encode_batch(contextual_chunks[i : i + batch_size])
            for key, values in (part or {}).items():
                embeddings.setdefault(key, []).extend(values)
            done = min(i + batch_size, total)
            elapsed = time.monotonic() - embed_start
            rate = elapsed / done if done else 0.0
            eta = rate * (total - done)
            logger.info(
                "Embedding %s: batch %d/%d — %d/%d chunks (%.1fs elapsed, ETA %.0fs)",
                source_url, batch_num, n_batches, done, total, elapsed, eta,
            )

        # §6.3 late chunking — replace the dense vector with one pooled from the
        # WHOLE document, so a chunk whose referents live in its neighbours ("that
        # state", "he said") still embeds what it is actually about. Measured on a
        # transcript excerpt: a chunk that never says "beautiful state" scored
        # 0.4744 against that query with today's CLS vectors and 0.7708 late-chunked
        # (+62%). Sparse vectors and the stored text are untouched — only the dense
        # vector changes, and the header still helps BM25 and the generation stage.
        #
        # Pooling must match on the query side: mean-pooled chunks searched with a
        # CLS query scored 0.4823, i.e. the entire gain disappears. `pooling` is
        # written into every payload so a collection declares how to query it
        # instead of leaving that as tribal knowledge.
        pooling_modes = ["cls"] * len(contextual_chunks)
        dense_vectors = embeddings.get("dense", [])
        if settings.reingest_late_chunking:
            late_vectors = self._embedder().encode_late_chunked(full_text, spans)
            replaced = 0
            recovered = 0
            for i in range(len(dense_vectors)):
                vec = late_vectors[i] if i < len(late_vectors) else None
                if vec and any(vec):
                    dense_vectors[i] = vec
                    replaced += 1
                else:
                    # A zero vector means _chunk_spans could not locate this
                    # chunk in the document. The old code kept the CLS vector
                    # here, which put CLS and mean vectors — ~0.757 cosine apart
                    # — in ONE collection: whichever pooling the query used, the
                    # other half of the corpus was scored across that gap, so
                    # ranking was wrong for every query. A collection has exactly
                    # one pooling mode. Mean-pool the chunk on its own instead;
                    # it loses the cross-chunk context late chunking provides but
                    # stays in the same vector space as everything around it.
                    dense_vectors[i] = self._embedder().encode_query_mean_pooled(
                        contextual_chunks[i]
                    )
                    recovered += 1
                pooling_modes[i] = "mean"
            logger.info(
                "Late chunking: %d/%d dense vectors pooled from the document, "
                "%d mean-pooled standalone (span not located) for %s",
                replaced, len(dense_vectors), recovered, source_url,
            )

        # One collection, one pooling mode — asserted, not assumed. A mixed
        # collection is silently wrong rather than loudly broken, which is why
        # the defect above survived a full pilot run undetected.
        distinct_pooling = set(pooling_modes)
        if len(distinct_pooling) > 1:
            raise ValueError(
                f"Refusing to write {unit_label}: mixed pooling modes "
                f"{sorted(distinct_pooling)} in one collection."
            )

        # Build metadata aligned with contextual chunks.
        #
        # `first` is now guaranteed to be a TRANSCRIPT chunk: _list_source_groups
        # filters RAPTOR summaries out of the group before this point. Previously
        # payloads[0] was whichever chunk sorted first, which for a source with a
        # summary at chunk_index 0 meant every re-ingested chunk inherited
        # content_type="summary" — mislabelling verbatim doctrine as a derived
        # artifact, on every source that had summaries.
        #
        # Note `or` rather than `.get(key, default)` throughout: blue payloads
        # carry these keys with EMPTY values (topic: ""), so a dict default never
        # fires and the empty string wins. That is how every green point ended up
        # with topic="" instead of the intended fallback.
        first = payloads[0] if payloads else {}
        now_iso = datetime.now(timezone.utc).isoformat()

        # Parent-child. The child is what gets embedded and searched; the parent
        # is what `retrieval.py` substitutes before generation (searcher.py reads
        # parent_id/parent_text/is_child straight off the payload). Green shipped
        # with none of these, so every small-to-big swap in the graph was a no-op
        # against the new collection while it still worked against blue.
        #
        # Built from raw_chunks, not contextual_chunks: the parent goes to the
        # LLM as prose, and repeating the "[Source: … | Speaker: …]" header once
        # per child inside it is noise the model has to read past.
        parents = self._build_parents(unit_label, raw_chunks)

        # Per-chunk provenance. See _INHERITED_PER_CHUNK — a book's title and
        # page range change from section to section, so these come from the
        # payload whose text this chunk actually overlaps.
        origin = self._origin_index_map(payloads, spans, len(full_text))

        metadatas: list[dict[str, Any]] = []
        for i, chunk in enumerate(contextual_chunks):
            src_payload = payloads[origin[i]] if i < len(origin) and payloads else first
            parent_id, parent_text = parents[i] if i < len(parents) else ("", "")
            meta = {
                "source_url": source_url,
                "title": src_payload.get("title") or first.get("title") or "",
                "speaker": first.get("speaker") or "Unknown",
                "topic": first.get("topic") or "Spiritual",
                # This IS a contextual chunk regardless of what blue called its
                # source rows — do not inherit the upstream content_type.
                "content_type": _CHUNK_TYPE,
                # How this vector was pooled. Late-chunked (mean) and CLS vectors
                # are ~0.757 cosine apart, so a collection must not mix them and a
                # searcher must pool its query the same way.
                "pooling": pooling_modes[i] if i < len(pooling_modes) else "cls",
                "source_type": first.get("source_type") or first.get("content_type") or "transcript",
                "language": first.get("language") or "en",
                "tags": list({t.strip().lower() for t in (first.get("tags") or ["general"]) if t and str(t).strip()}),
                "chunk_index": i,
                "raptor_level": 0,
                "source_version": _SOURCE_VERSION_BUMP,
                "ingested_at": now_iso,
                "authority_tier": first.get("authority_tier") or "primary",
                # `parent_chunk_id` stays omitted — it was a fresh uuid4() per
                # chunk pointing at no stored parent, a dangling reference that
                # read as a working index. The real parent fields below are the
                # ones searcher.py and retrieval.py actually consume.
                "parent_id": parent_id,
                "parent_text": parent_text,
                "is_child": True,
                "chunk_type": _CHUNK_TYPE,
                # `original_chunk_count` removed: it recorded how many blue rows
                # the source had, which is a property of the migration and not of
                # the chunk. Nothing reads it (0 points in blue carry it), and it
                # rode on 100% of green's payloads.
            }
            # Inherited only when the origin payload actually has a value —
            # writing `page_range: ""` on 89k transcript chunks would recreate
            # the empty-value problem that `or`-fallbacks exist to avoid.
            for field in _INHERITED_PER_CHUNK:
                if field == "title":
                    continue  # already set above, with a fallback
                value = src_payload.get(field)
                if value not in (None, "", [], {}):
                    meta[field] = value
            metadatas.append(meta)

        # Quality gate. This script is the backfill path from `spiritual_wisdom`
        # into `spiritual_wisdom_contextual`, and it writes through the raw Qdrant
        # client — so it bypasses the gate in `QdrantIndexer.upsert_chunks`.
        # Without this, the migration would faithfully copy the ~26,161
        # contaminated chunks (LLM chain-of-thought + ASR decoder loops) measured
        # in the 2026-08-01 audit straight into the clean collection, and the
        # re-ingest would accomplish nothing.
        from services.text_quality_filter import select_clean

        _keep, _rejected = select_clean(contextual_chunks)
        if _rejected:
            logger.warning(
                "Contextual re-ingest: dropped %d/%d chunks from %s failing the "
                "quality gate. First: %r in %r",
                len(_rejected), len(contextual_chunks), source_url,
                _rejected[0][1], _rejected[0][2],
            )
            _dense = embeddings["dense"]
            _sparse = embeddings.get("sparse", [])
            contextual_chunks = [contextual_chunks[i] for i in _keep]
            metadatas = [metadatas[i] for i in _keep]
            embeddings = {
                "dense": [_dense[i] for i in _keep],
                "sparse": [_sparse[i] if i < len(_sparse) else {} for i in _keep],
            }

        return (
            contextual_chunks,
            metadatas,
            embeddings.get("dense", []),
            embeddings.get("sparse", []),
        )

async def _smoke_test() -> None:
    """Self-check: dry-run the smallest YouTube source available locally."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

    # Force local Ollama settings for the self-check.
    os.environ.setdefault("LLM_PROVIDER", "ollama")
    os.environ.setdefault("OLLAMA_REINGEST_MODEL", "deepseek-v4-flash:cloud")
    os.environ.setdefault("OLLAMA_REINGEST_FALLBACK_MODEL", "gemini-3-flash-preview:cloud")
    os.environ.setdefault("OLLAMA_MODEL", "deepseek-v4-flash:cloud")
    os.environ.setdefault("OLLAMA_CLASSIFY_MODEL", "deepseek-v4-flash:cloud")
    os.environ.setdefault("OLLAMA_CLOUD_ONLY", "false")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

    engine = ContextualReingestEngine()
    preview = await engine.dry_run(limit=1, skip_health_check=True)
    print(json.dumps(preview, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_smoke_test()))
