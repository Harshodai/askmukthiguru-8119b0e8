"""Editorial Intelligence API endpoints (role-gated, human-approval enforced)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.admin import _require_admin
from app.config import settings
from app.dependencies import ServiceContainer, get_container_async
from domain.evidence_contract import EvidenceCandidate
from services.editorial.editorial_service import (
    EditorialApprovalError,
    EditorialIntelligenceService,
    LaneResults,
    ScriptBlock,
)
from services.editorial.editorial_store import EditorialStoreError, SupabaseEditorialStore
from services.evidence_adapters import (
    EvidenceFusionEngine,
    MemgraphEvidenceAdapter,
    OKFEvidenceAdapter,
    QdrantEvidenceAdapter,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/editorial", tags=["editorial"])

_EDITORIAL_SINGLETON: EditorialIntelligenceService | None = None


def _actor(user: dict) -> str:
    """Acting user comes from the authenticated request, never from the body."""
    return str(user.get("sub") or user.get("id") or user.get("email") or "")


def _lane_err(lane: str, exc: Exception) -> str:
    return f"{lane}: {type(exc).__name__}: {str(exc)[:200]}"


def get_editorial_service(container: ServiceContainer) -> EditorialIntelligenceService:
    global _EDITORIAL_SINGLETON
    if _EDITORIAL_SINGLETON is not None:
        return _EDITORIAL_SINGLETON

    def _guarded(name: str, lane_errors: list[str], fn: Callable[[], Any]) -> Any:
        """Run one retrieval lane; a failure is logged and surfaced in lane_errors, never hidden."""
        try:
            return fn()
        except Exception as exc:
            logger.warning("[EditorialAPI] %s lane failed: %s", name, exc, exc_info=True)
            lane_errors.append(_lane_err(name, exc))
            return None

    def _search_fn(topic: str, teacher_scope: str | None, limit: int) -> list[EvidenceCandidate]:
        ranked: dict[str, list[EvidenceCandidate]] = {}
        lane_errors: list[str] = []
        q_vec: list[float] = []
        embedding = getattr(container, "embedding", None)
        if embedding is not None:
            q_vec = (
                _guarded("embedding", lane_errors, lambda: list(embedding.encode([topic])[0])) or []
            )
        else:
            lane_errors.append("embedding: service unavailable")

        qdrant_client = getattr(container, "qdrant_client", None)
        if q_vec and qdrant_client is not None:
            col = settings.first_person_context_collection or settings.first_person_collection
            hits = _guarded(
                "qdrant",
                lane_errors,
                lambda: QdrantEvidenceAdapter(qdrant_client, col).search(
                    query_dense=q_vec,
                    teacher_id=teacher_scope,
                    limit=limit,
                    raise_on_error=True,
                ),
            )
            if hits is not None:
                ranked["qdrant"] = hits
        elif q_vec:
            lane_errors.append("qdrant: client unavailable")

        if getattr(container, "memgraph_driver", None):
            terms = [w for w in topic.split() if len(w) > 3][:5]
            hits = _guarded(
                "memgraph",
                lane_errors,
                lambda: MemgraphEvidenceAdapter(container.memgraph_driver).discover_by_concepts(
                    terms or [topic], limit=limit, teacher_id=teacher_scope, raise_on_error=True
                ),
            )
            if hits is not None:
                ranked["memgraph"] = hits
        else:
            lane_errors.append("memgraph: driver unavailable")

        if q_vec:
            hits = _guarded(
                "okf",
                lane_errors,
                lambda: OKFEvidenceAdapter().search(
                    query_dense=q_vec,
                    teacher_id=teacher_scope,
                    limit=min(5, limit),
                    raise_on_error=True,
                ),
            )
            if hits is not None:
                ranked["okf"] = hits

        return LaneResults(EvidenceFusionEngine().fuse(ranked, limit=limit), lane_errors)

    def _graph_fn(concepts: list[str]) -> list[dict[str, Any]]:
        if not getattr(container, "memgraph_driver", None):
            return []
        return MemgraphEvidenceAdapter(container.memgraph_driver).get_concept_neighborhood(concepts)

    def _ingestion_status_fn() -> dict[str, Any]:
        return {
            "collection": settings.first_person_context_collection
            or settings.first_person_collection,
            "books_indexed": False,
        }

    def _seeker_demand_fn() -> list[dict[str, Any]]:
        try:
            sink = getattr(container, "telemetry_sink", None)
            client = getattr(sink, "client", None) if sink else None
            if client is not None:
                resp = (
                    client.table("chat_queries")
                    .select("route,query_text")
                    .in_("route", ["first_person_abstain", "first_person_bridge"])
                    .limit(100)
                    .execute()
                )
                rows = list(getattr(resp, "data", None) or [])
                if rows:
                    topic_counts: dict[str, dict[str, Any]] = {}
                    for r in rows:
                        q = str(r.get("query_text") or "").strip()
                        if not q:
                            continue
                        key = " ".join(q.split()[:5])
                        bucket = topic_counts.setdefault(key, {"query_count": 0, "abstains": 0})
                        bucket["query_count"] += 1
                        if r.get("route") == "first_person_abstain":
                            bucket["abstains"] += 1
                    return [
                        {
                            "topic": t,
                            "query_count": v["query_count"],
                            "abstain_rate": v["abstains"] / max(1, v["query_count"]),
                        }
                        for t, v in sorted(
                            topic_counts.items(), key=lambda kv: kv[1]["query_count"], reverse=True
                        )
                    ][:10]
        except Exception as exc:
            logger.debug("[EditorialAPI] seeker demand unavailable: %s", exc)
        return []

    store = None
    if settings.editorial_persistence_enabled:
        sink = getattr(container, "telemetry_sink", None)
        store = SupabaseEditorialStore(getattr(sink, "client", None))

    _EDITORIAL_SINGLETON = EditorialIntelligenceService(
        store=store,
        search_fn=_search_fn,
        concept_graph_fn=_graph_fn,
        seeker_demand_fn=_seeker_demand_fn,
        ingestion_status_fn=_ingestion_status_fn,
        provenance_versions={
            "corpus_collection": settings.first_person_context_collection
            or settings.first_person_collection,
            "serving_posture": settings.first_person_serving_posture,
        },
    )
    return _EDITORIAL_SINGLETON


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    objective: str = Field(default="", max_length=1000)
    teacher_scope: str | None = None
    max_evidence: int = Field(default=20, ge=1, le=50)


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    topic: str = Field(min_length=2, max_length=300)
    objective: str = Field(default="", max_length=1000)
    target_format: str = Field(default="youtube_video")


class FactCheckRequest(BaseModel):
    blocks: list[ScriptBlock]
    evidence_pool: list[EvidenceCandidate]


class ScriptAttachRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    topic: str = Field(min_length=2, max_length=300)
    blocks: list[ScriptBlock]
    evidence_pool: list[EvidenceCandidate] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    notes: str = Field(default="", max_length=2000)


@router.post("/research")
async def create_research_dossier(
    body: ResearchRequest,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    dossier = await asyncio.to_thread(
        svc.generate_dossier,
        topic=body.topic,
        objective=body.objective,
        teacher_scope=body.teacher_scope,
        max_evidence=body.max_evidence,
    )
    return dossier.model_dump(mode="json")


@router.post("/opportunities")
async def discover_content_opportunities(
    limit: int = 10,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    opps = await asyncio.to_thread(svc.discover_opportunities, limit=max(1, min(limit, 30)))
    return {"opportunities": [o.model_dump(mode="json") for o in opps]}


@router.post("/fact-check")
async def fact_check_script(
    body: FactCheckRequest,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    # SECURITY NOTE (not fixed yet): the evidence pool is client-supplied, so retrieval_source and
    # speaker_verified are client-asserted. An admin could fake an exact quote. Verification must
    # move to server-held dossier evidence; until then responses carry evidence_pool_trust.
    svc = get_editorial_service(container)
    report = svc.fact_check_blocks(body.blocks, body.evidence_pool)
    return {**report.model_dump(mode="json"), "evidence_pool_trust": "client_supplied"}


@router.get("/projects")
async def list_editorial_projects(
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    return {"projects": [p.model_dump(mode="json") for p in svc.list_projects()]}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_editorial_project(
    body: ProjectCreateRequest,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    proj = svc.create_project(
        title=body.title,
        topic=body.topic,
        objective=body.objective,
        target_format=body.target_format,
        author_id=_actor(_admin),
    )
    return proj.model_dump(mode="json")


@router.get("/projects/{project_id}")
async def get_editorial_project(
    project_id: str,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    proj = svc.get_project(project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Editorial project not found")
    return proj.model_dump(mode="json")


@router.post("/projects/{project_id}/script")
async def attach_editorial_script(
    project_id: str,
    body: ScriptAttachRequest,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    proj = svc.get_project(project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Editorial project not found")
    # SECURITY NOTE (not fixed yet): the evidence pool is client-supplied, so retrieval_source and
    # speaker_verified are client-asserted. An admin could fake an exact quote. Verification must
    # move to server-held dossier evidence; until then responses carry evidence_pool_trust.
    client_supplied = bool(body.evidence_pool)
    pool = body.evidence_pool or (proj.dossier.evidence_items if proj.dossier else [])
    script = svc.build_verified_script(
        title=body.title,
        topic=body.topic,
        blocks=body.blocks,
        evidence_pool=pool,
    )
    updated = svc.attach_script(project_id, script, actor_id=_actor(_admin))
    out = updated.model_dump(mode="json")
    out["evidence_pool_trust"] = "client_supplied" if client_supplied else "server"
    return out


@router.post("/projects/{project_id}/dossier")
async def build_and_attach_dossier(
    project_id: str,
    body: ResearchRequest,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    if svc.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Editorial project not found")
    dossier = await asyncio.to_thread(
        svc.generate_dossier,
        topic=body.topic,
        objective=body.objective,
        teacher_scope=body.teacher_scope,
        max_evidence=body.max_evidence,
    )
    return svc.attach_dossier(project_id, dossier, actor_id=_actor(_admin)).model_dump(mode="json")


@router.post("/projects/{project_id}/brief")
async def build_and_attach_brief(
    project_id: str,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    proj = svc.get_project(project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Editorial project not found")
    dossier = proj.dossier or await asyncio.to_thread(
        svc.generate_dossier, topic=proj.topic, objective=proj.objective, max_evidence=15
    )
    brief = svc.generate_brief(dossier=dossier, target_format=proj.target_format)
    return svc.attach_brief(project_id, brief, actor_id=_actor(_admin)).model_dump(mode="json")


@router.post("/projects/{project_id}/outline")
async def build_and_attach_outline(
    project_id: str,
    _admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    proj = svc.get_project(project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Editorial project not found")
    dossier = proj.dossier or await asyncio.to_thread(
        svc.generate_dossier, topic=proj.topic, objective=proj.objective, max_evidence=15
    )
    outline = svc.generate_outline(title=proj.title, dossier=dossier, brief=proj.brief)
    return svc.attach_outline(project_id, outline, actor_id=_actor(_admin)).model_dump(mode="json")


@router.post("/projects/{project_id}/approve")
async def approve_editorial_project(
    project_id: str,
    body: ApprovalRequest,
    admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    reviewer = _actor(admin)
    try:
        updated = svc.approve_project(project_id, reviewer_id=reviewer, notes=body.notes)
        return updated.model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EditorialApprovalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EditorialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/projects/{project_id}/publish")
async def publish_editorial_project(
    project_id: str,
    admin: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container_async),
) -> dict[str, Any]:
    svc = get_editorial_service(container)
    publisher = str(admin.get("sub") or admin.get("id") or admin.get("email") or "admin")
    try:
        updated = svc.publish_project(project_id, publisher_id=publisher)
        return updated.model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EditorialApprovalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
