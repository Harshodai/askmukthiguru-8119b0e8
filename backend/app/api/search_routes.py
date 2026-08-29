"""
Search & Source Inspection API Routes
Provides:
  - GET /api/search/inspect-source: In-situ full-text inspection, keyword matching, and timestamp extraction for cited sources
  - POST /api/search/web-discourse: Guarded spiritual web search across whitelisted domains
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from qdrant_client.http import models as qmodels

from app.dependencies import ServiceContainer, get_container
from app.sanitization import sanitize_log_input
from app.security_utils import is_benchmark_request
from services.auth_service import get_optional_user, resolve_anon_identity
from services.web_search_service import WebSearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["Search & Source Inspection"])


class WebSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Search query")
    max_results: int = Field(default=5, ge=1, le=10, description="Max results to return")


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from standard or short URLs."""
    if not url:
        return None
    parsed = urlparse(url)
    vid = None
    if parsed.hostname in ("www.youtube.com", "youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            vid = qs.get("v", [None])[0]
        elif parsed.path.startswith("/embed/"):
            vid = parsed.path.split("/embed/")[1].split("?")[0]
        elif parsed.path.startswith("/v/"):
            vid = parsed.path.split("/v/")[1].split("?")[0]
    elif parsed.hostname in ("youtu.be", "www.youtu.be"):
        vid = parsed.path.lstrip("/").split("?")[0]
    if vid and re.match(r"^[A-Za-z0-9_-]{1,64}$", vid):
        return vid
    return None


@router.get("/inspect-source")
async def inspect_source(
    request: Request,
    url: str = Query(..., min_length=3, max_length=1000, description="Canonical URL of the source to inspect"),
    query: Optional[str] = Query(None, max_length=200, description="Optional search term to highlight within source"),
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_optional_user),
) -> dict[str, Any]:
    """
    Retrieve indexed transcript chunks and full text for a given source URL,
    with keyword matching and timestamp metadata.
    """
    clean_url = url.strip()
    video_id = _extract_video_id(clean_url)
    
    # 1. Query Qdrant for all points with this source_url or video_id
    chunks = []
    source_title = clean_url
    
    try:
        qdrant_client = container.qdrant.get_client() if container.qdrant else None
        collection_name = container.qdrant.collection_name if container.qdrant else "spiritual_wisdom_contextual"
        
        if qdrant_client:
            # Match by source_url or video_id
            filter_conditions = [
                qmodels.FieldCondition(key="source_url", match=qmodels.MatchValue(value=clean_url))
            ]
            if video_id:
                filter_conditions.append(
                    qmodels.FieldCondition(key="video_id", match=qmodels.MatchValue(value=video_id))
                )
                filter_conditions.append(
                    qmodels.FieldCondition(
                        key="source_url", 
                        match=qmodels.MatchValue(value=f"https://www.youtube.com/watch?v={video_id}")
                    )
                )

            scroll_result, _ = qdrant_client.scroll(
                collection_name=collection_name,
                scroll_filter=qmodels.Filter(should=filter_conditions),
                limit=150,
                with_payload=True,
                with_vectors=False,
            )

            for point in scroll_result:
                payload = point.payload or {}
                chunk_text = payload.get("text") or payload.get("chunk_text") or ""
                title = payload.get("title") or payload.get("source_title")
                if title and source_title == clean_url:
                    source_title = title
                    
                chunks.append({
                    "id": str(point.id),
                    "chunk_index": payload.get("chunk_index", 0),
                    "start_time": payload.get("start_time", 0),
                    "end_time": payload.get("end_time", 0),
                    "text": chunk_text,
                    "speaker": payload.get("speaker", "Sri Krishnaji / Sri Preethaji"),
                    "raptor_level": payload.get("raptor_level", 0),
                })
    except Exception as exc:
        logger.warning(f"Failed to scroll Qdrant for source {sanitize_log_input(clean_url)}: {exc}")

    # Fallback to local projected transcript cache if Qdrant points not populated
    if not chunks and video_id and re.match(r"^[A-Za-z0-9_-]{1,64}$", video_id):
        candidate_bases = [
            Path("transcripts").resolve(),
            Path("/app/transcripts").resolve(),
            Path("../transcripts").resolve(),
            Path("scripts/ingestion/corpus").resolve(),
            Path("/app/scripts/ingestion/corpus").resolve(),
        ]
        candidate_paths = [
            Path("transcripts") / f"{video_id}.md",
            Path("/app/transcripts") / f"{video_id}.md",
            Path("../transcripts") / f"{video_id}.md",
            Path("scripts/ingestion/corpus") / video_id / "transcript.md",
            Path("/app/scripts/ingestion/corpus") / video_id / "transcript.md",
        ]
        for p in candidate_paths:
            try:
                resolved_p = p.resolve()
                if not any(
                    resolved_p.is_relative_to(base)
                    for base in candidate_bases
                    if base.exists()
                ):
                    continue
                if resolved_p.is_file():
                    with resolved_p.open("r", encoding="utf-8") as f:
                        raw_content = f.read()

                    title_match = re.search(r"^#\s+(.+)$", raw_content, re.MULTILINE)
                    if title_match:
                        source_title = title_match.group(1).strip()

                    speaker = "Sri Krishnaji / Sri Preethaji"
                    speaker_match = re.search(r"\*\*Speaker:\*\*\s*(.+)$", raw_content, re.MULTILINE)
                    if speaker_match:
                        speaker = speaker_match.group(1).strip()

                    transcript_body = raw_content
                    if "## Transcript" in raw_content:
                        transcript_body = raw_content.split("## Transcript", 1)[1].strip()

                    paragraphs = [para.strip() for para in transcript_body.split("\n\n") if para.strip()]
                    for i, para in enumerate(paragraphs):
                        chunks.append({
                            "id": f"{video_id}-{i}",
                            "chunk_index": i,
                            "start_time": i * 45,
                            "end_time": (i + 1) * 45,
                            "text": para,
                            "speaker": speaker,
                            "raptor_level": 0,
                        })
                    break
            except Exception as file_err:
                logger.warning(f"Error reading transcript file {sanitize_log_input(str(p))}: {file_err}")

    # Sort chunks by raptor_level asc, then chunk_index asc
    chunks.sort(key=lambda c: (c.get("raptor_level", 0), c.get("chunk_index", 0)))

    # Compute matches if query provided
    query_matches = []
    if query and query.strip():
        q_lower = query.strip().lower()
        for c in chunks:
            text = c["text"]
            if q_lower in text.lower():
                # Count occurrences
                count = len(re.findall(re.escape(q_lower), text, re.IGNORECASE))
                query_matches.append({
                    "chunk_id": c["id"],
                    "chunk_index": c["chunk_index"],
                    "start_time": c["start_time"],
                    "match_count": count,
                    "snippet": text[:300] + "..." if len(text) > 300 else text,
                })

    full_text = "\n\n".join(c["text"] for c in chunks if c.get("raptor_level", 0) == 0)
    if not full_text and chunks:
        full_text = "\n\n".join(c["text"] for c in chunks)

    return {
        "url": clean_url,
        "video_id": video_id,
        "title": source_title if source_title != clean_url else (f"Discourse: {video_id}" if video_id else clean_url),
        "total_chunks": len(chunks),
        "chunks": chunks,
        "full_text": full_text,
        "query": query,
        "matches": query_matches,
    }


@router.post("/web-discourse")
async def web_discourse_search(
    request: Request,
    body: WebSearchRequest,
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_optional_user),
) -> dict[str, Any]:
    """
    Search whitelisted spiritual discourses and external references using WebSearchService.
    """
    session_id = request.headers.get("X-Session-Id") or request.headers.get("X-Session-Token")
    user = resolve_anon_identity(user, session_id)
    uid = user.get("id") if user else "anonymous"

    service = getattr(container, "web_search", None) or WebSearchService()
    results = await service.search(body.query, user_id=uid)
    
    # Cap to max_results
    bounded_results = results[:body.max_results]

    return {
        "query": body.query,
        "count": len(bounded_results),
        "results": bounded_results,
    }
