"""
Mukthi Guru — Supabase Telemetry Sink

Responsible for logging structured observability and tracing data
(queries, responses, retrievals, spans, and events) to Supabase.
"""

import os
import logging
import asyncio
import uuid
import time
from typing import Any, Dict, List, Optional
from supabase import create_client, Client
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class SupabaseTelemetrySink:
    """Telemetry sink for writing RAG metrics and trace spans to Supabase."""
    
    def __init__(self):
        self.url = settings.supabase_url
        # Support either SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY (which is service_role)
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", settings.supabase_key)
        self.client: Optional[Client] = None
        
        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                logger.info("SupabaseTelemetrySink initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client in telemetry sink: {e}")
        else:
            logger.warning("Supabase URL or Key missing. SupabaseTelemetrySink is disabled.")

    def _sync_insert(self, table: str, payload: Any):
        """Perform a synchronous insert using the Supabase client."""
        if not self.client:
            return
        try:
            self.client.table(table).insert(payload).execute()
        except Exception as e:
            logger.error(f"Failed to insert into {table}: {e}")

    async def log_query_trace(
        self,
        query_id: str,
        session_id: str,
        user_id: str,
        query_text: str,
        model: str,
        latency_ms: int,
        status: str,
        created_at: str,
        response_text: Optional[str] = None,
        citations: Optional[List[str]] = None,
        faithfulness: float = 1.0,
        answer_relevancy: float = 1.0,
        context_precision: float = 1.0,
        context_recall: float = 1.0,
        hallucination_flag: bool = False,
        confidence_score: Optional[float] = None,
        judge_reasoning: str = "",
        retrieval_metadata: Optional[Dict[str, Any]] = None,
        spans: Optional[List[Dict[str, Any]]] = None,
        trigger_events: Optional[List[Dict[str, Any]]] = None,
        safety_events: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Asynchronously write telemetry data into all relevant Supabase tables.
        This runs in an executor to avoid blocking the main async loop.
        """
        if not self.client:
            logger.debug("SupabaseTelemetrySink is disabled, skipping log.")
            return

        # Prepare Payloads
        # 1. chat_queries
        query_payload = {
            "id": query_id,
            "session_id": session_id,
            "user_id": user_id,
            "query_text": query_text,
            "model": model,
            "latency_ms": latency_ms,
            "status": status,
            "created_at": created_at,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_estimate": 0.0
        }
        
        # 2. chat_responses
        response_payload = None
        if response_text is not None:
            response_payload = {
                "id": str(uuid.uuid4()),
                "query_id": query_id,
                "response_text": response_text,
                "citations": citations or [],
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
                "context_precision": context_precision,
                "context_recall": context_recall,
                "hallucination_flag": hallucination_flag,
                "confidence": confidence_score,
                "judge_reasoning": judge_reasoning,
                "created_at": created_at
            }

        # 3. retrieval_events
        retrieval_payload = None
        if retrieval_metadata:
            retrieval_payload = {
                "query_id": query_id,
                "source_docs": retrieval_metadata.get("source_docs", []),
                "scores": retrieval_metadata.get("scores", []),
                "top_k": retrieval_metadata.get("top_k", 0),
                "retrieval_hit": retrieval_metadata.get("hit", False),
                "created_at": created_at
            }

        # 4. trace_spans
        span_payloads = []
        if spans:
            for span in spans:
                span_payloads.append({
                    "query_id": query_id,
                    "span_name": span["span_name"],
                    "start_ms": span["start_ms"],
                    "duration_ms": span["duration_ms"]
                })

        # 5. trigger_events
        trigger_payloads = []
        if trigger_events:
            for te in trigger_events:
                trigger_payloads.append({
                    "query_id": query_id,
                    "trigger_name": te.get("name"),
                    "metadata": te.get("metadata", {}),
                    "created_at": created_at
                })

        # 6. safety_events
        safety_payloads = []
        if safety_events:
            for se in safety_events:
                safety_payloads.append({
                    "query_id": query_id,
                    "event_type": se.get("event_type"),
                    "decision": se.get("decision"),
                    "reason": se.get("reason"),
                    "created_at": created_at
                })

        # Execute inserts in the executor
        def do_inserts():
            try:
                # Insert session dependency if active
                if session_id:
                    session_payload = {
                        "id": session_id,
                        "user_id": user_id,
                        "started_at": created_at
                    }
                    try:
                        self.client.table("chat_sessions").upsert(session_payload).execute()
                    except Exception as e:
                        logger.warning(f"Upserting session failed in sink (non-fatal): {e}")

                # 1. Insert chat_queries
                self.client.table("chat_queries").insert(query_payload).execute()
                
                # 2. Insert chat_responses
                if response_payload:
                    self.client.table("chat_responses").insert(response_payload).execute()
                
                # 3. Insert retrieval_events
                if retrieval_payload:
                    # Clean payload keys if needed to match DB schema (e.g. check for chunk_ids if present)
                    self.client.table("retrieval_events").insert(retrieval_payload).execute()
                    
                # 4. Insert trace_spans
                if span_payloads:
                    self.client.table("trace_spans").insert(span_payloads).execute()
                    
                # 5. Insert trigger_events
                if trigger_payloads:
                    self.client.table("trigger_events").insert(trigger_payloads).execute()
                    
                # 6. Insert safety_events
                if safety_payloads:
                    self.client.table("safety_events").insert(safety_payloads).execute()
                    
                logger.info(f"Successfully logged query trace {query_id} to Supabase via Telemetry Sink.")
            except Exception as e:
                logger.error(f"Telemetry Sink insert operation failed: {e}")

        # Run in executor
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, do_inserts)
