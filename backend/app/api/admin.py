"""
Admin dashboard API routes.

Unit 13 — moved from `routers/admin.py` into `app.api`.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.limiter import limiter
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
    get_node_latencies,
)
from services.auth_service import get_current_user_from_supabase

logger = logging.getLogger(__name__)

admin_router = APIRouter(tags=["admin"])


@admin_router.get("/traces")
async def fetch_telemetry_traces(
    limit: int = 50,
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Fetch recent traces for Admin UI. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_recent_traces(min(limit, 200))


@admin_router.get("/traces/{trace_id}")
async def fetch_query_trace(
    trace_id: str,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Fetch a single detailed trace by query ID. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    trace = await get_query_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return trace


@admin_router.get("/prompts")
async def fetch_prompts(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
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


class DoctrineTermUpdate(BaseModel):
    canonical: str = Field(..., min_length=1)
    variants: list[str] = Field(default_factory=list)
    enabled: bool = True


@admin_router.get("/doctrine-terms")
async def fetch_doctrine_terms(
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Effective doctrine-term correction map (code defaults + admin overrides)."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.doctrine_terms import load_doctrine_terms

    return {"terms": load_doctrine_terms()}


@admin_router.post("/doctrine-terms")
async def upsert_doctrine_term(
    body: DoctrineTermUpdate,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Add/update a canonical term + its mis-transcription variants. Applies without a restart —
    the whisper bias, ingest corrector and output cleanup all read the shared source of truth."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    from app.telemetry_db import _get_client
    from services.doctrine_terms import reload as reload_doctrine_terms

    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    try:
        await client.table("doctrine_terms").upsert(
            {
                "canonical": body.canonical.strip(),
                "variants": body.variants,
                "enabled": body.enabled,
                "updated_by": user.get("email") or user.get("id"),
            },
            on_conflict="canonical",
        ).execute()
    except Exception as e:
        logger.error(f"Failed to upsert doctrine term: {e}")
        raise HTTPException(status_code=500, detail="Failed to save doctrine term. Please try again.")
    reload_doctrine_terms()  # hot-reload the correction map (no restart needed)
    return {"ok": True, "canonical": body.canonical.strip()}


@admin_router.get("/rag-flow-graph")
async def get_rag_flow_graph(
    strategy: str = "standard",
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """
    Expose the active RAG graph strategy nodes and edges, merged with average timing latencies.
    Requires admin authentication.
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

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
            nodes.append({
                "id": key,
                "label": getattr(node, "name", key) or key,
                "avg_latency_ms": avg_metrics["avg_latency_ms"],
                "invocation_count": avg_metrics["count"],
            })
            
        # 3. Extract edges
        edges = []
        for edge in compiled_graph.edges:
            edges.append({
                "id": f"e-{edge.source}-{edge.target}",
                "source": edge.source,
                "target": edge.target,
                "animated": True,
            })
            
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
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_eval_runs()


