from __future__ import annotations

"""
Mukthi Guru — Admin Telemetry Database (Supabase Version)

Provides a persistent cloud-backed database to store query traces,
evaluations, and user feedback via Supabase.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
from typing import Any, Optional

from supabase import Client, create_client

from app.config import get_settings
from app.security_utils import validate_iso_date, validate_session_id, validate_user_id

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
    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    # Matches international and local phone numbers
    PHONE_REGEX = re.compile(r"(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
    # Matches 12-digit Indian Aadhaar or 16 digit credit cards
    ID_REGEX = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}([\s-]?\d{4})?\b")

    @classmethod
    def scrub(cls, text: str) -> str:
        if not text:
            return text
        text = cls.EMAIL_REGEX.sub("[EMAIL]", text)
        text = cls.PHONE_REGEX.sub("[PHONE]", text)
        text = cls.ID_REGEX.sub("[ID_NUMBER]", text)
        return text


async def log_query_trace(query_data: dict, response_data: dict) -> None:
    """Log a complete query and response trace to Supabase."""
    client = _get_client()
    if not client:
        return

    try:
        # Validate session_id before any DB use
        raw_session_id = query_data.get("session_id")
        safe_session_id = validate_session_id(raw_session_id)
        safe_user_id = validate_user_id(query_data.get("user_id"))

        # 1. Insert into chat_queries
        query_payload = {
            "id": query_data["id"],
            "session_id": safe_session_id,
            "user_id": safe_user_id,
            "anon_user_id": query_data.get("anon_user_id"),
            "query_text": PIIScrubber.scrub(query_data["query_text"]),
            "model": query_data.get("model"),
            "latency_ms": query_data.get("latency_ms", 0),
            "status": query_data.get("status", "ok"),
            "created_at": query_data["created_at"],
        }

        # Filter out None values to let Postgres defaults kick in
        query_payload = {k: v for k, v in query_payload.items() if v is not None}

        # 0. Ensure session exists in chat_sessions
        try:
            if safe_session_id:
                session_payload = {
                    "id": safe_session_id,
                    "user_id": safe_user_id,
                    "anon_user_id": query_data.get("anon_user_id"),
                    "started_at": query_payload["created_at"],
                }
                session_payload = {k: v for k, v in session_payload.items() if v is not None}
                client.table("chat_sessions").upsert(session_payload).execute()
        except Exception as e:
            logger.warning(f"Upserting session failed: {e}")

        client.table("chat_queries").insert(query_payload).execute()

        # 2. Insert into chat_responses
        response_payload = {
            "id": response_data["id"],
            "query_id": query_data["id"],
            "response_text": response_data["response_text"],
            "citations": response_data.get("citations", []),
            "faithfulness": response_data.get("faithfulness", 0.0),
            "answer_relevancy": response_data.get("answer_relevancy", 0.0),
            "context_precision": response_data.get("context_precision", 0.0),
            "context_recall": response_data.get("context_recall", 0.0),
            "hallucination_flag": bool(response_data.get("hallucination_flag")),
            "judge_reasoning": response_data.get("judge_reasoning", ""),
            "created_at": response_data.get("created_at", query_data["created_at"]),
        }

        response_payload = {k: v for k, v in response_payload.items() if v is not None}

        client.table("chat_responses").insert(response_payload).execute()

        # 3. Log Retrieval Event (if any)
        retrieval = query_data.get("retrieval_metadata")
        if retrieval:
            retrieval_payload = {
                "query_id": query_data["id"],
                "chunk_ids": retrieval.get("chunk_ids", []),
                "source_docs": retrieval.get("source_docs", []),
                "scores": retrieval.get("scores", []),
                "top_k": retrieval.get("top_k", 0),
                "retrieval_hit": retrieval.get("hit", False),
            }
            client.table("retrieval_events").insert(retrieval_payload).execute()

        # 4. Log Triggers (e.g. Distress Detection)
        triggers = query_data.get("trigger_events", [])
        if triggers:
            trigger_payloads = []
            for t in triggers:
                trigger_payloads.append(
                    {
                        "query_id": query_data["id"],
                        "trigger_name": t.get("name"),
                        "metadata": t.get("metadata", {}),
                        "created_at": query_data["created_at"],
                    }
                )
            client.table("trigger_events").insert(trigger_payloads).execute()

        logger.debug(f"Successfully logged trace {query_data['id']} to Supabase")

    except Exception as e:
        logger.error(f"Failed to log telemetry trace to Supabase: {e}")


async def get_recent_traces(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch recent traces for Admin UI from Supabase."""
    client = _get_client()
    if not client:
        return []

    try:
        # Join chat_queries with chat_responses
        response = (
            client.table("chat_queries")
            .select("*, chat_responses(*)")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        traces = []
        for row in response.data:
            # Flatten response data for UI compatibility, preserving query id and created_at
            res_data = row.pop("chat_responses", [])
            if res_data and len(res_data) > 0:
                response_item = res_data[0]
                for k, v in response_item.items():
                    if k not in ("id", "created_at"):
                        row[k] = v
                    else:
                        row[f"response_{k}"] = v
            traces.append(row)

        return traces
    except Exception as e:
        logger.error(f"Failed to fetch traces from Supabase: {e}")
        return []


async def get_kpis(from_date: Optional[str] = None, to_date: Optional[str] = None) -> dict[str, Any]:
    """Fetch aggregated KPI snapshot from Supabase."""
    client = _get_client()
    if not client:
        return {
            "total_queries": 0,
            "total_seekers": 0,
            "p50_latency_ms": 0,
            "p95_latency_ms": 0,
            "hallucination_rate": 0,
            "serene_mind_trigger_rate": 0,
            "thumbs_up_rate": 0,
            "estimated_cost_usd": 0,
            "estimated_cost_inr": 0,
            "error_rate": 0,
        }

    try:
        # Validate date parameters before use in DB queries
        safe_from = validate_iso_date(from_date)
        safe_to = validate_iso_date(to_date)

        # 1. Total queries
        query = client.table("chat_queries").select("id", count="exact")
        if safe_from:
            query = query.gte("created_at", safe_from)
        if safe_to:
            query = query.lte("created_at", safe_to)
        total_queries = query.execute().count or 0

        # 2. Total seekers (unique anon_user_id or user_id)
        # Simplified: count unique user_ids if available, otherwise anon
        seeker_query = client.table("chat_queries").select("user_id", count="exact")
        if safe_from:
            seeker_query = seeker_query.gte("created_at", safe_from)
        total_seekers = seeker_query.execute().count or 0

        # 3. Latency and Errors
        # We fetch last 1000 to compute percentiles locally (Supabase free tier lacks complex agg)
        metric_query = client.table("chat_queries").select("latency_ms, status")
        if safe_from:
            metric_query = metric_query.gte("created_at", safe_from)
        metric_query = metric_query.order("created_at", desc=True).limit(1000)
        metrics = metric_query.execute().data or []

        latencies = [m["latency_ms"] for m in metrics if m.get("latency_ms")]
        errors = [m for m in metrics if m.get("status") == "error"]

        import statistics

        p50 = statistics.median(latencies) if latencies else 0
        p95 = (
            statistics.quantiles(latencies, n=20)[18]
            if len(latencies) >= 20
            else (max(latencies) if latencies else 0)
        )
        error_rate = len(errors) / len(metrics) if metrics else 0

        # 4. Hallucination rate from chat_responses
        resp_query = client.table("chat_responses").select("hallucination_flag")
        if safe_from:
            resp_query = resp_query.gte("created_at", safe_from)
        resps = resp_query.execute().data or []
        hallucinations = [r for r in resps if r.get("hallucination_flag")]
        hallucination_rate = len(hallucinations) / len(resps) if resps else 0

        # 5. Serene Mind trigger rate
        trigger_query = (
            client.table("trigger_events")
            .select("id", count="exact")
            .eq("trigger_name", "DISTRESS")
        )
        if safe_from:
            trigger_query = trigger_query.gte("created_at", safe_from)
        total_triggers = trigger_query.execute().count or 0
        trigger_rate = total_triggers / total_queries if total_queries > 0 else 0

        # Sarvam-30B public pricing: ₹2.5 input + ₹10 output per 1M tokens.
        # Until token telemetry is populated, use a conservative 800 input / 350 output token estimate.
        estimated_cost_inr = total_queries * (((800 / 1_000_000) * 2.5) + ((350 / 1_000_000) * 10))

        return {
            "total_queries": total_queries,
            "total_seekers": total_seekers,
            "p50_latency_ms": int(p50),
            "p95_latency_ms": int(p95),
            "hallucination_rate": hallucination_rate,
            "serene_mind_trigger_rate": trigger_rate,
            "thumbs_up_rate": 0.85,  # TODO: implement feedback table query
            "estimated_cost_usd": 0,
            "estimated_cost_inr": estimated_cost_inr,
            "error_rate": error_rate,
        }
    except Exception as e:
        logger.error(f"Failed to aggregate KPIs from Supabase: {e}")
        return {
            "total_queries": 0,
            "total_seekers": 0,
            "p50_latency_ms": 0,
            "p95_latency_ms": 0,
            "hallucination_rate": 0,
            "serene_mind_trigger_rate": 0,
            "thumbs_up_rate": 0,
            "estimated_cost_usd": 0,
            "estimated_cost_inr": 0,
            "error_rate": 0,
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
            "created_at": run_data.get("created_at"),
        }
        # Filter out None values to let Postgres defaults kick in
        payload = {k: v for k, v in payload.items() if v is not None}
        client.table("ingestion_runs").insert(payload).execute()
        logger.info(f"Successfully logged ingestion run {run_data.get('id')} to Supabase")
    except Exception as e:
        logger.error(f"Failed to log ingestion run to Supabase: {e}")


async def get_available_models() -> list[str]:
    """Get list of available LLM models."""
    # For now, return hardcoded list based on what's configured
    # In a real implementation, this might query Ollama or check available models
    models = []
    if settings.ollama_model:
        models.append(settings.ollama_model)
    if settings.sarvam_cloud_model:
        models.append(settings.sarvam_cloud_model)
    # Add some defaults if none configured
    if not models:
        models = ["sarvam-30b", "llama3.2:3b"]
    return models


async def get_timeseries_data(
    metric: str, from_date: str, to_date: str, buckets: int = 24
) -> list[dict[str, Any]]:
    """Get timeseries data for a specific metric."""
    client = _get_client()
    if not client:
        return []

    try:
        # Validate date parameters
        safe_from = validate_iso_date(from_date)
        safe_to = validate_iso_date(to_date)

        # Build query based on metric type
        if metric == "queries":
            query = client.table("chat_queries").select("created_at")
        elif metric == "p50_latency_ms" or metric == "p95_latency_ms":
            query = client.table("chat_queries").select("latency_ms, created_at").eq("status", "ok")
        elif metric == "hallucination_rate":
            query = client.table("chat_responses").select("hallucination_flag, created_at")
        elif metric == "cost_usd":
            query = client.table("chat_queries").select("cost_estimate, created_at")
        elif metric == "thumbs_up_rate":
            # Placeholder - would need feedback table
            query = client.table("chat_queries").select("created_at")
        elif metric == "retrieval_hit_rate":
            # Would need to check if citations exist
            query = client.table("chat_responses").select("citations, created_at")
        else:
            # Default fallback
            query = client.table("chat_queries").select("created_at")

        # Apply date filters
        if safe_from:
            query = query.gte("created_at", safe_from)
        if safe_to:
            query = query.lte("created_at", safe_to)

        # Execute query
        response = query.order("created_at", desc=True).execute()
        data = response.data or []

        if not data:
            return []

        # Bucket the data
        from datetime import datetime

        start_time = datetime.fromisoformat(safe_from.replace("Z", "+00:00")).timestamp()
        end_time = datetime.fromisoformat(safe_to.replace("Z", "+00:00")).timestamp()
        bucket_size = (end_time - start_time) / buckets if buckets > 0 else 0

        buckets_data = []
        for i in range(buckets):
            bucket_start = start_time + (i * bucket_size)
            bucket_start + bucket_size
            bucket_time = datetime.fromtimestamp(bucket_start + (bucket_size / 2)).isoformat()

            buckets_data.append({"bucket": bucket_time, "value": 0, "count": 0})

        # Process data points
        for item in data:
            item_time = datetime.fromisoformat(
                item["created_at"].replace("Z", "+00:00")
            ).timestamp()
            if start_time <= item_time <= end_time:
                bucket_index = int((item_time - start_time) / bucket_size) if bucket_size > 0 else 0
                bucket_index = max(0, min(bucket_index, buckets - 1))

                if metric == "queries":
                    buckets_data[bucket_index]["value"] += 1
                    buckets_data[bucket_index]["count"] += 1
                elif metric == "p50_latency_ms" or metric == "p95_latency_ms":
                    latency = item.get("latency_ms")
                    if latency is not None:
                        buckets_data[bucket_index]["latencies"] = buckets_data[bucket_index].get(
                            "latencies", []
                        ) + [latency]
                        buckets_data[bucket_index]["count"] += 1
                elif metric == "hallucination_rate":
                    hallucination = item.get("hallucination_flag", False)
                    buckets_data[bucket_index]["value"] += 1 if hallucination else 0
                    buckets_data[bucket_index]["count"] += 1
                elif metric == "cost_usd":
                    cost = item.get("cost_estimate", 0)
                    buckets_data[bucket_index]["value"] += cost
                    buckets_data[bucket_index]["count"] += 1
                elif metric == "thumbs_up_rate":
                    # Placeholder
                    buckets_data[bucket_index]["value"] += 0
                    buckets_data[bucket_index]["count"] += 1
                elif metric == "retrieval_hit_rate":
                    citations = item.get("citations", [])
                    hit = len(citations) > 0 if isinstance(citations, list) else False
                    buckets_data[bucket_index]["value"] += 1 if hit else 0
                    buckets_data[bucket_index]["count"] += 1

        # Calculate final values for each bucket
        result = []
        for bucket in buckets_data:
            if bucket["count"] == 0:
                bucket["value"] = 0
            elif metric == "p50_latency_ms":
                latencies = sorted(bucket.get("latencies", []))
                bucket["value"] = latencies[len(latencies) // 2] if latencies else 0
            elif metric == "p95_latency_ms":
                latencies = sorted(bucket.get("latencies", []))
                index = int(len(latencies) * 0.95)
                bucket["value"] = latencies[index] if latencies else 0
            elif metric in ["hallucination_rate", "thumbs_up_rate", "retrieval_hit_rate"]:
                bucket["value"] = bucket["value"] / bucket["count"] if bucket["count"] > 0 else 0
            # For queries and cost_usd, value is already summed

            # Remove temporary fields
            bucket.pop("latencies", None)
            result.append({"bucket": bucket["bucket"], "value": bucket["value"]})

        return result
    except Exception as e:
        logger.error(f"Failed to get timeseries data: {e}")
        return []


async def get_trigger_events(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> list[dict[str, Any]]:
    """Get trigger events."""
    client = _get_client()
    if not client:
        return []

    try:
        query = client.table("trigger_events").select("*")

        if from_date:
            safe_from = validate_iso_date(from_date)
            query = query.gte("created_at", safe_from)
        if to_date:
            safe_to = validate_iso_date(to_date)
            query = query.lte("created_at", safe_to)

        response = query.order("created_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get trigger events: {e}")
        return []


async def get_safety_events(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> list[dict[str, Any]]:
    """Get safety events."""
    client = _get_client()
    if not client:
        return []

    try:
        query = client.table("safety_events").select("*")

        if from_date:
            safe_from = validate_iso_date(from_date)
            query = query.gte("created_at", safe_from)
        if to_date:
            safe_to = validate_iso_date(to_date)
            query = query.lte("created_at", safe_to)

        response = query.order("created_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get safety events: {e}")
        return []


async def get_topic_clusters() -> list[dict[str, Any]]:
    """Get topic clusters."""
    client = _get_client()
    if not client:
        return []

    try:
        # This would ideally come from a clustering service or pre-computed data
        # For now, return empty list as placeholder
        return []
    except Exception as e:
        logger.error(f"Failed to get topic clusters: {e}")
        return []


async def get_retrieval_health(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> dict[str, Any]:
    """Get retrieval health metrics."""
    client = _get_client()
    if not client:
        return {
            "total_retrievals": 0,
            "hit_rate": 0,
            "empty_retrievals": 0,
            "avg_top_score": 0,
            "avg_precision": 0,
            "avg_recall": 0,
            "miss_rate": 0,
            "avg_chunks_per_query": 0,
            "top_missing_topics": [],
            "sources": [],
        }

    try:
        # Validate date parameters
        if from_date:
            safe_from = validate_iso_date(from_date)
        if to_date:
            safe_to = validate_iso_date(to_date)

        # Build query for retrieval events with joins
        query = client.table("retrieval_events").select("*, chat_queries!inner(created_at)")

        if from_date:
            query = query.gte("chat_queries.created_at", safe_from)
        if to_date:
            query = query.lte("chat_queries.created_at", safe_to)

        response = query.execute()
        retrievals = response.data or []

        if not retrievals:
            return {
                "total_retrievals": 0,
                "hit_rate": 0,
                "empty_retrievals": 0,
                "avg_top_score": 0,
                "avg_precision": 0,
                "avg_recall": 0,
                "miss_rate": 0,
                "avg_chunks_per_query": 0,
                "top_missing_topics": [],
                "sources": [],
            }

        # Calculate metrics
        total_retrievals = len(retrievals)
        hit_count = sum(1 for r in retrievals if r.get("retrieval_hit"))
        hit_rate = hit_count / total_retrievals if total_retrievals > 0 else 0

        # Calculate average scores (simplified)
        scores = [r.get("scores", []) for r in retrievals if r.get("scores")]
        avg_top_score = 0.0
        if scores:
            # Flatten and get top scores
            all_scores = [
                score for sublist in scores for score in sublist if isinstance(score, int | float)
            ]
            if all_scores:
                avg_top_score = sum(all_scores) / len(all_scores)

        # Placeholder for precision/recall (would need more complex calculation)
        avg_precision = 0.0
        avg_recall = 0.0
        miss_rate = 1.0 - hit_rate

        # Calculate average chunks per query
        chunk_counts = [len(r.get("chunk_ids", [])) for r in retrievals if r.get("chunk_ids")]
        avg_chunks_per_query = sum(chunk_counts) / len(chunk_counts) if chunk_counts else 0

        # Get top missing topics (placeholder)
        top_missing_topics = []

        # Get sources with average faithfulness (simplified)
        sources = []

        return {
            "total_retrievals": total_retrievals,
            "hit_rate": hit_rate,
            "empty_retrievals": total_retrievals - hit_count,
            "avg_top_score": avg_top_score,
            "avg_precision": avg_precision,
            "avg_recall": avg_recall,
            "miss_rate": miss_rate,
            "avg_chunks_per_query": avg_chunks_per_query,
            "top_missing_topics": top_missing_topics,
            "sources": sources,
        }
    except Exception as e:
        logger.error(f"Failed to get retrieval health: {e}")
        return {
            "total_retrievals": 0,
            "hit_rate": 0,
            "empty_retrievals": 0,
            "avg_top_score": 0,
            "avg_precision": 0,
            "avg_recall": 0,
            "miss_rate": 0,
            "avg_chunks_per_query": 0,
            "top_missing_topics": [],
            "sources": [],
        }


async def get_quality_data(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> dict[str, Any]:
    """Get quality data metrics."""
    client = _get_client()
    if not client:
        return {
            "faithfulness": 0.0,
            "relevancy": 0.0,
            "safety_score": 0.0,
            "manual_review_score": 0.0,
            "disagreements": [],
            "low_confidence": [],
        }

    try:
        # Validate date parameters
        if from_date:
            safe_from = validate_iso_date(from_date)
        if to_date:
            safe_to = validate_iso_date(to_date)

        # Build query for responses with joins
        query = client.table("chat_responses").select("*, chat_queries!inner(created_at)")

        if from_date:
            query = query.gte("chat_queries.created_at", safe_from)
        if to_date:
            query = query.lte("chat_queries.created_at", safe_to)

        response = query.execute()
        responses = response.data or []

        if not responses:
            return {
                "faithfulness": 0.0,
                "relevancy": 0.0,
                "safety_score": 0.0,
                "manual_review_score": 0.0,
                "disagreements": [],
                "low_confidence": [],
            }

        # Calculate average faithfulness and relevancy
        faithfulness_scores = [
            r.get("faithfulness", 0)
            for r in responses
            if isinstance(r.get("faithfulness"), int | float)
        ]
        relevancy_scores = [
            r.get("answer_relevancy", 0)
            for r in responses
            if isinstance(r.get("answer_relevancy"), int | float)
        ]

        avg_faithfulness = (
            sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0.0
        )
        avg_relevancy = sum(relevancy_scores) / len(relevancy_scores) if relevancy_scores else 0.0

        # Safety score placeholder (would come from guardrails)
        safety_score = 0.99

        # Manual review score placeholder
        manual_review_score = 0.85

        # Discoveries and low confidence (placeholders)
        disagreements = []
        low_confidence = []

        return {
            "faithfulness": avg_faithfulness,
            "relevancy": avg_relevancy,
            "safety_score": safety_score,
            "manual_review_score": manual_review_score,
            "disagreements": disagreements,
            "low_confidence": low_confidence,
        }
    except Exception as e:
        logger.error(f"Failed to get quality data: {e}")
        return {
            "faithfulness": 0.0,
            "relevancy": 0.0,
            "safety_score": 0.0,
            "manual_review_score": 0.0,
            "disagreements": [],
            "low_confidence": [],
        }


async def get_eval_runs() -> list[dict[str, Any]]:
    """Get evaluation runs."""
    client = _get_client()
    if not client:
        return []

    try:
        response = client.table("eval_runs").select("*").order("started_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get eval runs: {e}")
        return []


async def get_golden_questions() -> list[dict[str, Any]]:
    """Get golden questions."""
    client = _get_client()
    if not client:
        return []

    try:
        response = client.table("golden_questions").select("*").execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get golden questions: {e}")
        return []


async def get_ingestion_runs() -> list[dict[str, Any]]:
    """Get ingestion runs."""
    client = _get_client()
    if not client:
        return []

    try:
        response = (
            client.table("ingestion_runs").select("*").order("created_at", desc=True).execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get ingestion runs: {e}")
        return []


async def get_alert_rules() -> list[dict[str, Any]]:
    """Get alert rules."""
    client = _get_client()
    if not client:
        return []

    try:
        response = client.table("alert_rules").select("*").execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get alert rules: {e}")
        return []


async def get_alert_events() -> list[dict[str, Any]]:
    """Get alert events."""
    client = _get_client()
    if not client:
        return []

    try:
        response = client.table("alert_events").select("*").order("fired_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get alert events: {e}")
        return []


async def get_annotations() -> list[dict[str, Any]]:
    """Get annotations."""
    client = _get_client()
    if not client:
        return []

    try:
        response = client.table("annotations").select("*").order("created_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get annotations: {e}")
        return []


async def get_admins() -> list[dict[str, Any]]:
    """Get admin users."""
    client = _get_client()
    if not client:
        return []

    try:
        # Join user_roles with auth_users to get email
        response = (
            client.table("user_roles")
            .select("*, auth_users:user_id(email)")
            .eq("role", "admin")
            .execute()
        )
        data = response.data or []

        result = []
        for row in data:
            result.append(
                {
                    "id": row.get("user_id"),
                    "email": row.get("auth_users", {}).get("email", "Unknown")
                    if row.get("auth_users")
                    else "Unknown",
                    "role": row.get("role"),
                    "created_at": row.get("created_at", "2024-01-01T00:00:00Z"),
                }
            )
        return result
    except Exception as e:
        logger.error(f"Failed to get admins: {e}")
        return []


async def get_model_pricing() -> list[dict[str, Any]]:
    """Get model pricing."""
    client = _get_client()
    if not client:
        return []

    try:
        response = client.table("model_pricing").select("*").execute()
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to get model pricing: {e}")
        return []


async def get_top_failures(
    from_date: Optional[str] = None, to_date: Optional[str] = None, limit: int = 8
) -> list[dict[str, Any]]:
    """Get top failures by faithfulness."""
    client = _get_client()
    if not client:
        return []

    try:
        # Build query for responses with joins
        query = client.table("chat_responses").select("*, chat_queries!inner(*)")

        if from_date:
            safe_from = validate_iso_date(from_date)
            query = query.gte("chat_queries.created_at", safe_from)
        if to_date:
            safe_to = validate_iso_date(to_date)
            query = query.lte("chat_queries.created_at", safe_to)

        # Filter for low faithfulness and relevancy, then sort
        response = query.execute()
        responses = response.data or []

        # Filter out entries with null faithfulness or relevancy
        valid_responses = [
            r
            for r in responses
            if r.get("faithfulness") is not None and r.get("answer_relevancy") is not None
        ]

        # Sort by combined score (faithfulness + relevancy) ascending
        valid_responses.sort(key=lambda x: x.get("faithfulness", 0) + x.get("answer_relevancy", 0))

        # Take top limit
        top_failures = valid_responses[:limit]

        # Format for frontend
        result = []
        for failure in top_failures:
            query_data = failure.get("chat_queries", {})
            result.append(
                {
                    "query_id": failure.get("query_id"),
                    "query_text": query_data.get("query_text", "Unknown query"),
                    "faithfulness": failure.get("faithfulness", 0),
                    "answer_relevancy": failure.get("answer_relevancy", 0),
                    "created_at": failure.get("created_at"),
                    "reason": "Low faithfulness score",
                }
            )

        return result
    except Exception as e:
        logger.error(f"Failed to get top failures: {e}")
        return []


def _parse_dt(value: Optional[str]) -> datetime | None:
    if not value:
        return None
    safe = validate_iso_date(value)
    return datetime.fromisoformat(safe.replace("Z", "+00:00"))


def _parse_range_start(value: Optional[str], days: int) -> datetime:
    parsed = _parse_dt(value)
    if parsed:
        return parsed
    return datetime.now(UTC) - timedelta(days=days)


def _parse_range_end(value: Optional[str]) -> datetime:
    parsed = _parse_dt(value)
    if parsed:
        return parsed
    return datetime.now(UTC)


def _bucket_rows(
    rows: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    buckets: int,
    time_key: str,
) -> list[dict[str, Any]]:
    buckets = max(1, buckets)
    width = max((end - start).total_seconds() / buckets, 1)
    out = [
        {"bucket": (start + timedelta(seconds=i * width)).isoformat(), "items": []}
        for i in range(buckets)
    ]
    for row in rows:
        raw = row.get(time_key)
        if not raw:
            continue
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        idx = int((ts - start).total_seconds() / width)
        idx = min(max(idx, 0), buckets - 1)
        out[idx]["items"].append(row)
    return out


async def get_ragas_heatmap(
    from_date: Optional[str] = None, to_date: Optional[str] = None, buckets: int = 8
) -> list[dict[str, Any]]:
    """Get RAGAS heatmap data."""
    client = _get_client()
    if not client:
        return []

    metrics = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
    try:
        start = _parse_range_start(from_date, days=7)
        end = _parse_range_end(to_date)
        query = (
            client.table("chat_responses")
            .select("faithfulness, answer_relevancy, context_precision, context_recall, created_at")
            .gte("created_at", start.isoformat())
            .lte("created_at", end.isoformat())
        )
        rows = query.execute().data or []
        bucketed = _bucket_rows(rows, start, end, buckets, "created_at")
        out: list[dict[str, Any]] = []
        for bucket in bucketed:
            for metric in metrics:
                vals = [
                    float(r.get(metric) or 0) for r in bucket["items"] if r.get(metric) is not None
                ]
                out.append(
                    {
                        "bucket": bucket["bucket"],
                        "metric": metric,
                        "value": sum(vals) / len(vals) if vals else 0,
                        "count": len(vals),
                    }
                )
        return out
    except Exception as e:
        logger.error(f"Failed to get RAGAS heatmap: {e}")
        return []


async def get_trigger_trend(
    from_date: Optional[str] = None, to_date: Optional[str] = None, buckets: int = 14
) -> list[dict[str, Any]]:
    """Get trigger trend data."""
    client = _get_client()
    if not client:
        return []

    try:
        start = _parse_range_start(from_date, days=buckets)
        end = _parse_range_end(to_date)
        rows = (
            client.table("trigger_events")
            .select("trigger_name, trigger_type, created_at")
            .gte("created_at", start.isoformat())
            .lte("created_at", end.isoformat())
            .execute()
            .data
            or []
        )
        bucketed = _bucket_rows(rows, start, end, buckets, "created_at")
        out = []
        for bucket in bucketed:
            point: dict[str, Any] = {"bucket": bucket["bucket"]}
            for row in bucket["items"]:
                name = row.get("trigger_name") or row.get("trigger_type") or "unknown"
                point[name] = point.get(name, 0) + 1
            out.append(point)
        return out
    except Exception as e:
        logger.error(f"Failed to get trigger trend: {e}")
        return []


async def get_similarity_trend(
    from_date: Optional[str] = None, to_date: Optional[str] = None, buckets: int = 14
) -> list[dict[str, Any]]:
    """Get similarity trend data."""
    client = _get_client()
    if not client:
        return []

    try:
        start = _parse_range_start(from_date, days=buckets)
        end = _parse_range_end(to_date)
        rows = (
            client.table("retrieval_events")
            .select("scores, chat_queries!inner(created_at)")
            .gte("chat_queries.created_at", start.isoformat())
            .lte("chat_queries.created_at", end.isoformat())
            .execute()
            .data
            or []
        )
        for row in rows:
            row["bucket_created_at"] = (row.get("chat_queries") or {}).get("created_at")
        bucketed = _bucket_rows(rows, start, end, buckets, "bucket_created_at")
        out = []
        for bucket in bucketed:
            scores = []
            for row in bucket["items"]:
                row_scores = row.get("scores") or []
                if row_scores:
                    scores.append(float(row_scores[0] or 0))
            out.append(
                {
                    "bucket": bucket["bucket"],
                    "avg_top_score": sum(scores) / len(scores) if scores else 0,
                }
            )
        return out
    except Exception as e:
        logger.error(f"Failed to get similarity trend: {e}")
        return []


async def get_dead_docs(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> list[dict[str, Any]]:
    """Get dead documents."""
    client = _get_client()
    if not client:
        return []

    try:
        docs = client.table("document_registry").select("source").execute().data or []
    except Exception:
        # No document registry exists in the current schema, so this metric cannot
        # be computed truthfully. Return an empty list instead of fabricated rows.
        return []

    try:
        query = client.table("retrieval_events").select("source_docs")
        if from_date:
            query = query.gte("created_at", validate_iso_date(from_date))
        if to_date:
            query = query.lte("created_at", validate_iso_date(to_date))
        rows = query.execute().data or []
        retrieved = {src for row in rows for src in (row.get("source_docs") or [])}
        return [
            {"source": row.get("source")}
            for row in docs
            if row.get("source") and row.get("source") not in retrieved
        ]
    except Exception as e:
        logger.error(f"Failed to get dead docs: {e}")
        return []


async def get_empty_retrievals(
    from_date: Optional[str] = None, to_date: Optional[str] = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Get empty retrievals."""
    client = _get_client()
    if not client:
        return []

    try:
        # Build query for responses with no citations
        query = client.table("chat_responses").select("*, chat_queries!inner(*)")

        if from_date:
            safe_from = validate_iso_date(from_date)
            query = query.gte("chat_queries.created_at", safe_from)
        if to_date:
            safe_to = validate_iso_date(to_date)
            query = query.lte("chat_queries.created_at", safe_to)

        response = query.execute()
        responses = response.data or []

        # Filter for empty citations
        empty_responses = [
            r
            for r in responses
            if not r.get("citations")
            or (isinstance(r.get("citations"), list) and len(r.get("citations")) == 0)
        ]

        # Take top limit
        top_empty = empty_responses[:limit]

        # Format for frontend
        result = []
        for empty in top_empty:
            query_data = empty.get("chat_queries", {})
            result.append(
                {
                    "query_id": empty.get("query_id"),
                    "query_text": query_data.get("query_text", "Unknown query"),
                    "created_at": empty.get("created_at"),
                }
            )

        return result
    except Exception as e:
        logger.error(f"Failed to get empty retrievals: {e}")
        return []


async def get_ingestion_health() -> dict[str, Any]:
    """Get ingestion health status."""
    client = _get_client()
    if not client:
        return {
            "status": "unknown",
            "last_run": "",
            "indexed_docs": 0,
            "failed_docs": 0,
            "total_runs": 0,
            "ok": 0,
            "partial": 0,
            "failed": 0,
            "total_chunks": 0,
        }

    try:
        response = client.table("ingestion_runs").select("*").execute()
        runs = response.data or []

        indexed_docs = 0
        failed_docs = 0
        total_runs = len(runs)
        ok = 0
        partial = 0
        failed = 0
        total_chunks = 0
        last_run = ""

        for run in runs:
            status = run.get("status", "").lower()
            chunks = run.get("chunks_added", 0)
            run_time = run.get("created_at", "")

            total_chunks += chunks

            if status == "ok":
                ok += 1
                indexed_docs += chunks
            elif status == "partial":
                partial += 1
                indexed_docs += chunks
            elif status == "failed":
                failed += 1
                failed_docs += chunks

            if run_time and (not last_run or run_time > last_run):
                last_run = run_time

        # Determine overall status
        if failed > 0:
            status = "degraded"
        elif total_runs > 0:
            status = "healthy"
        else:
            status = "unknown"

        if not last_run:
            last_run = datetime.now().isoformat()

        return {
            "status": status,
            "last_run": last_run,
            "indexed_docs": indexed_docs,
            "failed_docs": failed_docs,
            "total_runs": total_runs,
            "ok": ok,
            "partial": partial,
            "failed": failed,
            "total_chunks": total_chunks,
        }
    except Exception as e:
        logger.error(f"Failed to get ingestion health: {e}")
        return {
            "status": "unknown",
            "last_run": "",
            "indexed_docs": 0,
            "failed_docs": 0,
            "total_runs": 0,
            "ok": 0,
            "partial": 0,
            "failed": 0,
            "total_chunks": 0,
        }


async def get_prompt_metrics_by_version() -> Any:
    """Get prompt metrics by version."""
    client = _get_client()
    if not client:
        return []

    try:
        prompts = client.table("prompt_versions").select("*").execute().data or []
        queries = (
            client.table("chat_queries")
            .select("prompt_version_id, latency_ms, chat_responses(faithfulness, answer_relevancy)")
            .execute()
            .data
            or []
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in queries:
            key = row.get("prompt_version_id")
            if key:
                grouped.setdefault(key, []).append(row)

        out = []
        for prompt in prompts:
            rows = grouped.get(prompt.get("id"), [])
            faith = []
            rel = []
            latencies = []
            for row in rows:
                if row.get("latency_ms") is not None:
                    latencies.append(float(row["latency_ms"]))
                for response in row.get("chat_responses") or []:
                    if response.get("faithfulness") is not None:
                        faith.append(float(response["faithfulness"]))
                    if response.get("answer_relevancy") is not None:
                        rel.append(float(response["answer_relevancy"]))
            out.append(
                {
                    "prompt_version_id": prompt.get("id"),
                    "name": prompt.get("name"),
                    "version": prompt.get("version"),
                    "active": prompt.get("active"),
                    "query_count": len(rows),
                    "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
                    "avg_faithfulness": sum(faith) / len(faith) if faith else 0,
                    "avg_answer_relevancy": sum(rel) / len(rel) if rel else 0,
                }
            )
        return out
    except Exception as e:
        logger.error(f"Failed to get prompt metrics: {e}")
        return []


async def get_live_feed() -> list[dict[str, Any]]:
    """Get live feed (recent queries)."""
    return await get_recent_traces(limit=10)


async def get_query_trace(query_id: str) -> Optional[dict[str, Any]]:
    """Fetch a complete query trace by query_id from Supabase."""
    client = _get_client()
    if not client:
        return None

    try:
        # Fetch the query
        query_resp = client.table("chat_queries").select("*").eq("id", query_id).execute()
        if not query_resp.data:
            return None
        query = query_resp.data[0]

        # Fetch corresponding response
        response_resp = (
            client.table("chat_responses").select("*").eq("query_id", query_id).execute()
        )
        response = response_resp.data[0] if response_resp.data else None

        # Fetch retrieval events
        retrieval_resp = (
            client.table("retrieval_events").select("*").eq("query_id", query_id).execute()
        )
        retrieval = retrieval_resp.data[0] if retrieval_resp.data else None

        # Fetch spans
        spans_resp = (
            client.table("trace_spans")
            .select("*")
            .eq("query_id", query_id)
            .order("start_ms")
            .execute()
        )
        spans = []
        for span in spans_resp.data or []:
            if "name" not in span and span.get("span_name"):
                span["name"] = span["span_name"]
            spans.append(span)

        # Fetch triggers
        triggers_resp = (
            client.table("trigger_events").select("*").eq("query_id", query_id).execute()
        )
        triggers = triggers_resp.data or []

        # Fetch safety events
        safety_resp = client.table("safety_events").select("*").eq("query_id", query_id).execute()
        safety = safety_resp.data or []

        return {
            "query": query,
            "prompt": None,
            "retrieval": retrieval,
            "response": response,
            "spans": spans,
            "triggers": triggers,
            "feedback": None,
            "safety": safety,
        }
    except Exception as e:
        logger.error(f"Failed to get query trace {query_id}: {e}")
        return None
