"""
Admin dashboard API routes.

Unit 13 — moved from `routers/admin.py` into `app.api`.
"""

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.admin_telemetry import operations_snapshot, trace_detail, trace_summary
from app.config import settings
from app.dependencies import ServiceContainer, get_container
from app.telemetry_db import (
    get_admins,
    get_alert_events,
    get_alert_rules,
    get_annotations,
    get_available_models,
    get_dead_docs,
    get_empty_retrievals,
    get_eval_runs,
    get_golden_questions,
    get_ingestion_health,
    get_ingestion_runs,
    get_kpis,
    get_live_feed,
    get_model_pricing,
    get_node_latencies,
    get_prompt_metrics_by_version,
    get_quality_data,
    get_query_trace,
    get_ragas_heatmap,
    get_recent_traces,
    get_retrieval_health,
    get_safety_events,
    get_similarity_trend,
    get_timeseries_data,
    get_top_failures,
    get_topic_clusters,
    get_trigger_events,
    get_trigger_trend,
)
from celery_config import celery_app
from schemas.feedback import FeedbackResponse
from services.auth_service import require_aal2
from services.feedback_service import FeedbackService


class _AdminActionResult(BaseModel):
    ok: bool = True
    message: Optional[str] = None


def _require_admin(user: dict = Depends(require_aal2)) -> dict:
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    # P1-SEC-1 (T4): defense-in-depth admin allowlist. When ADMIN_USER_IDS is
    # set, an AAL2 superuser MUST also be in the list. Empty = not enforced.
    allowlist = settings.admin_user_ids_list
    if allowlist and user.get("id") not in allowlist:
        raise HTTPException(status_code=403, detail="Admin access required (not allowlisted)")
    return user


logger = logging.getLogger(__name__)

admin_router = APIRouter(tags=["admin"])