@admin_router.get("/kpis")
async def fetch_kpis(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Fetch aggregated KPIs for Admin UI. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    return await get_kpis(from_date, to_date)


@admin_router.get("/models")
async def list_models(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[str]:
    """List available LLM models. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_available_models()


@admin_router.get("/timeseries")
async def get_timeseries(
    metric: str,
    from_date: str,
    to_date: str,
    buckets: int = 24,
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Get timeseries data for a metric. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_timeseries_data(metric, from_date, to_date, buckets)


@admin_router.get("/triggers")
async def list_triggers(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List trigger events. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_trigger_events(from_date, to_date)


@admin_router.get("/safety-events")
async def list_safety_events(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List safety events. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_safety_events(from_date, to_date)


@admin_router.get("/topic-clusters")
async def list_topic_clusters(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List topic clusters. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_topic_clusters()


@admin_router.get("/retrieval-health")
async def get_retrieval_health_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Get retrieval health metrics. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_retrieval_health(from_date, to_date)


@admin_router.get("/quality-data")
async def get_quality_data_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Get quality data metrics. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_quality_data(from_date, to_date)


@admin_router.get("/eval-runs")
async def list_eval_runs(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List evaluation runs. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_eval_runs()


@admin_router.get("/golden-questions")
async def list_golden_questions(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List golden questions. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_golden_questions()


@admin_router.get("/ingestion-runs")
async def list_ingestion_runs(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List ingestion runs. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_ingestion_runs()


@admin_router.get("/alert-rules")
async def list_alert_rules(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List alert rules. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_alert_rules()


@admin_router.get("/alert-events")
async def list_alert_events(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List alert events. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_alert_events()


@admin_router.get("/annotations")
async def list_annotations(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List annotations. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_annotations()


@admin_router.get("/admins")
async def list_admins(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List admin users. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_admins()


@admin_router.get("/model-pricing")
async def list_model_pricing(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List model pricing. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_model_pricing()


@admin_router.get("/top-failures")
async def get_top_failures_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(8, ge=1, le=100),
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Get top failures by faithfulness. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_top_failures(from_date, to_date, limit)


@admin_router.get("/ragas-heatmap")
async def get_ragas_heatmap_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(8, ge=1, le=100),
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Get RAGAS heatmap data. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_ragas_heatmap(from_date, to_date, buckets)


@admin_router.get("/trigger-trend")
async def get_trigger_trend_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(14, ge=1, le=100),
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Get trigger trend data. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_trigger_trend(from_date, to_date, buckets)


@admin_router.get("/similarity-trend")
async def get_similarity_trend_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(14, ge=1, le=100),
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Get similarity trend data. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_similarity_trend(from_date, to_date, buckets)


@admin_router.get("/dead-docs")
async def get_dead_docs_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Get dead documents. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_dead_docs(from_date, to_date)


@admin_router.get("/empty-retrievals")
async def get_empty_retrievals_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Get empty retrievals. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_empty_retrievals(from_date, to_date, limit)


@admin_router.get("/ingestion-health")
async def get_ingestion_health_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Get ingestion health status. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_ingestion_health()


@admin_router.get("/prompt-metrics")
async def get_prompt_metrics_by_version_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
) -> Any:
    """Get prompt metrics by version. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_prompt_metrics_by_version()


@admin_router.get("/live-feed")
async def poll_live_feed_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Poll live feed. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_live_feed()


class AskRequest(BaseModel):
    question: str
    kpi_context: str = ""


@admin_router.post("/ask")
async def ask_admin_question(
    req: AskRequest,
    user: dict = Depends(get_current_user_from_supabase),
):
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    container = get_container()
    llm_service = container.ollama

    # Fetch rich context dynamically to support complex queries
    from app.telemetry_db import get_kpis, get_node_latencies
    from services.cost_tracker import get_cost_tracker
    from datetime import datetime, timedelta, UTC

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
            
        dynamic_context.append(f"\nCost & Token Metrics:")
        dynamic_context.append(f"  Total Cost USD: ${cost_report.total_cost_usd:.6f}")
        dynamic_context.append(f"  Total Tokens: {cost_report.total_tokens} (Prompt/In: {cost_report.total_tokens_in}, Completion/Out: {cost_report.total_tokens_out})")
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
                dynamic_context.append(f"  - {nl.get('name')}: {nl.get('avg_duration_ms', 0):.2f}ms (count: {nl.get('count', 0)})")
                
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
        raise HTTPException(status_code=500, detail="Admin assistant request failed. Please try again.")


# ── Unit 23: Cost Attribution Endpoints ──────────────────────────────

@admin_router.get("/cost/usage")
async def get_cost_usage(
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Get token usage and cost report. Admin only."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
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
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """Get day-by-day cost breakdown for a tenant. Admin only."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.cost_tracker import get_cost_tracker
    return get_cost_tracker().get_daily_usage(tenant_id, days=days)


# ── Unit 22: Prompt Versioning Endpoints ─────────────────────────────

@admin_router.get("/prompt-store/names")
async def list_prompt_names(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[str]:
    """List all prompt names in the prompt store. Admin only."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.prompt_store import get_prompt_store
    return get_prompt_store().list_prompt_names()


@admin_router.get("/prompt-store/{name}/versions")
async def list_prompt_versions(
    name: str,
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List all versions of a prompt. Admin only."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.prompt_store import get_prompt_store
    store = get_prompt_store()
    versions = store.list_versions(name)
    return [
        {
            "id": v.id, "name": v.name, "version": v.version,
            "description": v.description, "author": v.author,
            "created_at": v.created_iso, "is_active": v.is_active,
            "content_length": len(v.content),
        }
        for v in versions
    ]


@admin_router.post("/prompt-store/{name}/rollback/{version}")
async def rollback_prompt(
    name: str,
    version: str,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Rollback a prompt to a specific version. Admin only."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.prompt_store import get_prompt_store
    result = get_prompt_store().rollback(name, version)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Version {version} of {name} not found")
    return {"status": "rolled_back", "name": name, "version": version}


# ── Unit 16: A/B Testing Endpoints ───────────────────────────────────

@admin_router.get("/ab-tests")
async def list_ab_experiments(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List all registered A/B experiments. Admin only."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    from services.ab_testing import get_ab_router
    return get_ab_router().list_experiments()


@admin_router.get("/ab-tests/{experiment}/assign")
async def preview_ab_assignment(
    experiment: str,
    user_id: str = Query(..., description="User UUID to preview assignment for"),
    caller: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Preview A/B variant assignment for a user. Admin only."""
    if not caller.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
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
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
):
    """List all active/queued jobs for admin queue monitor."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not container.job_queue:
        return {"jobs": [], "queue_enabled": False}
    jobs = await container.job_queue.list_jobs(limit=limit)
    return {"jobs": jobs, "queue_enabled": True, "total": len(jobs)}


# ---- OKF management (Phase 5) ----
def _require_admin(user: dict) -> None:
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")


@admin_router.get("/okf")
async def list_okf_entries(
    type_filter: Optional[str] = Query(None),
    user: dict = Depends(get_current_user_from_supabase),
):
    """List OKF knowledge entries (optionally filtered by type). Admin only."""
    _require_admin(user)
    from services.memory.okf_store import OKFStore
    store = OKFStore()
    entries = store.by_type(type_filter) if type_filter else store.list_entries()
    return {
        "entries": [
            {
                "title": e.title,
                "type": e.type,
                "source": e.source,
                "tags": e.tags,
                "body_preview": e.body[:200],
            }
            for e in entries
        ],
        "total": len(entries),
    }


@admin_router.post("/okf/compile")
async def compile_okf_index(user: dict = Depends(get_current_user_from_supabase)):
    """Rebuild the OKF compiled index. Admin only."""
    _require_admin(user)
    from services.memory.compiler import compile_okf
    path = compile_okf()
    return {"status": "ok", "path": str(path)}


class OkfExtractRequest(BaseModel):
    topic: Optional[str] = None
    video_id: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    auto_approve: bool = False
    mode: str = Field(default="direct", description="'direct' (run inline) or 'celery' (queue async)")


@admin_router.post("/okf/extract")
async def extract_okf_entries(
    body: OkfExtractRequest,
    user: dict = Depends(get_current_user_from_supabase),
):
    """Extract OKF entries from Qdrant/Neo4j/LightRAG via LLM synthesis. Admin only."""
    _require_admin(user)

    if body.mode == "celery":
        from tasks.okf_extract_tasks import extract_okf_entries as celery_extract

        task = celery_extract.delay(
            target_topic=body.topic,
            target_video_id=body.video_id,
            limit=body.limit,
            auto_approve=body.auto_approve,
        )
        return {"status": "queued", "task_id": task.id, "mode": "celery"}

    # Direct mode — run inline (may take 30-120s for LLM calls)
    from scripts.extract_okf_from_stores import extract_okf

    paths = await extract_okf(
        target_topic=body.topic,
        target_video_id=body.video_id,
        limit=body.limit,
        auto_approve=body.auto_approve,
    )
    return {
        "status": "ok",
        "entries_written": len(paths),
        "paths": [str(p) for p in paths],
        "mode": "approved" if body.auto_approve else "staging",
    }


class AppSettingsUpdate(BaseModel):
    web_search_allowed_domains: list[str]


@admin_router.get("/settings")
async def get_admin_settings(
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Fetch global application settings (Admin only)."""
    _require_admin(user)
    
    from app.telemetry_db import _get_client
    client = _get_client()
    if not client:
        # Fallback to current settings if Supabase is offline/not set
        return {
            "web_search_allowed_domains": settings.web_search_allowed_domains_list
        }
        
    try:
        res = client.table("app_settings").select("*").eq("key", "global").execute()
        if res.data and len(res.data) > 0:
            val = res.data[0]["value"]
            return {
                "web_search_allowed_domains": val.get("web_search_allowed_domains", settings.web_search_allowed_domains_list)
            }
    except Exception as e:
        logger.error(f"Failed to fetch app settings from DB: {e}")
        
    return {
        "web_search_allowed_domains": settings.web_search_allowed_domains_list
    }


@admin_router.post("/settings")
async def update_admin_settings(
    payload: AppSettingsUpdate,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Update global application settings (Admin only)."""
    _require_admin(user)
        
    from app.telemetry_db import _get_client
    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database service unavailable")
        
    try:
        data = {
            "key": "global",
            "value": {
                "web_search_allowed_domains": [d.strip().lower() for d in payload.web_search_allowed_domains if d.strip()]
            },
            "updated_at": "now()"
        }
        client.table("app_settings").upsert(data).execute()
        
        # Dynamic hot-reload in memory
        container = get_container()
        new_domains = [d.strip().lower() for d in payload.web_search_allowed_domains if d.strip()]
        settings.web_search_allowed_domains = ",".join(new_domains)
        if getattr(container, "web_search", None):
            container.web_search.allowed_domains = new_domains
            logger.info(f"WebSearchService allowed domains dynamically updated in memory: {new_domains}")
            
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
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict[str, Any]]:
    """List items in the OKF review queue (Admin only)."""
    _require_admin(user)
    from app.telemetry_db import _get_client
    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Data service not available")

    try:
        res = client.table("okf_review_queue").select("*").eq("status", status).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to fetch OKF review queue: {e}")
        raise HTTPException(status_code=500, detail="Failed to load review queue. Please try again.")


@admin_router.post("/okf/review/{review_id}/approve")
async def approve_okf_entry(
    review_id: str,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Approve a draft OKF entry, save it as a markdown file, and recompile index (Admin only)."""
    _require_admin(user)
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
        valid_chars = "-_%s%s" % (string.ascii_letters, string.digits)
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

        client.table("okf_review_queue").update({
            "status": "approved",
            "reviewed_at": "now()",
            "reviewed_by": user.get("id"),
        }).eq("id", review_id).execute()

        return {"status": "success", "file": str(target_file)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve OKF entry: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve entry. Please try again.")


@admin_router.post("/okf/review/{review_id}/reject")
async def reject_okf_entry(
    review_id: str,
    reviewer_notes: Optional[str] = None,
    user: dict = Depends(get_current_user_from_supabase),
) -> dict[str, Any]:
    """Reject a draft OKF entry (Admin only)."""
    _require_admin(user)
    from app.telemetry_db import _get_client
    client = _get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Data service not available")

    try:
        client.table("okf_review_queue").update({
            "status": "rejected",
            "reviewer_notes": reviewer_notes,
            "reviewed_at": "now()",
            "reviewed_by": user.get("id"),
        }).eq("id", review_id).execute()

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to reject OKF entry: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject entry. Please try again.")

