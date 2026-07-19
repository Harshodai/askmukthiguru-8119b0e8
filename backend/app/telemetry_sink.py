"""
Mukthi Guru — Supabase Telemetry Sink

Responsible for logging structured observability and tracing data
(queries, responses, retrievals, spans, and events) to Supabase.
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Optional

import redis.asyncio as Redis
from supabase import Client, create_client

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SupabaseTelemetrySink:
    """Telemetry sink for writing RAG metrics and trace spans to Supabase via Redis Streams."""

    def __init__(self):
        self.url = settings.supabase_url
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", settings.supabase_key)
        self.client: Client | None = None
        self.redis_url = getattr(settings, "redis_url", None)
        self.redis = None

        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                logger.info("SupabaseTelemetrySink client initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client in telemetry sink: {e}")
        else:
            logger.warning("Supabase URL or Key missing. SupabaseTelemetrySink is disabled.")

        if self.redis_url:
            try:
                self.redis = Redis.from_url(
                    self.redis_url,
                    socket_connect_timeout=5,
                    socket_timeout=10,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
                logger.info("SupabaseTelemetrySink Redis connection initialized.")
            except Exception as e:
                logger.warning(f"SupabaseTelemetrySink: Failed to initialize Redis connection: {e}")

    def _sync_insert(self, table: str, payload: Any):
        """Perform a synchronous insert using the Supabase client."""
        if not self.client:
            return
        try:
            self.client.table(table).insert(payload).execute()
        except Exception as e:
            logger.error(f"Failed to insert into {table}: {e}")

    def _coerce_uuid(self, val: Any) -> Optional[str]:
        if not val:
            return None
        val_str = str(val).strip()
        try:
            return str(uuid.UUID(val_str))
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, val_str))

    def _stable_child_id(self, query_id: str, logical: str) -> str:
        """Deterministic UUID for a trace child row, derived from the parent
        trace id plus a logical event identity (e.g. 'response'). The worker is
        at-least-once, so a re-processed telemetry message must not create a
        second row: a stable id + upsert makes the write idempotent, unlike the
        previous per-attempt uuid4() which duplicated on every replay."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{query_id}:{logical}"))

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
        citations: Optional[list[str]] = None,
        faithfulness: float = 1.0,
        answer_relevancy: float = 1.0,
        context_precision: float = 1.0,
        context_recall: float = 1.0,
        hallucination_flag: bool = False,
        confidence_score: Optional[float] = None,
        judge_reasoning: str = "",
        retrieval_metadata: Optional[dict[str, Any]] = None,
        spans: Optional[list[dict[str, Any]]] = None,
        trigger_events: Optional[list[dict[str, Any]]] = None,
        safety_events: Optional[list[dict[str, Any]]] = None,
        provider: Optional[str] = None,
        route_decision: Optional[str] = None,
        cache_hit: Optional[bool] = None,
        ttft_ms: Optional[int] = None,
        tokens_per_second: Optional[float] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        cost_estimate: Optional[float] = None,
        evaluation_trace: Optional[dict[str, Any]] = None,
        assistant_slug: Optional[str] = None,
    ) -> None:
        """
        Serialize trace data and append to Redis Stream.
        Falls back to direct DB insert if Redis is unavailable.
        """
        query_id = self._coerce_uuid(query_id) or str(uuid.uuid4())
        session_id = self._coerce_uuid(session_id)
        user_id = self._coerce_uuid(user_id)

        payload_dict = {
            "query_id": query_id,
            "session_id": session_id,
            "user_id": user_id,
            "query_text": query_text,
            "model": model,
            "latency_ms": latency_ms,
            "status": status,
            "created_at": created_at,
            "response_text": response_text,
            "citations": citations,
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_precision": context_precision,
            "context_recall": context_recall,
            "hallucination_flag": hallucination_flag,
            "confidence_score": confidence_score,
            "judge_reasoning": judge_reasoning,
            "retrieval_metadata": retrieval_metadata,
            "spans": spans,
            "trigger_events": trigger_events,
            "safety_events": safety_events,
            "provider": provider,
            "route_decision": route_decision,
            "cache_hit": cache_hit,
            "ttft_ms": ttft_ms,
            "tokens_per_second": tokens_per_second,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_estimate": cost_estimate,
            "evaluation_trace": evaluation_trace,
            "assistant_slug": assistant_slug,
        }

        if self.redis:
            try:
                serialized_payload = json.dumps(payload_dict, default=str)
                await self.redis.xadd("telemetry:stream", {"payload": serialized_payload})
                logger.debug(f"Queued query trace {query_id} into Redis Stream 'telemetry:stream'.")
                return
            except Exception as e:
                logger.warning(
                    f"Failed to queue trace to Redis Stream: {e}. Falling back to direct DB insert."
                )

        # Fallback to direct insertion
        await self.log_query_trace_direct(payload_dict)

    async def log_query_trace_direct(self, payload_dict: dict) -> None:
        """
        Asynchronously write telemetry data into all relevant Supabase tables.
        This runs in an executor to avoid blocking the main async loop.
        """
        if not self.client:
            logger.debug("SupabaseTelemetrySink is disabled, skipping log.")
            return

        # Unpack the common payload dict for backward-compatibility with the rest of the method
        p = payload_dict
        query_id = self._coerce_uuid(p.get("query_id")) or str(uuid.uuid4())
        # Local aliases from payload so the rest of the code can keep using the flat names
        session_id = self._coerce_uuid(p.get("session_id"))
        user_id = self._coerce_uuid(p.get("user_id"))
        query_text = p.get("query_text")
        model = p.get("model")
        latency_ms = p.get("latency_ms")
        status = p.get("status")
        created_at = p.get("created_at")
        response_text = p.get("response_text")
        citations = p.get("citations")
        faithfulness = p.get("faithfulness", 1.0)
        answer_relevancy = p.get("answer_relevancy", 1.0)
        context_precision = p.get("context_precision", 1.0)
        context_recall = p.get("context_recall", 1.0)
        hallucination_flag = p.get("hallucination_flag", False)
        confidence_score = p.get("confidence_score")
        judge_reasoning = p.get("judge_reasoning", "")
        assistant_slug = p.get("assistant_slug")
        provider = p.get("provider")
        route_decision = p.get("route_decision")
        cache_hit = p.get("cache_hit")
        ttft_ms = p.get("ttft_ms")
        tokens_per_second = p.get("tokens_per_second")
        prompt_tokens = p.get("prompt_tokens")
        completion_tokens = p.get("completion_tokens")
        cost_estimate = p.get("cost_estimate")
        evaluation_trace = p.get("evaluation_trace")
        retrieval_metadata = p.get("retrieval_metadata")
        spans = p.get("spans")
        trigger_events = p.get("trigger_events")
        safety_events = p.get("safety_events")

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
            "prompt_tokens": prompt_tokens or 0,
            "completion_tokens": completion_tokens or 0,
            "cost_estimate": cost_estimate or 0.0,
            "provider": provider,
            "route_decision": route_decision,
            "cache_hit": cache_hit,
            "ttft_ms": ttft_ms,
            "tokens_per_second": tokens_per_second,
            "assistant_slug": assistant_slug,
        }
        query_payload = {k: v for k, v in query_payload.items() if v is not None}

        # 2. chat_responses — deterministic id so worker replays (at-least-once)
        # upsert the same row instead of inserting a duplicate every attempt.
        response_payload = None
        if response_text is not None:
            response_payload = {
                "id": self._stable_child_id(query_id, "response"),
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
                "evaluation_trace": evaluation_trace or {},
                "created_at": created_at,
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
            }

        # 4. trace_spans
        span_payloads = []
        if spans:
            for span in spans:
                span_payloads.append(
                    {
                        "query_id": query_id,
                        # DB column is `name` (original schema). main.py uses `span_name` key
                        # in intermediate dicts — normalize here before DB write.
                        "name": span.get("span_name") or span.get("name") or "unknown",
                        "start_ms": span.get("start_ms", 0),
                        "duration_ms": span.get("duration_ms", 0),
                        # attributes column added by migration 20260601090000
                        "attributes": span.get("attributes") or {},
                    }
                )


        # 5. trigger_events
        trigger_payloads = []
        if trigger_events:
            for te in trigger_events:
                trigger_payloads.append(
                    {
                        "query_id": query_id,
                        "trigger_name": te.get("name"),
                        "metadata": te.get("metadata", {}),
                        "created_at": created_at,
                    }
                )

        # 6. safety_events
        safety_payloads = []
        if safety_events:
            for se in safety_events:
                safety_payloads.append(
                    {
                        "query_id": query_id,
                        "rule": se.get("event_type") or "guardrail",
                        "severity": se.get("decision"),
                        "action": se.get("decision"),
                        "details": {"reason": se.get("reason")},
                        "created_at": created_at,
                    }
                )

        # Execute inserts in the executor
        def do_inserts():
            try:
                # Insert session dependency if active
                if session_id:
                    session_payload = {
                        "id": session_id,
                        "user_id": user_id,
                        "started_at": created_at,
                    }
                    try:
                        self.client.table("chat_sessions").upsert(session_payload).execute()
                    except Exception as e:
                        logger.warning(f"Upserting session failed in sink (non-fatal): {e}")

                # 1. Insert chat_queries
                self.client.table("chat_queries").upsert(query_payload).execute()

                # 2. Insert chat_responses (upsert on stable id — idempotent on replay)
                if response_payload:
                    self.client.table("chat_responses").upsert(response_payload).execute()

                # 3. Insert retrieval_events
                if retrieval_payload:
                    # Clean payload keys if needed to match DB schema (e.g. check for chunk_ids if present)
                    self.client.table("retrieval_events").insert(retrieval_payload).execute()

                # 4. Insert trace_spans
                if span_payloads:
                    self.client.table("trace_spans").insert(span_payloads).execute()

                # 5. Insert trigger_events
                if trigger_payloads:
                    try:
                        self.client.table("trigger_events").insert(trigger_payloads).execute()
                    except Exception as e:
                        if "metadata" in str(e) or "payload" in str(e):
                            try:
                                fallback_payloads = []
                                for tp in trigger_payloads:
                                    if "metadata" in tp:
                                        fallback_payloads.append({
                                            "query_id": tp["query_id"],
                                            "trigger_name": tp["trigger_name"],
                                            "trigger_type": "event",
                                            "payload": tp["metadata"],
                                            "created_at": tp["created_at"],
                                        })
                                    else:
                                        fallback_payloads.append({
                                            "query_id": tp["query_id"],
                                            "trigger_name": tp["trigger_name"],
                                            "metadata": tp.get("payload", {}),
                                            "created_at": tp["created_at"],
                                        })
                                self.client.table("trigger_events").insert(fallback_payloads).execute()
                            except Exception as e2:
                                logger.warning(f"Trigger events insert failed with fallback: {e2}")
                        else:
                            logger.warning(f"Trigger events insert failed: {e}")

                # 6. Insert safety_events
                if safety_payloads:
                    try:
                        self.client.table("safety_events").insert(safety_payloads).execute()
                    except Exception as e:
                        try:
                            fallback_payloads = []
                            for sp in safety_payloads:
                                excerpt_val = ""
                                if "details" in sp and isinstance(sp["details"], dict):
                                    excerpt_val = sp["details"].get("reason", "")
                                fallback_payloads.append({
                                    "query_id": sp["query_id"],
                                    "type": sp.get("rule", "guardrail"),
                                    "severity": sp.get("severity"),
                                    "excerpt": excerpt_val,
                                    "created_at": sp.get("created_at"),
                                })
                            self.client.table("safety_events").insert(fallback_payloads).execute()
                        except Exception as e2:
                            logger.warning(f"Safety events insert failed with fallback: {e2}")

                logger.info(
                    f"Successfully logged query trace {query_id} to Supabase via Telemetry Sink."
                )
            except Exception as e:
                logger.error(f"Telemetry Sink insert operation failed: {e}")

        # Run in executor
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, do_inserts)


