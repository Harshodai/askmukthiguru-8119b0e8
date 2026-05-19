"""
Mukthi Guru — Admin Telemetry Database (Supabase Version)

Provides a persistent cloud-backed database to store query traces,
evaluations, and user feedback via Supabase.
"""

import os
import json
import logging
import re
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def _get_client() -> Client:
    """Initialize Supabase client."""
    if not settings.supabase_key:
        logger.warning("SUPABASE_KEY is not set. Telemetry will be disabled.")
        return None
    return create_client(settings.supabase_url, settings.supabase_key)

async def init_telemetry_db():
    """
    Supabase initialization. 
    In this version, schema is managed by Supabase Migrations.
    """
    logger.info(f"Telemetry initialized using Supabase at {settings.supabase_url}")

class PIIScrubber:
    """Regex-based lightweight PII redaction utility."""
    # Common PII regex patterns
    EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
    # Matches international and local phone numbers
    PHONE_REGEX = re.compile(r'(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}')
    # Matches 12-digit Indian Aadhaar or 16 digit credit cards
    ID_REGEX = re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}([\s-]?\d{4})?\b')

    @classmethod
    def scrub(cls, text: str) -> str:
        if not text:
            return text
        text = cls.EMAIL_REGEX.sub('[EMAIL]', text)
        text = cls.PHONE_REGEX.sub('[PHONE]', text)
        text = cls.ID_REGEX.sub('[ID_NUMBER]', text)
        return text

async def log_query_trace(query_data: dict, response_data: dict) -> None:
    """Log a complete query and response trace to Supabase."""
    client = _get_client()
    if not client:
        return

    try:
        # 1. Insert into chat_queries
        # Map SQLite field names to Supabase schema names if necessary
        # Supabase schema (schema.sql) matches most names
        query_payload = {
            "id": query_data['id'],
            "session_id": query_data.get('session_id'),
            "user_id": query_data.get('user_id'),
            "anon_user_id": query_data.get('anon_user_id'),
            "query_text": PIIScrubber.scrub(query_data['query_text']),
            "model": query_data.get('model'),
            "latency_ms": query_data.get('latency_ms', 0),
            "status": query_data.get('status', 'ok'),
            "created_at": query_data['created_at']
        }
        
        # Filter out None values to let Postgres defaults kick in
        query_payload = {k: v for k, v in query_payload.items() if v is not None}
        
        # 0. Ensure session exists in chat_sessions
        try:
            session_payload = {
                "id": query_payload["session_id"],
                "user_id": query_payload.get("user_id"),
                "anon_user_id": query_payload.get("anon_user_id"),
                "started_at": query_payload["created_at"]
            }
            session_payload = {k: v for k, v in session_payload.items() if v is not None}
            client.table("chat_sessions").upsert(session_payload).execute()
        except Exception as e:
            logger.warning(f"Upserting session failed: {e}")

        client.table("chat_queries").insert(query_payload).execute()
        
        # 2. Insert into chat_responses
        response_payload = {
            "id": response_data['id'],
            "query_id": query_data['id'],
            "response_text": response_data['response_text'],
            "citations": response_data.get('citations', []),
            "faithfulness": response_data.get('faithfulness', 0.0),
            "answer_relevancy": response_data.get('answer_relevancy', 0.0),
            "context_precision": response_data.get('context_precision', 0.0),
            "context_recall": response_data.get('context_recall', 0.0),
            "hallucination_flag": bool(response_data.get('hallucination_flag')),
            "judge_reasoning": response_data.get('judge_reasoning', ''),
            "created_at": response_data.get('created_at', query_data['created_at'])
        }
        
        response_payload = {k: v for k, v in response_payload.items() if v is not None}
        
        client.table("chat_responses").insert(response_payload).execute()
        
        # 3. Log Retrieval Event (if any)
        retrieval = query_data.get("retrieval_metadata")
        if retrieval:
            retrieval_payload = {
                "query_id": query_data['id'],
                "chunk_ids": retrieval.get("chunk_ids", []),
                "source_docs": retrieval.get("source_docs", []),
                "scores": retrieval.get("scores", []),
                "top_k": retrieval.get("top_k", 0),
                "retrieval_hit": retrieval.get("hit", False)
            }
            client.table("retrieval_events").insert(retrieval_payload).execute()
            
        # 4. Log Triggers (e.g. Distress Detection)
        triggers = query_data.get("trigger_events", [])
        if triggers:
            trigger_payloads = []
            for t in triggers:
                trigger_payloads.append({
                    "query_id": query_data['id'],
                    "trigger_name": t.get("name"),
                    "metadata": t.get("metadata", {}),
                    "created_at": query_data['created_at']
                })
            client.table("trigger_events").insert(trigger_payloads).execute()
        
        logger.debug(f"Successfully logged trace {query_data['id']} to Supabase")
        
    except Exception as e:
        logger.error(f"Failed to log telemetry trace to Supabase: {e}")

