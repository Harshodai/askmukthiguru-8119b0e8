"""Book (PDF/PageIndex-JSON) ingestion -- Qdrant + LightRAG + OKF, Railway-native.

Runs inside the deployed celery-worker (internal-network access to Neo4j/Qdrant),
unlike scripts/ingestion/bulk_ingest_async.py's ingest_book_to_qdrant which is a
host-side, Qdrant-only script for ad-hoc runs against the public Qdrant proxy.
Both flatten the same PageIndex tree shape; kept separate rather than shared
because they run in different execution contexts (host script vs. deployed
worker) and evolve independently -- see book_ingest_task in tasks/ingest_tasks.py
for the Celery entrypoint that calls this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BOOK_SOURCE_NAME = "The_Four_Sacred_Secrets.pdf"
LIGHTRAG_CHUNK_SIZE = 1500


def flatten_book_structure(structure: list[dict]) -> list[dict]:
    """Flatten a PageIndex chapter tree into (text, metadata) chunks.

    Uses the same boundary-aware chunker + contextual headers as the standard
    ingestion pipeline (ingest/pipeline.py, use_boundary_chunker) instead of
    the legacy RecursiveCharacterTextSplitter -- sentence/verse-boundary-aware,
    not a raw character-count cut mid-sentence.

    Dedupes globally by content hash: PageIndex sometimes repeats a
    subsection's full text inside its parent section's text field
    (2026-08-15 audit: 236/1196 chunks, 19.7%, were exact parent/child
    duplicates). Every chunk carries source_type/language/tags so it is
    visible to every optional Qdrant search filter, not just the ones that
    happen to be unset for a given query.

    Deliberately stays CLS-pooled (plain EmbeddingService.encode_batch, not
    encode_late_chunked) to match every video that lands in the same
    collection via the standard pipeline -- see ingest_book()'s docstring for
    why mixing pooling modes within one collection is a correctness bug, not
    an upgrade.
    """
    from ingest.boundary_chunker import chunk_with_contextual_headers

    seen_hashes: set[str] = set()
    chunks: list[dict] = []

    def _dedup_append(text: str, header: str, metadata: dict) -> None:
        body_hash = hashlib.md5(text.strip().encode()).hexdigest()
        if body_hash in seen_hashes:
            return
        seen_hashes.add(body_hash)
        chunks.append({"text": header + text, "metadata": metadata})

    def _walk(nodes: list[dict], parent_title: str = "", cluster_id: int = 1) -> None:
        for node in nodes:
            title = node.get("title", "")
            context_title = f"{parent_title} > {title}" if parent_title and title else (title or parent_title)
            text = (node.get("text") or "").strip()
            summary = (node.get("summary") or "").strip()

            if text:
                import unicodedata
                text = unicodedata.normalize("NFC", text)
                try:
                    from services.doctrine_terms import apply_corrections
                    text = apply_corrections(text)
                except Exception:
                    pass

                parent_id = str(uuid.uuid4())
                header = f"[Source: {BOOK_SOURCE_NAME} | Chapter: {context_title}]\n"
                boundary_chunks = chunk_with_contextual_headers(
                    text, title=BOOK_SOURCE_NAME, speaker="Sri Preethaji & Sri Krishnaji", topic="Spiritual",
                )
                for full_chunk in boundary_chunks:
                    # chunk_with_contextual_headers already prepends its own
                    # "[Source: ... | Speaker: ... ]" header; strip it so we
                    # control the header format ourselves (chapter title, not
                    # book title, is the useful context here) without double
                    # headers stacking on every chunk.
                    child_text = full_chunk.split("]\n", 1)[-1] if full_chunk.startswith("[") else full_chunk
                    _dedup_append(
                        child_text,
                        header,
                        {
                            "source_url": BOOK_SOURCE_NAME,
                            "title": context_title,
                            "speaker": "Sri Preethaji & Sri Krishnaji",
                            "topic": "Spiritual",
                            "content_type": "book",
                            "source_type": "book",
                            "language": "en",
                            "tags": ["general"],
                            "raptor_level": 0,
                            "cluster_id": cluster_id,
                            "node_id": node.get("node_id", ""),
                            "page_range": f"{node.get('start_index', '?')}-{node.get('end_index', '?')}",
                            "parent_id": parent_id,
                            "parent_text": text,
                            "is_child": True,
                        },
                    )

            if summary:
                import unicodedata
                summary = unicodedata.normalize("NFC", summary)
                try:
                    from services.doctrine_terms import apply_corrections
                    summary = apply_corrections(summary)
                except Exception:
                    pass

                header = f"[Source: {BOOK_SOURCE_NAME} | Chapter Summary: {context_title}]\n"
                _dedup_append(
                    summary,
                    header,
                    {
                        "source_url": BOOK_SOURCE_NAME,
                        "title": f"Summary: {context_title}",
                        "speaker": "Sri Preethaji & Sri Krishnaji",
                        "topic": "Spiritual",
                        "content_type": "summary",
                        "source_type": "book",
                        "language": "en",
                        "tags": ["general"],
                        "raptor_level": 1,
                        "cluster_id": cluster_id,
                        "node_id": node.get("node_id", ""),
                    },
                )

            if node.get("nodes"):
                _walk(node["nodes"], parent_title=context_title, cluster_id=cluster_id)
            cluster_id += 1

    _walk(structure)
    for i, chunk in enumerate(chunks):
        chunk["metadata"]["chunk_index"] = i
    return chunks


def _full_text(structure: list[dict]) -> str:
    parts: list[str] = []
    for node in structure:
        parts.append(node.get("text", ""))
        parts.append(node.get("summary", ""))
        if node.get("nodes"):
            parts.append(_full_text(node["nodes"]))
    full = "\n".join(p for p in parts if p)
    import unicodedata
    full = unicodedata.normalize("NFC", full)
    try:
        from services.doctrine_terms import apply_corrections
        return apply_corrections(full)
    except Exception:
        return full


def _chunk_text(text: str, size: int = LIGHTRAG_CHUNK_SIZE) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [text]


async def ingest_book(json_path: str, collection: str) -> dict[str, Any]:
    """Ingest the book into Qdrant (given collection) + LightRAG, then queue OKF.

    Returns a summary dict: {chunks_indexed, lightrag_chunks_ok, lightrag_chunks_failed}.
    """
    from app.dependencies import get_container
    from services.embedding_service import EmbeddingService
    from services.qdrant_service import QdrantService

    path = Path(json_path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    structure = data.get("structure", [])
    if not structure:
        raise ValueError(f"No 'structure' array in {json_path}")

    chunks = flatten_book_structure(structure)
    logger.info("book_ingest: flattened %d deduped chunks from %s", len(chunks), json_path)

    qdrant = QdrantService(collection=collection)
    qdrant.init_collection()
    embeddings = EmbeddingService()

    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["text"] for c in batch]
        metadatas = [c["metadata"] for c in batch]
        encoded = embeddings.encode_batch(texts)
        qdrant.upsert_chunks(
            texts=texts, vectors=encoded["dense"], metadatas=metadatas,
            sparse_vectors=encoded["sparse"],
        )
    logger.info("book_ingest: %d chunks upserted to %s", len(chunks), collection)

    container = get_container()
    lightrag_ok, lightrag_failed = 0, 0
    if container.lightrag:
        try:
            await container.lightrag.initialize()
        except Exception as e:
            logger.warning("book_ingest: LightRAG init degraded: %s", e)

        full_text = _full_text(structure)
        for i, piece in enumerate(_chunk_text(full_text)):
            try:
                await container.lightrag.ainsert(
                    f"[Source: {BOOK_SOURCE_NAME}]\n{piece}",
                    file_paths=[BOOK_SOURCE_NAME], timeout=180.0,
                )
                lightrag_ok += 1
            except Exception as e:
                lightrag_failed += 1
                logger.error("book_ingest: LightRAG chunk %d failed: %s", i, e)
    else:
        logger.info("book_ingest: LightRAG service inactive, skipping graph extraction")

    okf_status = "skipped"
    try:
        from scripts.extract_okf_from_stores import extract_okf
        await extract_okf(target_video_id=BOOK_SOURCE_NAME, auto_approve=False)
        okf_status = "queued_for_review"
    except Exception as e:
        okf_status = "failed"
        logger.warning("book_ingest: OKF extraction failed (non-fatal): %s", e)

    return {
        "chunks_indexed": len(chunks),
        "lightrag_chunks_ok": lightrag_ok,
        "lightrag_chunks_failed": lightrag_failed,
        "okf_status": okf_status,
    }


if __name__ == "__main__":
    import sys

    sample_structure = [
        {
            "node_id": "1",
            "title": "Chapter A",
            "text": "This is the parent chapter body text repeated below.",
            "nodes": [
                {
                    "node_id": "1.1",
                    "title": "Subsection",
                    # Deliberately duplicates the parent's text to exercise dedup.
                    "text": "This is the parent chapter body text repeated below.",
                }
            ],
        }
    ]
    result = flatten_book_structure(sample_structure)
    body_texts = [c["text"].split("]\n", 1)[-1] for c in result]
    assert len(body_texts) == len(set(body_texts)), "dedup failed: duplicate body text survived"
    for c in result:
        assert c["metadata"]["source_type"] == "book"
        assert c["metadata"]["language"] == "en"
        assert c["metadata"]["tags"] == ["general"]
    print(f"book_ingest self-check OK -- {len(result)} chunk(s), no duplicates, full metadata")
    sys.exit(0)
