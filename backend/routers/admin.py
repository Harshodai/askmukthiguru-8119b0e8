import logging
from typing import Optional, Any

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
        logger.error(f"Error in ask_admin_question: {e}")
        raise HTTPException(status_code=500, detail=str(e))