class TelemetryWorker:
    """Background worker to consume telemetry events from Redis Stream and write to Supabase."""

    def __init__(self, sink: SupabaseTelemetrySink):
        self.sink = sink
        self.running = False
        self._task = None

    def start(self):
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("Telemetry background worker started.")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            logger.info("Telemetry background worker stopped.")

    async def _loop(self):
        logger.info("Starting telemetry consumer loop from 'telemetry:stream'...")
        while self.running:
            try:
                if not self.sink.redis or not self.sink.client:
                    await asyncio.sleep(5)
                    continue

                # Read from the stream (blocking read, timeout 5000ms)
                last_id = await self.sink.redis.get("telemetry:stream:last_id") or "0-0"
                if isinstance(last_id, bytes):
                    last_id = last_id.decode("utf-8")

                streams = await self.sink.redis.xread(
                    {"telemetry:stream": last_id}, count=10, block=5000
                )
                if streams:
                    for _, messages in streams:
                        for msg_id, data in messages:
                            payload_str = data.get(b"payload")
                            if payload_str:
                                try:
                                    payload = json.loads(payload_str.decode("utf-8"))
                                    # Insert directly to Supabase via direct method
                                    await self.sink.log_query_trace_direct(payload)
                                except Exception as parse_err:
                                    logger.error(
                                        f"Worker failed to process telemetry message {msg_id}: {parse_err}"
                                    )

                            # Update last processed ID
                            last_id = (
                                msg_id.decode("utf-8") if isinstance(msg_id, bytes) else msg_id
                            )
                            await self.sink.redis.set("telemetry:stream:last_id", last_id)
                            # Auto-prune stream to prevent infinite Redis memory growth
                            await self.sink.redis.xtrim(
                                "telemetry:stream", maxlen=1000, approximate=True
                            )
                else:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telemetry consumer loop: {e}")
                # Try to reconnect Redis if connection was lost
                if self.sink.redis:
                    try:
                        await self.sink.redis.ping()
                    except Exception:
                        logger.warning("Redis connection lost, attempting to reconnect...")
                        try:
                            self.sink.redis = Redis.from_url(
                                self.sink.redis_url,
                                socket_connect_timeout=5,
                                socket_timeout=10,
                                retry_on_timeout=True,
                                health_check_interval=30,
                            )
                            logger.info("Redis reconnected successfully")
                        except Exception as reconnect_err:
                            logger.error(f"Failed to reconnect Redis: {reconnect_err}")
                await asyncio.sleep(5)
