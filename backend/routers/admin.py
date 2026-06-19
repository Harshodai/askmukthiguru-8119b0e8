import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)

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
)
from services.auth_service import get_current_user_from_supabase
from app.dependencies import get_container, ServiceContainer

admin_router = APIRouter(
    tags=["admin"],
)


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


from typing import Any

from pydantic import BaseModel


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

    from app.dependencies import get_container

    container = get_container()
    llm_service = container.ollama

    system_prompt = (
        "You are an AI analytics assistant for the AskMukthiGuru admin dashboard. "
        "Answer questions about platform metrics, query volume, latency, costs, "
        "hallucination rates and serene mind triggers. Be concise (2-4 sentences). "
        "If data is unavailable say so — do not fabricate numbers."
    )

    context_block = f"Current platform metrics:\n{req.kpi_context}\n\n" if req.kpi_context else ""
    user_message = f"{context_block}{req.question}"

    try:
        answer = await llm_service.generate(
            system_prompt=system_prompt,
            user_prompt=user_message,
            max_tokens=200,
            temperature=0.3,
        )
        if not answer or not answer.strip():
            logger.warning(
                "LLM returned empty or whitespace response for admin ask. Using fallback response."
            )
            answer = "I apologize, but I am currently unable to retrieve a response from the analytics engine. Please ensure that platform metrics are populated and try again."
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

