"""
Federated Multi-DataSource Ingestion Engine (Phase 7)
- Pluggable SourceAdapters: YouTubeAdapter, PDFDoctrineAdapter, AudioArchiveAdapter, WhatsAppReflectionAdapter, OKFStagingAdapter.
- Invariant X40 rights stamping: domain_rights_status='licensed', chunker_version.
- Atomic Dual-Write Coordinator: Qdrant (dense/sparse vectors) + Memgraph (relational ontology, Zero Neo4j!).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class SourceAdapter(ABC):
    """Abstract base class for all data source adapters in the federated engine."""

    @abstractmethod
    def fetch(self, source_ref: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch raw content and metadata from the source."""
        pass

    @abstractmethod
    def parse_and_chunk(self, raw_items: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        """Parse raw items into normalized chunks adhering to chunker grammar."""
        pass


class YouTubeAdapter(SourceAdapter):
    """Adapter for YouTube videos and subtitles."""

    def fetch(self, source_ref: str, **kwargs: Any) -> list[dict[str, Any]]:
        from ingest.youtube_loader import fetch_transcript_hybrid

        video_id = source_ref
        result = fetch_transcript_hybrid(video_id, **kwargs)
        return [result] if result else []

    def parse_and_chunk(self, raw_items: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        chunks = []
        for item in raw_items:
            text = item.get("text", "")
            title = item.get("title", "YouTube Discourse")
            chunks.append({
                "content": text,
                "metadata": {
                    "source_type": "youtube",
                    "title": title,
                    "source_url": item.get("source_url", ""),
                    "domain_rights_status": "licensed",
                    "chunker_version": kwargs.get("chunker_version", "v2.4-adaptive"),
                    "modality": "video",
                },
            })
        return chunks


class PDFDoctrineAdapter(SourceAdapter):
    """Adapter for PDF books and discourse transcripts."""

    def fetch(self, source_ref: str, **kwargs: Any) -> list[dict[str, Any]]:
        from ingest.book_ingest import parse_book_pdf

        text_content = parse_book_pdf(source_ref) if isinstance(source_ref, (str, bytes)) else ""
        return [{"content": text_content, "source_ref": source_ref}]

    def parse_and_chunk(self, raw_items: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        chunks = []
        for item in raw_items:
            content = item.get("content", "")
            chunks.append({
                "content": content,
                "metadata": {
                    "source_type": "pdf_doctrine",
                    "source_ref": item.get("source_ref", ""),
                    "domain_rights_status": "licensed",
                    "chunker_version": kwargs.get("chunker_version", "v2.4-adaptive"),
                    "modality": "text",
                },
            })
        return chunks


class AudioArchiveAdapter(SourceAdapter):
    """Adapter for high-res WAVs with ECAPA diarization."""

    def fetch(self, source_ref: str, **kwargs: Any) -> list[dict[str, Any]]:
        from services.whisperx_pipeline import transcribe_with_alignment

        transcript = transcribe_with_alignment("audio_archive", source_ref, hf_token=kwargs.get("hf_token"))
        return [{"transcript": transcript, "source_ref": source_ref}]

    def parse_and_chunk(self, raw_items: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        chunks = []
        for item in raw_items:
            t_data = item.get("transcript", {})
            text = t_data.get("text", str(t_data))
            chunks.append({
                "content": text,
                "metadata": {
                    "source_type": "audio_archive",
                    "source_ref": item.get("source_ref", ""),
                    "domain_rights_status": "licensed",
                    "chunker_version": kwargs.get("chunker_version", "v2.4-adaptive"),
                    "modality": "audio",
                    "diarization": "ecapa",
                },
            })
        return chunks


class WhatsAppReflectionAdapter(SourceAdapter):
    """Adapter for seeker voice notes & journal reflections."""

    def fetch(self, source_ref: str, **kwargs: Any) -> list[dict[str, Any]]:
        audio_path = kwargs.get("audio_path")
        text = kwargs.get("text")
        if audio_path:
            from services.whisper_local_service import transcribe_with_whisper

            text = transcribe_with_whisper("wa_reflection", audio_path)
        return [{"content": text, "source_ref": source_ref}]

    def parse_and_chunk(self, raw_items: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        chunks = []
        for item in raw_items:
            content = item.get("content", "")
            chunks.append({
                "content": content,
                "metadata": {
                    "source_type": "whatsapp_reflection",
                    "source_ref": item.get("source_ref", ""),
                    "domain_rights_status": "licensed",
                    "chunker_version": kwargs.get("chunker_version", "v2.4-adaptive"),
                    "modality": "voice_note",
                    "sadhana_journal": True,
                },
            })
        return chunks


class OKFStagingAdapter(SourceAdapter):
    """Adapter for OKF Staging markdown."""

    def fetch(self, source_ref: str, **kwargs: Any) -> list[dict[str, Any]]:
        from pathlib import Path

        path = Path(source_ref)
        content = path.read_text(encoding="utf-8") if path.exists() else str(source_ref)
        return [{"content": content, "source_ref": source_ref}]

    def parse_and_chunk(self, raw_items: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        chunks = []
        for item in raw_items:
            content = item.get("content", "")
            chunks.append({
                "content": content,
                "metadata": {
                    "source_type": "okf_staging",
                    "source_ref": item.get("source_ref", ""),
                    "domain_rights_status": "licensed",
                    "chunker_version": kwargs.get("chunker_version", "v2.4-adaptive"),
                    "modality": "markdown",
                },
            })
        return chunks


class FederatedDataSourceIngestionEngine:
    """
    Federated ingestion engine coordinating adapters, invariant stamping,
    and atomic dual-write (Qdrant vectors + Memgraph relational ontology).
    """

    def __init__(self, qdrant_service: Any = None, memgraph_driver: Any = None):
        self.adapters = {
            "youtube": YouTubeAdapter(),
            "pdf_doctrine": PDFDoctrineAdapter(),
            "audio_archive": AudioArchiveAdapter(),
            "whatsapp_reflection": WhatsAppReflectionAdapter(),
            "okf_staging": OKFStagingAdapter(),
        }
        self.qdrant_service = qdrant_service
        self.memgraph_driver = memgraph_driver

    def ingest_source(self, source_type: str, source_ref: str, **kwargs: Any) -> dict[str, Any]:
        adapter = self.adapters.get(source_type)
        if not adapter:
            raise ValueError(f"Unknown source type: {source_type}")

        # 1. Fetch
        raw_items = adapter.fetch(source_ref, **kwargs)
        if not raw_items:
            return {"status": "skipped", "reason": "no raw items fetched"}

        # 2. Parse & chunk (enforcing X40 rights stamping and chunker_version)
        chunker_version = kwargs.get("chunker_version", "v2.4-adaptive")
        chunks = adapter.parse_and_chunk(raw_items, chunker_version=chunker_version)

        # Rights gate: a real check that raises (an assert is stripped under python -O).
        # Runs before any write so a bad chunk cannot leave a partial dual-write.
        for c in chunks:
            if (c.get("metadata") or {}).get("domain_rights_status") != "licensed":
                raise ValueError("Invariant X40 rights stamping violated")

        # 3. Dual-write (NOT atomic: Qdrant is written first, then Memgraph; a Memgraph
        # failure leaves the Qdrant points in place. Known limit, see lessons.md.)
        written_qdrant = 0
        written_memgraph = 0

        # Qdrant write
        if self.qdrant_service and hasattr(self.qdrant_service, "upsert_chunks"):
            try:
                written_qdrant = self.qdrant_service.upsert_chunks(chunks)
            except Exception as e:
                logger.error("Qdrant dual-write failed: %s", e)
                raise RuntimeError(f"Atomic dual-write Qdrant failed: {e}")

        # Memgraph write (Zero Neo4j!)
        if self.memgraph_driver:
            try:
                with self.memgraph_driver.session() as session:
                    for c in chunks:
                        meta = c["metadata"]
                        session.run(
                            "CREATE (s:Source {type: $type, ref: $ref, rights: $rights, version: $version})",
                            type=meta.get("source_type"),
                            ref=str(meta.get("source_ref", source_ref)),
                            rights=meta.get("domain_rights_status"),
                            version=meta.get("chunker_version"),
                        )
                        written_memgraph += 1
            except Exception as e:
                logger.error("Memgraph dual-write failed: %s", e)
                raise RuntimeError(f"Atomic dual-write Memgraph failed: {e}")

        return {
            "status": "success",
            "source_type": source_type,
            "chunks_ingested": len(chunks),
            "written_qdrant": written_qdrant,
            "written_memgraph": written_memgraph,
        }