@admin_router.get("/traces")
async def fetch_telemetry_traces(
    limit: int = 50,
    search: Optional[str] = None,
    prompt_version_id: Optional[str] = None,
    model: Optional[str] = None,
    min_judge_score: Optional[float] = Query(None, ge=0.0, le=1.0),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Fetch recent traces for Admin UI. Requires admin authentication."""
    traces = await get_recent_traces(
        min(limit, 200),
        search=search,
        prompt_version_id=prompt_version_id,
        model=model,
        min_judge_score=min_judge_score,
    )
    return [trace_summary(trace) for trace in traces]


@admin_router.get("/traces/{trace_id}")
async def fetch_query_trace(
    trace_id: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Fetch a single detailed trace by query ID. Requires admin authentication."""
    trace = await get_query_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return trace_detail(trace)


@admin_router.get("/operations/snapshot")
async def get_operations_snapshot(
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Return bounded aggregate evidence for the privacy-safe operations view."""
    traces = await get_recent_traces(200)
    return operations_snapshot(
        traces,
        model_policy_id=settings.openrouter_policy_id,
        budget_guard_enabled=settings.openrouter_budget_guard_enabled,
        release_readiness=_source_release_readiness(),
    )


@admin_router.get("/prompts")
async def fetch_prompts(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        return []
    try:
        res = client.table("prompt_versions").select("*").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to fetch prompts: {e}")
        return []


@admin_router.get("/feedback", response_model=list[FeedbackResponse])
async def fetch_admin_feedback(
    limit: int = 100,
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Fetch real seeker feedback (feedback_events table) for the admin dashboard."""
    service = FeedbackService()
    return await service.get_feedback_history(limit=min(limit, 200))


class DoctrineTermUpdate(BaseModel):
    canonical: str = Field(..., min_length=1)
    variants: list[str] = Field(default_factory=list)
    enabled: bool = True


@admin_router.get("/doctrine-terms")
async def fetch_doctrine_terms(
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Effective doctrine-term correction map (code defaults + admin overrides)."""
    from services.doctrine_terms import load_doctrine_terms

    return {"terms": load_doctrine_terms()}


@admin_router.post("/doctrine-terms")
async def upsert_doctrine_term(
    body: DoctrineTermUpdate,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Add/update a canonical term + its mis-transcription variants. Applies without a restart —
    the whisper bias, ingest corrector and output cleanup all read the shared source of truth."""
    from app.telemetry_db import _get_client
    from services.doctrine_terms import reload as reload_doctrine_terms

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        await (
            client.table("doctrine_terms")
            .upsert(
                {
                    "canonical": body.canonical.strip(),
                    "variants": body.variants,
                    "enabled": body.enabled,
                    "updated_by": user.get("email") or user.get("id"),
                },
                on_conflict="canonical",
            )
            .execute()
        )
    except Exception as e:
        logger.error(f"Failed to upsert doctrine term: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to save doctrine term. Please try again."
        )
    reload_doctrine_terms()  # hot-reload the correction map (no restart needed)
    return {"ok": True, "canonical": body.canonical.strip()}


@admin_router.get("/rag-flow-graph")
async def get_rag_flow_graph(
    strategy: str = "standard",
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """
    Expose the active RAG graph strategy nodes and edges, merged with average timing latencies.
    Requires admin authentication.
    """

    try:
        container = get_container()

        # Choose the correct graph based on strategy param
        graph_obj = container.standard_graph
        if strategy == "fast":
            graph_obj = container.fast_graph
        elif strategy == "deep":
            graph_obj = container.deep_graph

        compiled_graph = graph_obj.get_graph()

        # 1. Fetch latency averages from Supabase (last 1000 spans)
        latencies = await get_node_latencies(limit=1000)
        latency_map = {item["node"]: item for item in latencies}

        # 2. Extract nodes
        nodes = []
        for key, node in compiled_graph.nodes.items():
            avg_metrics = latency_map.get(key, {"avg_latency_ms": 0.0, "count": 0})
            nodes.append(
                {
                    "id": key,
                    "label": getattr(node, "name", key) or key,
                    "avg_latency_ms": avg_metrics["avg_latency_ms"],
                    "invocation_count": avg_metrics["count"],
                }
            )

        # 3. Extract edges
        edges = []
        for edge in compiled_graph.edges:
            edges.append(
                {
                    "id": f"e-{edge.source}-{edge.target}",
                    "source": edge.source,
                    "target": edge.target,
                    "animated": True,
                }
            )

        return {
            "strategy": strategy,
            "nodes": nodes,
            "edges": edges,
        }
    except Exception as e:
        logger.error(f"Failed to extract RAG flow graph: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate graph. Please try again.")


@admin_router.get("/evaluations")
async def fetch_evaluations(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    return await get_eval_runs()


@admin_router.get("/kpis")
async def fetch_kpis(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Fetch aggregated KPIs for Admin UI. Requires admin authentication."""

    return await get_kpis(from_date, to_date)


@admin_router.get("/models")
async def list_models(
    user: dict = Depends(_require_admin),
) -> list[str]:
    """List available LLM models. Requires admin authentication."""
    return await get_available_models()


@admin_router.get("/timeseries")
async def get_timeseries(
    metric: str,
    from_date: str,
    to_date: str,
    buckets: int = 24,
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Get timeseries data for a metric. Requires admin authentication."""
    return await get_timeseries_data(metric, from_date, to_date, buckets)


@admin_router.get("/triggers")
async def list_triggers(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List trigger events. Requires admin authentication."""
    return await get_trigger_events(from_date, to_date)


@admin_router.get("/safety-events")
async def list_safety_events(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List safety events. Requires admin authentication."""
    return await get_safety_events(from_date, to_date)


@admin_router.get("/topic-clusters")
async def list_topic_clusters(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List topic clusters. Requires admin authentication."""
    return await get_topic_clusters()


@admin_router.get("/retrieval-health")
async def get_retrieval_health_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Get retrieval health metrics. Requires admin authentication."""
    return await get_retrieval_health(from_date, to_date)


@admin_router.get("/data-stores")
async def get_data_stores_endpoint(
    user: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    """Get data quality stats for Qdrant, Neo4j, and LightRAG. Admin only."""

    result: dict[str, Any] = {
        "qdrant": {},
        "neo4j": {},
        "lightrag": {},
    }

    # ── Qdrant ──────────────────────────────────────────────────────────
    try:
        result["qdrant"] = await asyncio.to_thread(container.qdrant.get_stats)
    except Exception as e:
        result["qdrant"]["error"] = str(e)
        logger.warning(f"Failed to query Qdrant: {e}")

    # ── Neo4j ───────────────────────────────────────────────────────────
    try:
        driver = container.neo4j_driver
        if driver:

            def _query_neo4j():
                with driver.session(database="neo4j", default_access_mode="READ") as session:
                    node_rows = session.run(
                        "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS cnt ORDER BY cnt DESC"
                    ).data()
                    rel_rows = session.run(
                        "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS cnt ORDER BY cnt DESC"
                    ).data()
                    total = session.run("MATCH (n) RETURN count(n) AS cnt").single()
                    return node_rows, rel_rows, total["cnt"] if total else 0

            node_rows, rel_rows, total_nodes = await asyncio.to_thread(_query_neo4j)
            result["neo4j"]["nodes_by_label"] = {}
            for r in node_rows:
                label = r["label"]
                result["neo4j"]["nodes_by_label"][label] = (
                    result["neo4j"]["nodes_by_label"].get(label, 0) + r["cnt"]
                )
            result["neo4j"]["total_nodes"] = total_nodes
            result["neo4j"]["relationships_by_type"] = {r["type"]: r["cnt"] for r in rel_rows}
            result["neo4j"]["total_relationships"] = sum(r["cnt"] for r in rel_rows)
        else:
            result["neo4j"]["error"] = "Neo4j driver not available"
    except Exception as e:
        result["neo4j"]["error"] = str(e)
        logger.warning(f"Failed to query Neo4j: {e}")

    # ── LightRAG ────────────────────────────────────────────────────────
    try:
        lr = container.lightrag
        result["lightrag"]["initialized"] = lr._initialized
        if lr._initialized and lr.rag:
            result["lightrag"]["embedding_dim"] = getattr(lr.rag, "embedding_dim", None)
            result["lightrag"]["max_embed_tokens"] = getattr(lr.rag, "max_embed_tokens", None)
            result["lightrag"]["chunk_token_size"] = getattr(lr.rag, "chunk_token_size", None)
            result["lightrag"]["cache_size"] = len(lr._query_cache)
    except Exception as e:
        result["lightrag"]["error"] = str(e)
        logger.warning(f"Failed to query LightRAG: {e}")

    return result


@admin_router.get("/quality-data")
async def get_quality_data_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Get quality data metrics. Requires admin authentication."""
    return await get_quality_data(from_date, to_date)


@admin_router.get("/eval-runs")
async def list_eval_runs(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List evaluation runs. Requires admin authentication."""
    return await get_eval_runs()


@admin_router.get("/golden-questions")
async def list_golden_questions(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List golden questions. Requires admin authentication."""
    return await get_golden_questions()


class GoldenQuestionUpsert(BaseModel):
    id: Optional[str] = None
    question: str = Field(..., min_length=1)
    expected_answer: Optional[str] = None
    expected_sources: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    active: bool = Field(default=True)


@admin_router.post("/golden-questions")
async def upsert_golden_question(
    body: GoldenQuestionUpsert,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Create or update a golden question. Requires admin authentication + AAL2."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        payload = {
            "question": body.question.strip(),
            "expected_answer": body.expected_answer,
            "expected_sources": body.expected_sources,
            "tags": body.tags,
            "active": body.active,
        }
        if body.id:
            client.table("golden_questions").update(payload).eq("id", body.id).execute()
            return {"ok": True, "id": body.id, "message": "Golden question updated"}
        else:
            result = client.table("golden_questions").insert(payload).execute()
            new_id = (getattr(result, "data", None) or [{}])[0].get("id")
            return {"ok": True, "id": new_id, "message": "Golden question created"}
    except Exception as e:
        logger.error(f"Failed to upsert golden question: {e}")
        raise HTTPException(status_code=500, detail="Failed to save golden question")


@admin_router.delete("/golden-questions/{question_id}")
async def delete_golden_question(
    question_id: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Delete a golden question. Requires admin authentication + AAL2."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        client.table("golden_questions").delete().eq("id", question_id).execute()
        return {"ok": True, "message": "Golden question deleted", "id": question_id}
    except Exception as e:
        logger.error(f"Failed to delete golden question: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete golden question")


@admin_router.get("/ingestion-runs")
async def list_ingestion_runs(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List ingestion runs. Requires admin authentication."""
    return await get_ingestion_runs()


@admin_router.get("/alert-rules")
async def list_alert_rules(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List alert rules. Requires admin authentication."""
    return await get_alert_rules()


class AlertRuleUpsert(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    comparator: str = Field(..., pattern=r"^(>|>=|<|<=)$")
    threshold: float
    window_minutes: int = Field(default=15, ge=1)
    channel: str = Field(default="email")
    target: str = Field(default="")
    active: bool = Field(default=True)


@admin_router.post("/alert-rules")
async def upsert_alert_rule(
    body: AlertRuleUpsert,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Create or update an alert rule. Requires admin authentication + AAL2."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        payload = {
            "name": body.name.strip(),
            "metric": body.metric,
            "comparator": body.comparator,
            "threshold": body.threshold,
            "window_minutes": body.window_minutes,
            "channel": body.channel,
            "target": body.target,
            "active": body.active,
        }
        if body.id:
            client.table("alert_rules").update(payload).eq("id", body.id).execute()
            return {"ok": True, "id": body.id, "message": "Alert rule updated"}
        else:
            result = client.table("alert_rules").insert(payload).execute()
            new_id = (getattr(result, "data", None) or [{}])[0].get("id")
            return {"ok": True, "id": new_id, "message": "Alert rule created"}
    except Exception as e:
        logger.error(f"Failed to upsert alert rule: {e}")
        raise HTTPException(status_code=500, detail="Failed to save alert rule")


@admin_router.delete("/alert-rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Delete an alert rule. Requires admin authentication + AAL2."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        client.table("alert_rules").delete().eq("id", rule_id).execute()
        return {"ok": True, "message": "Alert rule deleted", "id": rule_id}
    except Exception as e:
        logger.error(f"Failed to delete alert rule: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete alert rule")


@admin_router.get("/alert-events")
async def list_alert_events(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List alert events. Requires admin authentication."""
    return await get_alert_events()


@admin_router.get("/annotations")
async def list_annotations(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List annotations. Requires admin authentication."""
    return await get_annotations()


@admin_router.get("/admins")
async def list_admins(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List admin users. Requires admin authentication."""
    return await get_admins()


class PromoteAdminRequest(BaseModel):
    email: str = Field(..., min_length=1)


@admin_router.post("/admins/promote")
async def promote_admin(
    body: PromoteAdminRequest,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Promote a user to admin by email. Requires admin authentication + AAL2."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        auth_resp = (
            client.table("auth_users")
            .select("id")
            .eq("email", body.email.strip().lower())
            .limit(1)
            .execute()
        )
        auth_rows = getattr(auth_resp, "data", None) or []
        if not auth_rows:
            raise HTTPException(status_code=404, detail="User not found")
        target_user_id = auth_rows[0]["id"]

        existing = (
            client.table("user_roles")
            .select("id")
            .eq("user_id", target_user_id)
            .eq("role", "admin")
            .limit(1)
            .execute()
        )
        if getattr(existing, "data", None):
            return {"ok": True, "message": "User is already an admin", "user_id": target_user_id}

        client.table("user_roles").insert({"user_id": target_user_id, "role": "admin"}).execute()
        return {"ok": True, "message": "User promoted to admin", "user_id": target_user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to promote admin: {e}")
        raise HTTPException(status_code=500, detail="Failed to promote admin")


class DemoteAdminRequest(BaseModel):
    user_id: str = Field(..., min_length=1)


@admin_router.post("/admins/demote")
async def demote_admin(
    body: DemoteAdminRequest,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Revoke admin role from a user. Requires admin authentication + AAL2."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        result = (
            client.table("user_roles")
            .delete()
            .eq("user_id", body.user_id)
            .eq("role", "admin")
            .execute()
        )
        return {
            "ok": True,
            "message": "Admin role revoked",
            "user_id": body.user_id,
            "deleted": bool(getattr(result, "data", None)),
        }
    except Exception as e:
        logger.error(f"Failed to demote admin: {e}")
        raise HTTPException(status_code=500, detail="Failed to demote admin")


@admin_router.get("/model-pricing")
async def list_model_pricing(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List model pricing. Requires admin authentication."""
    return await get_model_pricing()


@admin_router.get("/top-failures")
async def get_top_failures_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(8, ge=1, le=100),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Get top failures by faithfulness. Requires admin authentication."""
    return await get_top_failures(from_date, to_date, limit)


@admin_router.get("/ragas-heatmap")
async def get_ragas_heatmap_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(8, ge=1, le=100),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Get RAGAS heatmap data. Requires admin authentication."""
    return await get_ragas_heatmap(from_date, to_date, buckets)


@admin_router.get("/trigger-trend")
async def get_trigger_trend_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(14, ge=1, le=100),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Get trigger trend data. Requires admin authentication."""
    return await get_trigger_trend(from_date, to_date, buckets)


@admin_router.get("/similarity-trend")
async def get_similarity_trend_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(14, ge=1, le=100),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Get similarity trend data. Requires admin authentication."""
    return await get_similarity_trend(from_date, to_date, buckets)


@admin_router.get("/dead-docs")
async def get_dead_docs_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Get dead documents. Requires admin authentication."""
    return await get_dead_docs(from_date, to_date)


@admin_router.get("/empty-retrievals")
async def get_empty_retrievals_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Get empty retrievals. Requires admin authentication."""
    return await get_empty_retrievals(from_date, to_date, limit)


@admin_router.get("/ingestion-health")
async def get_ingestion_health_endpoint(
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Get ingestion health status. Requires admin authentication."""
    return await get_ingestion_health()


@admin_router.get("/prompt-metrics")
async def get_prompt_metrics_by_version_endpoint(
    user: dict = Depends(_require_admin),
) -> Any:
    """Get prompt metrics by version. Requires admin authentication."""
    return await get_prompt_metrics_by_version()


@admin_router.post("/prompts/{prompt_id}/activate")
async def activate_prompt_version(
    prompt_id: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Activate a single prompt version and deactivate all others with the same name.

    Requires admin authentication + AAL2.
    """
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        # Deactivate every version in the same prompt family as the target.
        target_rows = (
            client.table("prompt_versions")
            .select("name")
            .eq("id", prompt_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not target_rows:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        prompt_name = target_rows[0]["name"]
        client.table("prompt_versions").update({"active": False}).eq("name", prompt_name).execute()
        client.table("prompt_versions").update({"active": True}).eq("id", prompt_id).execute()
        return {"ok": True, "message": "Prompt version activated", "id": prompt_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate prompt version: {e}")
        raise HTTPException(status_code=500, detail="Failed to activate prompt version")


@admin_router.get("/live-feed")
async def poll_live_feed_endpoint(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Poll live feed. Requires admin authentication."""
    return await get_live_feed()


class AskRequest(BaseModel):
    question: str
    kpi_context: str = ""


@admin_router.post("/ask")
async def ask_admin_question(
    req: AskRequest,
    user: dict = Depends(_require_admin),
):

    container = get_container()
    llm_service = container.ollama

    # Fetch rich context dynamically to support complex queries.
    # Note: get_kpis/get_node_latencies are already imported at module top.
    # get_cost_tracker is intentionally lazy-loaded to avoid circular imports.
    from services.cost_tracker import get_cost_tracker

    dynamic_context = []

    try:
        now_dt = datetime.now(UTC)
        from_date = (now_dt - timedelta(days=30)).isoformat()
        to_date = now_dt.isoformat()

        kpis_30d = await get_kpis(from_date=from_date, to_date=to_date)
        node_latencies = await get_node_latencies(limit=100)

        tracker = get_cost_tracker()
        cost_report = tracker.get_usage_report(days=30)

        dynamic_context.append("--- Detailed Telemetry & Analytics (Last 30 Days) ---")
        dynamic_context.append("Overall KPIs:")
        for k, v in (kpis_30d or {}).items():
            dynamic_context.append(f"  {k}: {v}")

        dynamic_context.append("\nCost & Token Metrics:")
        dynamic_context.append(f"  Total Cost USD: ${cost_report.total_cost_usd:.6f}")
        dynamic_context.append(
            f"  Total Tokens: {cost_report.total_tokens} (Prompt/In: {cost_report.total_tokens_in}, Completion/Out: {cost_report.total_tokens_out})"
        )
        dynamic_context.append(f"  Unique Users: {cost_report.unique_users}")
        dynamic_context.append(f"  Unique Sessions: {cost_report.unique_sessions}")

        if cost_report.by_model:
            dynamic_context.append("  Usage by Model:")
            for m, details in cost_report.by_model.items():
                dynamic_context.append(f"    - {m}: {details}")

        if cost_report.by_provider:
            dynamic_context.append("  Usage by Provider:")
            for prov, details in cost_report.by_provider.items():
                dynamic_context.append(f"    - {prov}: {details}")

        if node_latencies:
            dynamic_context.append("\nAverage Node/Span Latencies:")
            for nl in node_latencies:
                dynamic_context.append(
                    f"  - {nl.get('name')}: {nl.get('avg_duration_ms', 0):.2f}ms (count: {nl.get('count', 0)})"
                )

    except Exception as ctx_err:
        logger.error(f"Failed to fetch dynamic telemetry context for ask_admin_question: {ctx_err}")

    dynamic_context_str = "\n".join(dynamic_context)

    system_prompt = (
        "You are an AI analytics assistant for the AskMukthiGuru admin dashboard. "
        "Answer questions about platform metrics, query volume, latency, costs, models, "
        "hallucination rates, serene mind triggers, and provider details. "
        "Analyze the provided metrics, including model breakdown and step latencies, to answer complex queries. "
        "Be professional, accurate, and concise (2-4 sentences). If the data is unavailable, state so."
    )

    context_block = ""
    if req.kpi_context:
        context_block += f"Current UI Metrics Context:\n{req.kpi_context}\n\n"
    if dynamic_context_str:
        context_block += f"Dynamic DB Telemetry Context:\n{dynamic_context_str}\n\n"

    user_message = f"{context_block}Question: {req.question}"

    try:
        answer = await llm_service.generate(
            system_prompt=system_prompt,
            user_prompt=user_message,
            max_tokens=300,
            temperature=0.3,
        )
        if not answer or not answer.strip():
            logger.warning(
                "LLM returned empty or whitespace response for admin ask. Using fallback response."
            )
            answer = "The Guru is unable to answer this question. Please try again."
        return {"response": answer.strip()}
    except Exception as e:
        logger.error(f"Error in ask_admin_question: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Admin assistant request failed. Please try again."
        )


# ── Unit 23: Cost Attribution Endpoints ──────────────────────────────


@admin_router.get("/cost/usage")
async def get_cost_usage(
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Get token usage and cost report. Admin only."""
    from services.cost_tracker import get_cost_tracker

    tracker = get_cost_tracker()
    report = tracker.get_usage_report(tenant_id=tenant_id, user_id=user_id, days=days)
    return {
        "tenant_id": report.tenant_id,
        "period_days": report.period_days,
        "total_tokens_in": report.total_tokens_in,
        "total_tokens_out": report.total_tokens_out,
        "total_tokens": report.total_tokens,
        "total_cost_usd": report.total_cost_usd,
        "unique_users": report.unique_users,
        "unique_sessions": report.unique_sessions,
        "by_model": report.by_model,
        "by_provider": report.by_provider,
    }


@admin_router.get("/cost/daily/{tenant_id}")
async def get_daily_cost(
    tenant_id: str,
    days: int = Query(7, ge=1, le=90),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Get day-by-day cost breakdown for a tenant. Admin only."""
    from services.cost_tracker import get_cost_tracker

    return get_cost_tracker().get_daily_usage(tenant_id, days=days)


# ── Unit 22: Prompt Versioning Endpoints ─────────────────────────────


@admin_router.get("/prompt-store/names")
async def list_prompt_names(
    user: dict = Depends(_require_admin),
) -> list[str]:
    """List all prompt names in the prompt store. Admin only."""
    from services.prompt_store import get_prompt_store

    return get_prompt_store().list_prompt_names()


@admin_router.get("/prompt-store/{name}/versions")
async def list_prompt_versions(
    name: str,
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List all versions of a prompt. Admin only."""
    from services.prompt_store import get_prompt_store

    store = get_prompt_store()
    versions = store.list_versions(name)
    return [
        {
            "id": v.id,
            "name": v.name,
            "version": v.version,
            "description": v.description,
            "author": v.author,
            "created_at": v.created_iso,
            "is_active": v.is_active,
            "content_length": len(v.content),
        }
        for v in versions
    ]


@admin_router.post("/prompt-store/{name}/rollback/{version}")
async def rollback_prompt(
    name: str,
    version: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Rollback a prompt to a specific version. Admin only."""
    from services.prompt_store import get_prompt_store

    result = get_prompt_store().rollback(name, version)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Version {version} of {name} not found")
    return {"status": "rolled_back", "name": name, "version": version}


# ── Unit 16: A/B Testing Endpoints ───────────────────────────────────


@admin_router.get("/ab-tests")
async def list_ab_experiments(
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List all registered A/B experiments. Admin only."""
    from services.ab_testing import get_ab_router

    return get_ab_router().list_experiments()


@admin_router.get("/ab-tests/{experiment}/assign")
async def preview_ab_assignment(
    experiment: str,
    user_id: str = Query(..., description="User UUID to preview assignment for"),
    caller: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Preview A/B variant assignment for a user. Admin only."""
    from services.ab_testing import get_ab_router

    result = get_ab_router().assign(user_id, experiment)
    return {
        "experiment": result.experiment_name,
        "user_id": result.user_id,
        "variant": result.variant,
        "is_control": result.is_control,
        "assignment_hash": result.assignment_hash,
    }


@admin_router.get("/queue")
async def list_queue_jobs(
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container),
):
    """List all active/queued jobs for admin queue monitor."""
    if not container.job_queue:
        return {"jobs": [], "queue_enabled": False}
    jobs = await container.job_queue.list_jobs(limit=limit)
    return {"jobs": jobs, "queue_enabled": True, "total": len(jobs)}


# ---- OKF management (Phase 5) ----
def _load_approved_okf_review_titles() -> dict[str, dict[str, Any]]:
    """Map OKF entry title -> {"by", "at"} for entries a human approved via the
    review queue. ``approve_okf_entry`` writes the frontmatter ``title`` verbatim
    from ``entry_json["title"]`` (only the filename gets slugified), so matching
    on that exact string ties a live markdown entry back to its approval row.

    Degrades to an empty map (never raises) when Supabase is unavailable or the
    query fails — verification provenance is best-effort, not load-bearing.
    """
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        return {}
    try:
        res = (
            client.table("okf_review_queue")
            .select("entry_json,reviewed_by,reviewed_at")
            .eq("status", "approved")
            .execute()
        )
    except Exception as e:
        logger.warning("Failed to load approved OKF review rows: %s", e)
        return {}

    verified: dict[str, dict[str, Any]] = {}
    for row in res.data or []:
        entry = row.get("entry_json") or {}
        title = str(entry.get("title", "")).strip()
        if not title:
            continue
        reviewed_by = row.get("reviewed_by")
        verified[title] = {
            "by": f"human:{reviewed_by}" if reviewed_by else "human",
            "at": row.get("reviewed_at"),
        }
    return verified


@admin_router.get("/okf")
async def list_okf_entries(
    type_filter: Optional[str] = Query(None),
    user: dict = Depends(_require_admin),
):
    """List OKF knowledge entries (optionally filtered by type). Admin only."""
    from services.memory.okf_store import OKFStore

    store = OKFStore()
    entries = store.by_type(type_filter) if type_filter else store.list_entries()
    verified_by_title = _load_approved_okf_review_titles()
    return {
        "entries": [
            {
                "title": e.title,
                "type": e.type,
                "source": e.source,
                "tags": e.tags,
                "body_preview": e.body[:200],
                "verified": verified_by_title.get(e.title.strip()),
            }
            for e in entries
        ],
        "total": len(entries),
    }


@admin_router.post("/okf/compile")
async def compile_okf_index(user: dict = Depends(_require_admin)):
    """Rebuild the OKF compiled index. Admin only."""
    from services.memory.compiler import compile_okf

    path = compile_okf()
    return {"status": "ok", "path": str(path)}


class OkfExtractRequest(BaseModel):
    topic: Optional[str] = None
    video_id: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    mode: str = Field(
        default="direct", description="'direct' (run inline) or 'celery' (queue async)"
    )


@admin_router.post("/okf/extract")
async def extract_okf_entries(
    body: OkfExtractRequest,
    user: dict = Depends(_require_admin),
):
    """Extract OKF entries from Qdrant/Neo4j/LightRAG via LLM synthesis. Admin only."""

    if body.mode == "celery":
        from tasks.okf_extract_tasks import extract_okf_entries as celery_extract

        task = celery_extract.delay(
            target_topic=body.topic,
            target_video_id=body.video_id,
            limit=body.limit,
            auto_approve=False,
        )
        return {"status": "queued", "task_id": task.id, "mode": "celery"}

    # Direct mode — run inline (may take 30-120s for LLM calls)
    from scripts.extract_okf_from_stores import extract_okf

    paths = await extract_okf(
        target_topic=body.topic,
        target_video_id=body.video_id,
        limit=body.limit,
        auto_approve=False,
    )
    return {
        "status": "ok",
        "entries_written": len(paths),
        "paths": [str(p) for p in paths],
        "mode": "staging",
    }


class OntologyReviewRequest(BaseModel):
    reviewer_notes: Optional[str] = Field(default=None, max_length=4000)


def _ontology_driver_or_503():
    container = get_container()
    driver = getattr(container, "neo4j_driver", None)
    if driver is None:
        raise HTTPException(status_code=503, detail="Ontology graph service unavailable")
    return driver


@admin_router.get("/ontology/review")
async def list_ontology_review_queue(
    status: str = Query("pending", pattern="^(pending|approved|rejected|all)$"),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List ontology relationships by review status; legacy edges stay pending."""
    driver = _ontology_driver_or_503()

    def _read() -> list[dict[str, Any]]:
        with driver.session() as session:
            clauses = ["coalesce(r.review_status, 'pending') = $status"]
            params: dict[str, Any] = {"status": status, "limit": limit}
            if status == "all":
                clauses = ["true"]
            query = f"""
                MATCH (s:base)-[r]->(o:base)
                WHERE {' AND '.join(clauses)}
                RETURN elementId(r) AS relationship_id,
                       s.entity_id AS subject_id,
                       s.name AS subject,
                       type(r) AS relation,
                       o.entity_id AS object_id,
                       o.name AS object,
                       r.confidence AS confidence,
                       coalesce(r.review_status, 'pending') AS review_status,
                       coalesce(r.reviewed, false) AS reviewed,
                       r.evidence AS evidence,
                       r.source_doc_id AS source_doc_id,
                       r.source_chunk_id AS source_chunk_id,
                       r.reviewed_at AS reviewed_at,
                       r.reviewed_by AS reviewed_by,
                       r.reviewer_notes AS reviewer_notes
                ORDER BY r.extracted_at DESC
                LIMIT $limit
            """
            return [dict(record) for record in session.run(query, **params)]

    return await asyncio.to_thread(_read)


async def _set_ontology_review_status(
    relationship_id: str,
    *,
    status: str,
    user: dict,
    reviewer_notes: Optional[str],
) -> dict[str, Any]:
    driver = _ontology_driver_or_503()
    reviewed = status == "approved"

    def _write() -> dict[str, Any] | None:
        with driver.session() as session:
            record = session.run(
                """
                MATCH ()-[r]->()
                WHERE elementId(r) = $relationship_id
                SET r.reviewed = $reviewed,
                    r.review_status = $status,
                    r.reviewed_at = $reviewed_at,
                    r.reviewed_by = $reviewed_by,
                    r.reviewer_notes = $reviewer_notes
                RETURN elementId(r) AS relationship_id,
                       r.review_status AS review_status,
                       r.reviewed AS reviewed,
                       r.reviewed_at AS reviewed_at,
                       r.reviewed_by AS reviewed_by
                """,
                relationship_id=relationship_id,
                reviewed=reviewed,
                status=status,
                reviewed_at=datetime.now(UTC).isoformat(),
                reviewed_by=str(user.get("id") or ""),
                reviewer_notes=reviewer_notes,
            ).single()
            return dict(record) if record else None

    result = await asyncio.to_thread(_write)
    if result is None:
        raise HTTPException(status_code=404, detail="Ontology relationship not found")
    return result


@admin_router.post("/ontology/review/{relationship_id}/approve")
async def approve_ontology_relationship(
    relationship_id: str,
    body: OntologyReviewRequest = Body(default=OntologyReviewRequest()),
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Make one staged ontology relationship traversable after human review."""
    return await _set_ontology_review_status(
        relationship_id,
        status="approved",
        user=user,
        reviewer_notes=body.reviewer_notes,
    )


@admin_router.post("/ontology/review/{relationship_id}/reject")
async def reject_ontology_relationship(
    relationship_id: str,
    body: OntologyReviewRequest = Body(default=OntologyReviewRequest()),
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Keep one rejected ontology relationship permanently out of retrieval."""
    return await _set_ontology_review_status(
        relationship_id,
        status="rejected",
        user=user,
        reviewer_notes=body.reviewer_notes,
    )


class AppSettingsUpdate(BaseModel):
    web_search_allowed_domains: list[str]


@admin_router.get("/settings")
async def get_admin_settings(
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Fetch global application settings (Admin only)."""

    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        # Fallback to current settings if Supabase is offline/not set
        return {"web_search_allowed_domains": settings.web_search_allowed_domains_list}

    try:
        res = client.table("app_settings").select("*").eq("key", "global").execute()
        if res.data and len(res.data) > 0:
            val = res.data[0]["value"]
            return {
                "web_search_allowed_domains": val.get(
                    "web_search_allowed_domains", settings.web_search_allowed_domains_list
                )
            }
    except Exception as e:
        logger.error(f"Failed to fetch app settings from DB: {e}")

    return {"web_search_allowed_domains": settings.web_search_allowed_domains_list}


@admin_router.post("/settings")
async def update_admin_settings(
    payload: AppSettingsUpdate,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Update global application settings (Admin only)."""

    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")

    try:
        data = {
            "key": "global",
            "value": {
                "web_search_allowed_domains": [
                    d.strip().lower() for d in payload.web_search_allowed_domains if d.strip()
                ]
            },
            "updated_at": "now()",
        }
        client.table("app_settings").upsert(data).execute()

        # Dynamic hot-reload in memory
        container = get_container()
        new_domains = [d.strip().lower() for d in payload.web_search_allowed_domains if d.strip()]
        settings.web_search_allowed_domains = ",".join(new_domains)
        if getattr(container, "web_search", None):
            container.web_search.allowed_domains = new_domains
            logger.info(
                f"WebSearchService allowed domains dynamically updated in memory: {new_domains}"
            )

        return {"status": "success", "web_search_allowed_domains": new_domains}
    except Exception as e:
        logger.error(f"Failed to update app settings in DB: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings. Please try again.")


class OkfReviewItem(BaseModel):
    entry_json: dict[str, Any]
    source_video_id: Optional[str] = None
    source_video_title: Optional[str] = None
    guru_slug: Optional[str] = "default"
    reviewer_notes: Optional[str] = None


@admin_router.get("/okf/review")
async def list_okf_review_queue(
    status: str = "pending",
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List items in the OKF review queue (Admin only)."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Data service not available")

    try:
        res = client.table("okf_review_queue").select("*").eq("status", status).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to fetch OKF review queue: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to load review queue. Please try again."
        )


@admin_router.post("/okf/review/{review_id}/approve")
async def approve_okf_entry(
    review_id: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Approve a draft OKF entry, save it as a markdown file, and recompile index (Admin only)."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Data service not available")

    try:
        res = client.table("okf_review_queue").select("*").eq("id", review_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Review entry not found")

        row = res.data[0]
        entry = row["entry_json"]
        guru_slug = row.get("guru_slug") or "default"

        title = entry.get("title", "untitled")
        import string

        valid_chars = f"-_{string.ascii_letters}{string.digits}"
        slug = "".join(c if c in valid_chars else "-" for c in title.lower().replace(" ", "_"))
        slug = re.sub(r"-+", "-", slug).strip("-")

        from services.memory.compiler import _OKF_DIR

        target_dir = _OKF_DIR / guru_slug
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{slug}.md"

        meta = {
            "type": entry.get("type", "teaching"),
            "title": title,
            "tags": entry.get("tags", []),
            "source": entry.get("source", ""),
            "confidence": "high",
        }
        import yaml

        yaml_str = yaml.safe_dump(meta, default_flow_style=False)
        body = entry.get("body", "")

        content = f"---\n{yaml_str}---\n\n{body}\n"
        target_file.write_text(content, encoding="utf-8")

        from services.memory.compiler import compile_okf

        compile_okf()

        client.table("okf_review_queue").update(
            {
                "status": "approved",
                "reviewed_at": "now()",
                "reviewed_by": user.get("id"),
            }
        ).eq("id", review_id).execute()

        return {"status": "success", "file": str(target_file)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve OKF entry: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve entry. Please try again.")


@admin_router.post("/okf/review/{review_id}/reject")
async def reject_okf_entry(
    review_id: str,
    reviewer_notes: Optional[str] = Body(None, embed=True),
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Reject a draft OKF entry (Admin only)."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Data service not available")

    try:
        client.table("okf_review_queue").update(
            {
                "status": "rejected",
                "reviewer_notes": reviewer_notes,
                "reviewed_at": "now()",
                "reviewed_by": user.get("id"),
            }
        ).eq("id", review_id).execute()

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to reject OKF entry: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject entry. Please try again.")


# ---- Ingestion quality staging queue (Apache Iceberg-style staged validation) ----
# ingest/quality_gate.py's StagingQueue.submit() writes here on Tier-3 reject;
# StagingQueuePage.tsx expected these routes to exist but they never did — the
# page 404'd on every load.


@admin_router.get("/staging")
async def list_staging_queue(
    status: str = Query("pending"),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """List ingestion content staged for human quality review (Admin only)."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        return []

    try:
        res = (
            client.table("staging_quality_queue")
            .select("id, created_at, source_url, quality_score, fail_reasons, content_preview")
            .eq("status", status)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list staging queue: {e}")
        raise HTTPException(status_code=500, detail="Failed to load staging queue.")


@admin_router.post("/staging/{staging_id}/review")
async def review_staging_item(
    staging_id: str,
    action: str = Body(..., embed=True, pattern="^(approve|reject)$"),
    notes: Optional[str] = Body(None, embed=True),
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Record a human review decision on a staged ingestion item (Admin only).

    Records the decision only — approving does not automatically re-run
    ingestion for the source; that remains a separate, deliberate step.
    """
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Data service not available")

    try:
        res = (
            client.table("staging_quality_queue")
            .update(
                {
                    "status": "approved" if action == "approve" else "rejected",
                    "reviewer_notes": notes or "",
                    "reviewed_at": "now()",
                    "reviewed_by": user.get("id"),
                }
            )
            .eq("id", staging_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Staging item not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to review staging item: {e}")
        raise HTTPException(status_code=500, detail="Failed to review item. Please try again.")


# ── Admin Logs ────────────────────────────────────────────────────


class AdminLogsFilter(BaseModel):
    level: Optional[str] = None
    search: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None


@admin_router.get("/logs")
async def list_admin_logs(
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Fetch structured app logs for the admin UI. Requires admin authentication + AAL2."""
    from app.telemetry_db import _get_client

    client = _get_client()
    if not client:
        # Fail gracefully when telemetry is not configured; return empty so the
        # admin UI does not crash, but log the incident.
        logger.warning("Supabase client unavailable; returning empty admin logs")
        return []

    try:
        query = client.table("app_logs").select("*")
        if from_date:
            query = query.gte("created_at", from_date)
        if to_date:
            query = query.lte("created_at", to_date)
        if level:
            query = query.eq("level", level)
        if search:
            query = query.ilike("message", f"%{search}%")
        response = query.order("created_at", desc=True).limit(200).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to fetch admin logs: {e}")
        return []


# ── Web Ingestion ─────────────────────────────────────────────────


@admin_router.post("/admin/ingest-url")
async def admin_ingest_url(
    url: str = Body(..., embed=True),
    mode: str = Body("auto", embed=True),
    user=Depends(_require_admin),
):
    """Admin-only: trigger web ingestion for a URL."""
    valid_modes = {"auto", "static", "dynamic", "stealth"}
    if mode not in valid_modes:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mode '{mode}'. Must be one of: {', '.join(sorted(valid_modes))}",
        )
    # Validate URL before queueing — reuse ingestion pipeline validator
    from ingestion.web_ingest_pipeline import _validate_and_normalize

    try:
        url = await _validate_and_normalize(url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid URL: {e}")
    from tasks.web_ingest_tasks import ingest_url_task

    task = ingest_url_task.delay(url, mode=mode)
    return {"task_id": task.id, "url": url, "status": "queued"}


class ReingestRequest(BaseModel):
    source: str = Field(..., min_length=1)
    mode: str = Field(default="contextual", description="One of: contextual, url")


# ── Contextual Re-ingestion ────────────────────────────────────────


class ContextualReingestRequest(BaseModel):
    source_url: Optional[str] = None
    limit: Optional[int] = None


class ContextualReingestDryRunRequest(BaseModel):
    source_url: Optional[str] = None
    limit: int = 1


@admin_router.post("/contextual-reingest/dry-run")
async def admin_contextual_reingest_dry_run(
    body: ContextualReingestDryRunRequest,
    user=Depends(_require_admin),
):
    """Admin-only preview of contextual re-ingestion."""
    from tasks.contextual_reingest_task import contextual_reingest_dry_run

    task = contextual_reingest_dry_run.delay(
        source_url=body.source_url,
        limit=body.limit,
    )
    return {"task_id": task.id, "source_url": body.source_url, "status": "queued"}


@admin_router.post("/reingest")
async def admin_reingest(
    body: ReingestRequest,
    user: dict = Depends(_require_admin),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    """Admin-only generic re-ingestion endpoint.

    Supports two modes:
      - ``contextual``: queue the existing contextual re-ingest worker.
      - ``url``: queue a fresh web ingestion for the provided source URL.

    All require admin authentication + AAL2.
    """
    mode = body.mode.lower().strip()
    if mode == "url":
        from ingestion.web_ingest_pipeline import _validate_and_normalize

        try:
            normalized_url = await _validate_and_normalize(body.source)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid URL: {e}")
        from tasks.web_ingest_tasks import ingest_url_task

        task = ingest_url_task.delay(normalized_url, mode="auto")
        return {"task_id": task.id, "source": normalized_url, "mode": "url", "status": "queued"}

    if mode == "contextual":
        from tasks.contextual_reingest_task import contextual_reingest

        acquired, owner = await _acquire_reingest_lock(container)
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail=f"Another contextual re-ingest is already running (lock held by {owner}). "
                "Wait for it to finish or expire.",
            )
        try:
            task = contextual_reingest.delay(source_url=body.source)
            return {
                "task_id": task.id,
                "source": body.source,
                "mode": "contextual",
                "status": "queued",
            }
        except Exception:
            await _release_reingest_lock(container)
            raise

    raise HTTPException(
        status_code=422,
        detail=f"Invalid mode '{body.mode}'. Must be one of: contextual, url",
    )


_REINGEST_LOCK_KEY: str = "contextual_reingest:running"
_REINGEST_LOCK_TTL_SECONDS: int = 3600


async def _acquire_reingest_lock(container: ServiceContainer) -> tuple[bool, Optional[str]]:
    """Try to acquire a Redis singleton lock for contextual re-ingest.

    Returns (acquired, existing_owner). owner is a short task-id/date string
    so the admin knows who is holding the lock.
    """
    redis_client = getattr(container, "redis_client", None)
    if redis_client is None:
        # No Redis → cannot deduplicate; allow through with a warning.
        logger.warning("No Redis client available; skipping contextual re-ingest lock")
        return True, None
    try:
        import datetime as _dt

        _current = celery_app.current_task
        _task_id = (
            _current.request.id if _current is not None and hasattr(_current, "request") else "api"
        )
        owner = f"{_task_id}@{_dt.datetime.now(_dt.UTC).isoformat()}"
        # redis-py set nx ex is atomic
        acquired = redis_client.set(
            _REINGEST_LOCK_KEY,
            owner,
            nx=True,
            ex=_REINGEST_LOCK_TTL_SECONDS,
        )
        if acquired:
            return True, None
        existing = redis_client.get(_REINGEST_LOCK_KEY)
        return False, existing.decode() if isinstance(existing, bytes) else existing
    except Exception as exc:
        logger.warning("Failed to acquire contextual re-ingest lock: %s", exc)
        # Fail-open: if Redis is misbehaving, still allow the job but log it.
        return True, None


async def _release_reingest_lock(container: ServiceContainer) -> None:
    redis_client = getattr(container, "redis_client", None)
    if redis_client is None:
        return
    try:
        redis_client.delete(_REINGEST_LOCK_KEY)
    except Exception as exc:
        logger.warning("Failed to release contextual re-ingest lock: %s", exc)


@admin_router.post("/contextual-reingest")
async def admin_contextual_reingest(
    body: ContextualReingestRequest,
    user=Depends(_require_admin),
    container: ServiceContainer = Depends(get_container),
):
    """Admin-only: trigger contextual re-ingestion from spiritual_wisdom.

    Singleton Redis lock prevents overlapping full-corpus rebuilds.
    """
    from tasks.contextual_reingest_task import contextual_reingest

    acquired, owner = await _acquire_reingest_lock(container)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail=f"Another contextual re-ingest is already running (lock held by {owner}). "
            "Wait for it to finish or expire.",
        )

    try:
        task = contextual_reingest.delay(
            source_url=body.source_url,
            limit=body.limit,
        )
        return {"task_id": task.id, "source_url": body.source_url, "status": "queued"}
    except Exception:
        await _release_reingest_lock(container)
        raise


# ── Governed source-release administration ────────────────────────────────
class SourceReleaseRegistrationRequest(BaseModel):
    corpus_id: str = Field(default_factory=lambda: settings.default_corpus_id)
    source_url: str = Field(..., min_length=1, max_length=4096)
    source_identity: str = Field(..., min_length=1, max_length=1024)
    content_checksum: str = Field(..., min_length=1, max_length=256)
    notes: Optional[str] = Field(default=None, max_length=1000)


def _source_release_registry():
    from app.corpus_release_registry import CorpusReleaseRegistry

    return CorpusReleaseRegistry.from_settings(settings)


def _raise_source_release_error(exc: Exception) -> None:
    from app.corpus_release_registry import (
        CorpusReleaseRegistryDisabled,
        CorpusReleaseRegistryUnavailable,
        CorpusReleaseTransitionError,
    )

    if isinstance(exc, CorpusReleaseRegistryDisabled):
        raise HTTPException(status_code=409, detail="Source-release registry is disabled")
    if isinstance(exc, CorpusReleaseTransitionError):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, CorpusReleaseRegistryUnavailable):
        raise HTTPException(status_code=503, detail="Source-release control store is unavailable")
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc))
    raise HTTPException(status_code=500, detail="Source-release operation failed")


@admin_router.get("/source-releases")
async def list_source_releases(
    corpus_id: str = Query(default_factory=lambda: settings.default_corpus_id),
    source_identity: Optional[str] = Query(default=None, max_length=1024),
    limit: int = Query(default=100, ge=1, le=200),
    user: dict = Depends(_require_admin),
) -> list[dict[str, Any]]:
    """Return bounded source-release metadata without source bodies or checksums."""
    try:
        releases = _source_release_registry().list_releases(
            corpus_id=corpus_id,
            source_identity=source_identity,
            limit=limit,
        )
        return [release.admin_dict() for release in releases]
    except Exception as exc:
        _raise_source_release_error(exc)


@admin_router.post("/source-releases", status_code=201)
async def register_source_release(
    body: SourceReleaseRegistrationRequest,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Register a checksum-addressed candidate source release for human review."""
    try:
        release = _source_release_registry().register_source(
            corpus_id=body.corpus_id,
            source_url=body.source_url,
            source_identity=body.source_identity,
            content_checksum=body.content_checksum,
            notes=body.notes,
        )
        return release.admin_dict()
    except Exception as exc:
        _raise_source_release_error(exc)


@admin_router.post("/source-releases/{release_id}/approve")
async def approve_source_release(
    release_id: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Record an AAL2 admin approval for a pending source release."""
    try:
        release = _source_release_registry().approve_release(
            release_id,
            approved_by=str(user.get("id") or ""),
        )
        return release.admin_dict()
    except Exception as exc:
        _raise_source_release_error(exc)


@admin_router.post("/source-releases/{release_id}/activate")
async def activate_source_release(
    release_id: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Atomically activate an approved release and supersede its prior active peer."""
    try:
        return _source_release_registry().activate_release(release_id).admin_dict()
    except Exception as exc:
        _raise_source_release_error(exc)


@admin_router.post("/source-releases/{release_id}/reject")
async def reject_source_release(
    release_id: str,
    user: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Close a pending or approved candidate without deleting its audit trail."""
    try:
        return _source_release_registry().reject_release(release_id).admin_dict()
    except Exception as exc:
        _raise_source_release_error(exc)


@admin_router.post("/ingest/book")
async def ingest_book_endpoint(
    collection: str = "spiritual_wisdom_contextual",
    json_path: str = "data/book/The_Four_Sacred_Secrets_structure.json",
    admin: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Dispatch the Four Sacred Secrets book (Qdrant + LightRAG + OKF) via Celery.

    json_path is relative to the backend/ working directory inside the image
    (baked in via Dockerfile.railway's `COPY backend/ .`); runs in
    celery-worker so LightRAG can reach Neo4j over Railway's internal network.
    """
    from tasks.ingest_tasks import ingest_book_task

    task = ingest_book_task.apply_async(args=[json_path, collection])
    return {"status": "queued", "task_id": task.id, "collection": collection}


def _source_release_readiness() -> dict[str, Any]:
    """Return allowlisted release counts for the operations snapshot only."""
    readiness = {
        "enabled": settings.corpus_release_registry_enabled,
        "available": False,
        "active_count": 0,
        "pending_count": 0,
        "approved_count": 0,
        "last_activated_at": None,
    }
    if not settings.corpus_release_registry_enabled:
        return readiness
    try:
        releases = _source_release_registry().list_releases(
            corpus_id=settings.default_corpus_id,
            limit=200,
        )
    except Exception as exc:
        logger.warning("Source-release snapshot unavailable: %s", exc)
        return readiness
    readiness["available"] = True
    for release in releases:
        if release.status == "active":
            readiness["active_count"] += 1
        elif release.status == "pending":
            readiness["pending_count"] += 1
        elif release.status == "approved":
            readiness["approved_count"] += 1
        if release.activated_at:
            previous = readiness["last_activated_at"]
            if previous is None or release.activated_at > previous:
                readiness["last_activated_at"] = release.activated_at
    return readiness
