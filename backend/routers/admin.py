from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from app.telemetry_db import get_recent_traces, get_kpis, get_available_models, get_timeseries_data, get_trigger_events, get_safety_events, get_topic_clusters, get_retrieval_health, get_quality_data, get_eval_runs, get_golden_questions, get_ingestion_runs, get_alert_rules, get_alert_events, get_annotations, get_admins, get_model_pricing, get_top_failures, get_ragas_heatmap, get_trigger_trend, get_similarity_trend, get_dead_docs, get_empty_retrievals, get_ingestion_health, get_prompt_metrics_by_version, get_live_feed
from services.auth_service import get_current_user_from_supabase

admin_router = APIRouter(
    tags=["admin"],
)

@admin_router.get("/traces")
async def fetch_telemetry_traces(
    limit: int = 50,
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Fetch recent traces for Admin UI. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_recent_traces(min(limit, 200))

@admin_router.get("/prompts")
async def fetch_prompts(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return []

@admin_router.get("/evaluations")
async def fetch_evaluations(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return []

@admin_router.get("/kpis")
async def fetch_kpis(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: Dict = Depends(get_current_user_from_supabase),
) -> Dict[str, Any]:
    """Fetch aggregated KPIs for Admin UI. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    return await get_kpis(from_date, to_date)

@admin_router.get("/models")
async def list_models(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[str]:
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
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Get timeseries data for a metric. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_timeseries_data(metric, from_date, to_date, buckets)

@admin_router.get("/triggers")
async def list_triggers(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List trigger events. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_trigger_events(from_date, to_date)

@admin_router.get("/safety-events")
async def list_safety_events(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List safety events. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_safety_events(from_date, to_date)

@admin_router.get("/topic-clusters")
async def list_topic_clusters(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List topic clusters. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_topic_clusters()

@admin_router.get("/retrieval-health")
async def get_retrieval_health_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: Dict = Depends(get_current_user_from_supabase),
) -> Dict[str, Any]:
    """Get retrieval health metrics. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_retrieval_health(from_date, to_date)

@admin_router.get("/quality-data")
async def get_quality_data_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: Dict = Depends(get_current_user_from_supabase),
) -> Dict[str, Any]:
    """Get quality data metrics. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_quality_data(from_date, to_date)

@admin_router.get("/eval-runs")
async def list_eval_runs(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List evaluation runs. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_eval_runs()

@admin_router.get("/golden-questions")
async def list_golden_questions(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List golden questions. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_golden_questions()

@admin_router.get("/ingestion-runs")
async def list_ingestion_runs(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List ingestion runs. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_ingestion_runs()

@admin_router.get("/alert-rules")
async def list_alert_rules(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List alert rules. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_alert_rules()

@admin_router.get("/alert-events")
async def list_alert_events(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List alert events. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_alert_events()

@admin_router.get("/annotations")
async def list_annotations(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List annotations. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_annotations()

@admin_router.get("/admins")
async def list_admins(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List admin users. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_admins()

@admin_router.get("/model-pricing")
async def list_model_pricing(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """List model pricing. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_model_pricing()

@admin_router.get("/top-failures")
async def get_top_failures(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(8, ge=1, le=100),
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Get top failures by faithfulness. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_top_failures(from_date, to_date, limit)

@admin_router.get("/ragas-heatmap")
async def get_ragas_heatmap(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(8, ge=1, le=100),
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Get RAGAS heatmap data. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_ragas_heatmap(from_date, to_date, buckets)

@admin_router.get("/trigger-trend")
async def get_trigger_trend_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(14, ge=1, le=100),
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Get trigger trend data. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_trigger_trend(from_date, to_date, buckets)

@admin_router.get("/similarity-trend")
async def get_similarity_trend_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    buckets: int = Query(14, ge=1, le=100),
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Get similarity trend data. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_similarity_trend(from_date, to_date, buckets)

@admin_router.get("/dead-docs")
async def get_dead_docs_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Get dead documents. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_dead_docs(from_date, to_date)

@admin_router.get("/empty-retrievals")
async def get_empty_retrievals_endpoint(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Get empty retrievals. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_empty_retrievals(from_date, to_date, limit)

@admin_router.get("/ingestion-health")
async def get_ingestion_health_endpoint(
    user: Dict = Depends(get_current_user_from_supabase),
) -> Dict[str, Any]:
    """Get ingestion health status. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_ingestion_health()

@admin_router.get("/prompt-metrics")
async def get_prompt_metrics_by_version_endpoint(
    user: Dict = Depends(get_current_user_from_supabase),
) -> Any:
    """Get prompt metrics by version. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_prompt_metrics_by_version()

@admin_router.get("/live-feed")
async def poll_live_feed_endpoint(
    user: Dict = Depends(get_current_user_from_supabase),
) -> List[Dict[str, Any]]:
    """Poll live feed. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await get_live_feed()

import httpx
import os
from typing import Any
from pydantic import BaseModel

class AskRequest(BaseModel):
    question: str
    kpi_context: str = ""

@admin_router.post("/ask")
async def ask_admin_question(
    req: AskRequest,
    user: Dict = Depends(get_current_user_from_supabase),
):
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.config import settings
    api_key = settings.sarvam_api_key
    base_url = settings.sarvam_base_url.rstrip("/")
    model = settings.sarvam_cloud_model
    if not api_key:
        raise HTTPException(status_code=500, detail="SARVAM_API_KEY not configured")

    system_prompt = (
        "You are an AI analytics assistant for the AskMukthiGuru admin dashboard. "
        "Answer questions about platform metrics, query volume, latency, costs, "
        "hallucination rates and serene mind triggers. Be concise (2-4 sentences). "
        "If data is unavailable say so — do not fabricate numbers."
    )

    context_block = f"Current platform metrics:\n{req.kpi_context}\n\n" if req.kpi_context else ""
    user_message = f"{context_block}{req.question}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "api-subscription-key": api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 200,
                    "temperature": 0.3
                },
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            return {"response": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