async def get_recent_traces(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent traces for Admin UI from Supabase."""
    client = _get_client()
    if not client:
        return []

    try:
        # Join chat_queries with chat_responses
        response = client.table("chat_queries").select(
            "*, chat_responses(*)"
        ).order("created_at", desc=True).limit(limit).execute()
        
        traces = []
        for row in response.data:
            # Flatten response data for UI compatibility
            res_data = row.pop("chat_responses", [])
            if res_data and len(res_data) > 0:
                row.update(res_data[0])
            traces.append(row)
            
        return traces
    except Exception as e:
        logger.error(f"Failed to fetch traces from Supabase: {e}")
        return []
async def get_kpis(from_date: Optional[str] = None, to_date: Optional[str] = None) -> Dict[str, Any]:
    """Fetch aggregated KPI snapshot from Supabase."""
    client = _get_client()
    if not client:
        return {
            "total_queries": 0, "total_seekers": 0, "p50_latency_ms": 0, "p95_latency_ms": 0,
            "hallucination_rate": 0, "serene_mind_trigger_rate": 0, "thumbs_up_rate": 0,
            "estimated_cost_usd": 0, "error_rate": 0
        }

    try:
        # 1. Total queries
        query = client.table("chat_queries").select("id", count="exact")
        if from_date: query = query.gte("created_at", from_date)
        if to_date: query = query.lte("created_at", to_date)
        total_queries = query.execute().count or 0

        # 2. Total seekers (unique anon_user_id or user_id)
        # Simplified: count unique user_ids if available, otherwise anon
        seeker_query = client.table("chat_queries").select("user_id", count="exact")
        if from_date: seeker_query = seeker_query.gte("created_at", from_date)
        total_seekers = seeker_query.execute().count or 0

        # 3. Latency and Errors
        # We fetch last 1000 to compute percentiles locally (Supabase free tier lacks complex agg)
        metric_query = client.table("chat_queries").select("latency_ms, status")
        if from_date: metric_query = metric_query.gte("created_at", from_date)
        metric_query = metric_query.order("created_at", desc=True).limit(1000)
        metrics = metric_query.execute().data or []

        latencies = [m["latency_ms"] for m in metrics if m.get("latency_ms")]
        errors = [m for m in metrics if m.get("status") == "error"]
        
        import statistics
        p50 = statistics.median(latencies) if latencies else 0
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0)
        error_rate = len(errors) / len(metrics) if metrics else 0

        # 4. Hallucination rate from chat_responses
        resp_query = client.table("chat_responses").select("hallucination_flag")
        if from_date: resp_query = resp_query.gte("created_at", from_date)
        resps = resp_query.execute().data or []
        hallucinations = [r for r in resps if r.get("hallucination_flag")]
        hallucination_rate = len(hallucinations) / len(resps) if resps else 0

        # 5. Serene Mind trigger rate
        trigger_query = client.table("trigger_events").select("id", count="exact").eq("trigger_name", "DISTRESS")
        if from_date: trigger_query = trigger_query.gte("created_at", from_date)
        total_triggers = trigger_query.execute().count or 0
        trigger_rate = total_triggers / total_queries if total_queries > 0 else 0

        return {
            "total_queries": total_queries,
            "total_seekers": total_seekers,
            "p50_latency_ms": int(p50),
            "p95_latency_ms": int(p95),
            "hallucination_rate": hallucination_rate,
            "serene_mind_trigger_rate": trigger_rate,
            "thumbs_up_rate": 0.85, # TODO: implement feedback table query
            "estimated_cost_usd": total_queries * 0.0012, # Simplified estimate
            "error_rate": error_rate
        }
    except Exception as e:
        logger.error(f"Failed to aggregate KPIs from Supabase: {e}")
        return {
            "total_queries": 0, "total_seekers": 0, "p50_latency_ms": 0, "p95_latency_ms": 0,
            "hallucination_rate": 0, "serene_mind_trigger_rate": 0, "thumbs_up_rate": 0,
            "estimated_cost_usd": 0, "error_rate": 0
        }

async def log_ingestion_run(run_data: dict) -> None:
    """Log an ingestion run attempt and result to Supabase."""
    client = _get_client()
    if not client:
        return

    try:
        payload = {
            "id": run_data.get("id"),
            "source": run_data.get("source"),
            "chunks_added": run_data.get("chunks_added", 0),
            "embedding_model": run_data.get("embedding_model"),
            "duration_ms": run_data.get("duration_ms", 0),
            "status": run_data.get("status", "ok"),
            "error_log": run_data.get("error_log"),
            "created_at": run_data.get("created_at")
        }
        # Filter out None values to let Postgres defaults kick in
        payload = {k: v for k, v in payload.items() if v is not None}
        client.table("ingestion_runs").insert(payload).execute()
        logger.info(f"Successfully logged ingestion run {run_data.get('id')} to Supabase")
    except Exception as e:
        logger.error(f"Failed to log ingestion run to Supabase: {e}")
