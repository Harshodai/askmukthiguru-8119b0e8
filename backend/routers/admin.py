from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.telemetry_db import get_recent_traces
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
    from_date: str = None,
    to_date: str = None,
    user: Dict = Depends(get_current_user_from_supabase),
) -> Dict[str, Any]:
    """Fetch aggregated KPIs for Admin UI. Requires admin authentication."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from app.telemetry_db import get_kpis
    return await get_kpis(from_date, to_date)

import httpx
import os
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
    
    api_key = os.environ.get("SARVAM_API_KEY")
    base_url = os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai/v1").rstrip("/")
    model = os.environ.get("SARVAM_CLOUD_MODEL", "sarvam-30b")
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
                    "Authorization": f"Bearer {api_key}",
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
