"""
Mukthi Guru — Admin Telemetry Database (Supabase Version)

Provides a persistent cloud-backed database to store query traces,
evaluations, and user feedback via Supabase.
"""

import os
import json
import logging
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
            "anon_user_id": query_data.get('anon_user_id'),
            "query_text": query_data['query_text'],
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
