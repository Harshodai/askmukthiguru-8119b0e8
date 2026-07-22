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
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct

from app.config import settings
from ingest.boundary_chunker import BoundaryChunker
from services.contextual_chunking_service import ContextualChunkingService
from services.embedding_service import EmbeddingService
from services.ollama_service import OllamaService
from services.qdrant.client import QdrantClientManager
from services.qdrant.utils import QdrantUtils

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE_COLLECTION: str = settings.qdrant_collection
_TARGET_SUFFIX: str = "_contextual"
_SOURCE_VERSION_BUMP: int = 2
_CHUNK_TYPE: str = "contextual"
_STATE_FILE: Path = Path(__file__).resolve().parents[2] / "scripts" / "ingestion" / "ingestion_state.json"
_STATE_KEY: str = "contextual_reingest_processed_sources"


class _LocalOllamaContextualizer:
    """Thin wrapper that forces local Ollama and primary/fallback model swap.

    The primary model is loaded at construction; if generation fails with an
    Ollama ResponseError, the wrapper swaps to the fallback model and retries
    once. This keeps the re-ingest resilient to transient model retirement.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        primary_model: str = "gemini-3-flash-preview:cloud",
        fallback_model: str = "deepseek-v4-flash:cloud",
        existing_service: Optional[OllamaService] = None,
    ) -> None:
        self._base_url = base_url
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._service = existing_service
        self._current_model = primary_model
        self._using_fallback = False

    @property
    def service(self) -> OllamaService:
        if self._service is None:
            # Build an OllamaService configured for local-only models.
            os.environ["OLLAMA_BASE_URL"] = self._base_url
            os.environ["OLLAMA_MODEL"] = self._current_model
            os.environ["OLLAMA_CLASSIFY_MODEL"] = self._current_model
            os.environ["OLLAMA_CLOUD_ONLY"] = "false"
            self._service = OllamaService()
        return self._service

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        from ollama import ResponseError as OllamaResponseError

        try:
            return await self.service.generate(system_prompt, user_prompt)
        except OllamaResponseError as exc:
            if self._using_fallback:
                raise
            logger.warning(
                "Contextualizer primary model %s failed (%s), switching to fallback %s",
                self._current_model,
                exc,
                self._fallback_model,
            )
            self._using_fallback = True
            self._current_model = self._fallback_model
            self._service = None
            return await self.service.generate(system_prompt, user_prompt)


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
        self._target_manager: Optional[QdrantClientManager] = None
        self._utils = QdrantUtils()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def dry_run(
        self,
        source_url: Optional[str] = None,
        limit: int = 1,
    ) -> dict[str, Any]:
        """Preview what would be re-ingested without writing to Qdrant."""
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
        if self._target_manager is None:
            self._target_manager = QdrantClientManager(collection=self._target_collection)
        self._target_manager.init_collection()

    def _embedder(self) -> EmbeddingService:
        if self._embedding is None:
            self._embedding = EmbeddingService()
        return self._embedding

    def _contextualizer_service(self) -> _LocalOllamaContextualizer:
        if self._contextualizer is None:
            self._contextualizer = _LocalOllamaContextualizer()
        return self._contextualizer

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
            if overall_limit is not None and len(groups) >= overall_limit:
                groups = dict(list(groups.items())[:overall_limit])
                break

        # Sort each group by chunk_index for stable reconstruction.
        for src in groups:
            groups[src].sort(key=lambda p: p.get("chunk_index", 0))
        return dict(groups)

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
        return "\n\n".join(t for t in texts if t)

    def _rechunk(self, full_text: str, payloads: list[dict[str, Any]]) -> list[str]:
        """Re-chunk the reconstructed document using boundary-aware chunking."""
        title = payloads[0].get("title", "") if payloads else ""
        speaker = payloads[0].get("speaker", "Unknown") if payloads else "Unknown"
        topic = payloads[0].get("topic", "Spiritual") if payloads else "Spiritual"

        # Use boundary-aware chunker first; contextual headers are added in a later step
        # by ContextualChunkingService so the situating LLM sees the raw chunk.
        chunker = BoundaryChunker(
            target_size=settings.rag_chunk_size,
            overlap_sentences=1,
        )
        return chunker.chunk(full_text)

    async def _contextualize(
        self,
        full_text: str,
        raw_chunks: list[str],
        source_label: str,
    ) -> list[str]:
        """Use local Ollama to situate each raw chunk within the full document."""
        contextualizer = self._contextualizer_service()
        service = ContextualChunkingService(
            llm=contextualizer.service,
            max_doc_chars=8_000,
            concurrency=3,
        )
        return await service.enrich_chunks(full_text, raw_chunks, source_label=source_label)

    async def _reingest_source(
        self,
        source_url: str,
        payloads: list[dict[str, Any]],
    ) -> int:
        full_text = self._reconstruct_full_text(payloads)
        raw_chunks = self._rechunk(full_text, payloads)
        if not raw_chunks:
            logger.info("No chunks produced for %s", source_url)
            return 0

        contextual_chunks = await self._contextualize(full_text, raw_chunks, source_url)

        # Embed dense + sparse in one pass.
        embeddings = self._embedder().encode_batch(contextual_chunks)

        # Build metadata aligned with contextual chunks.
        first = payloads[0] if payloads else {}
        now_iso = datetime.now(timezone.utc).isoformat()
        metadatas: list[dict[str, Any]] = []
        for i, chunk in enumerate(contextual_chunks):
            parent_id = str(uuid.uuid4())
            meta = {
                "source_url": source_url,
                "title": first.get("title", ""),
                "speaker": first.get("speaker", "Unknown"),
                "topic": first.get("topic", "Spiritual"),
                "content_type": first.get("content_type", "contextual"),
                "source_type": first.get("source_type") or first.get("content_type", "contextual"),
                "language": first.get("language", "en"),
                "tags": list({t.strip().lower() for t in (first.get("tags") or ["general"]) if t and str(t).strip()}),
                "chunk_index": i,
                "raptor_level": 0,
                "source_version": _SOURCE_VERSION_BUMP,
                "ingested_at": now_iso,
                "authority_tier": first.get("authority_tier", "primary"),
                "parent_chunk_id": parent_id,
                "chunk_type": _CHUNK_TYPE,
                "original_chunk_count": len(payloads),
            }
            metadatas.append(meta)

        # Prepare sparse vectors.
        sparse_vectors = embeddings.get("sparse", [])
        point_structs = []
        for i, (chunk, dense, meta) in enumerate(zip(contextual_chunks, embeddings["dense"], metadatas)):
            point_id = self._utils.make_point_id(source_url, i, 0)
            vector: dict[str, Any] = {"dense": dense}
            if i < len(sparse_vectors) and sparse_vectors[i]:
                vector["sparse"] = self._utils.sparse_dict_to_vector(sparse_vectors[i])
            point_structs.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"text": chunk, **meta},
                )
            )

        client = self._target_manager.client if self._target_manager else self._client()
        batch_size = 200
        for start in range(0, len(point_structs), batch_size):
            batch = point_structs[start : start + batch_size]
            client.upsert(
                collection_name=self._target_collection,
                points=batch,
            )

        logger.info(
            "Contextual re-ingest: wrote %d chunks for %s to %s",
            len(point_structs),
            source_url,
            self._target_collection,
        )
        return len(point_structs)


async def _smoke_test() -> None:
    """Self-check: dry-run the smallest YouTube source available locally."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

    # Force local Ollama settings for the self-check.
    os.environ.setdefault("LLM_PROVIDER", "ollama")
    os.environ.setdefault("OLLAMA_MODEL", "deepseek-v4-flash:cloud")
    os.environ.setdefault("OLLAMA_CLASSIFY_MODEL", "deepseek-v4-flash:cloud")
    os.environ.setdefault("OLLAMA_CLOUD_ONLY", "false")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

    engine = ContextualReingestEngine()
    preview = await engine.dry_run(limit=1)
    print(json.dumps(preview, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_smoke_test()))
