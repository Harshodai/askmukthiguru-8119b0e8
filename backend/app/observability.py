"""
OpenTelemetry setup for Mukthi Guru.

Tracing is optional and must never block application startup. Jaeger receives
OTLP spans from FastAPI, LangChain/LangGraph, and manually-instrumented direct
LLM gateways.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

_INITIALIZED = False

# Trace only the serving routes (chat, chat stream, first-person); everything else is noise.
DEFAULT_FASTAPI_EXCLUDED_URLS = (
    r"^(?!.*\/api\/(?:chat(?:\/stream)?|first-person\/query)(?:\?.*)?$).*"
)

try:
    from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
except ImportError:
    class SpanProcessor:  # type: ignore[no-redef]
        def on_start(self, span: Any, parent_context: Any = None) -> None:
            pass

        def on_end(self, span: Any) -> None:
            pass

        def shutdown(self) -> None:
            pass

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True

    class ReadableSpan:  # type: ignore[no-redef]
        pass

    class Span:  # type: ignore[no-redef]
        pass


# ---------------------------------------------------------------------------
# Privacy Redaction & Telemetry Sanitization Contract (SPEC-quality-observability)
# ---------------------------------------------------------------------------

SAFE_METADATA_ALLOWLIST: frozenset[str] = frozenset({
    # Correlation & identity-free IDs
    "trace_id",
    "span_id",
    "parent_id",
    "query_id",
    "correlation_id",
    "session_id",
    "request_id",
    # HTTP & networking
    "http.status_code",
    "http.route",
    "http.method",
    "http.target",
    "http.scheme",
    "http.flavor",
    "http.user_agent",
    "http.host",
    "net.host.name",
    "net.host.port",
    "net.peer.name",
    "net.peer.port",
    "net.transport",
    "route",
    "route_name",
    "route_decision",
    "endpoint",
    "path",
    # Query class & routing intent
    "query_class",
    "query_tier",
    "tier",
    "intent",
    "on_device_intent",
    "requested_variant",
    "selected_variant",
    "detected_cache_tier",
    "normalized_query_tier",
    "decision_method",
    "policy_version",
    # Service & system metadata
    "service.name",
    "service.version",
    "service.instance.id",
    "telemetry.sdk.name",
    "telemetry.sdk.version",
    "telemetry.sdk.language",
    "model",
    "model_name",
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.operation.name",
    "gen_ai.retry_reason",
    # Token counts & cost metrics
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.cached_input_tokens",
    "gen_ai.usage.total_tokens",
    "gen_ai.usage.cost",
    "llm.token_count.prompt",
    "llm.token_count.completion",
    "llm.token_count.total",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "token_count",
    # Timings & latency
    "latency_ms",
    "duration_ms",
    "duration",
    "elapsed_ms",
    "start_ms",
    "end_ms",
    "start_time",
    "end_time",
    # Quality & evaluation scores
    "faithfulness",
    "faithfulness_score",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "hallucination_flag",
    "confidence",
    "cost_estimate",
    "cost_usd",
    "actual_cost_usd",
    "score",
    "top_k",
    "sample_count",
    "sample_size",
    "failure_rate",
    "points_count",
    # Status & reasons
    "status",
    "status_code",
    "grounding_state",
    "gate_status",
    "abstain_reason",
    "error.type",
    "success",
    "passed",
    # Versions & hashes
    "version",
    "prompt_version_id",
    "corpus_version",
    "schema_version",
    "dataset_version",
    "model_version",
    "hash",
    "split_hash",
    "dataset_hash",
    "content_hash",
    "corpus_hash",
    "lineage_hash",
    "transcript_hash",
    "fingerprint",
})

SAFE_KEY_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"^http\.[a-z_.]+$", re.IGNORECASE),
    re.compile(r"^net\.[a-z_.]+$", re.IGNORECASE),
    re.compile(r"^gen_ai\.(?:usage|system|request|response|operation|retry)\b", re.IGNORECASE),
    re.compile(r"^llm\.token_count\b", re.IGNORECASE),
    re.compile(r".*_(?:tokens|ms|seconds|count|score|version|hash|tier|status)$", re.IGNORECASE),
)

SENSITIVE_BLOCKLIST: frozenset[str] = frozenset({
    # Raw prompts & user input
    "input.value",
    "output.value",
    "prompt",
    "prompts",
    "raw_prompt",
    "raw_prompts",
    "input",
    "inputs",
    "user_input",
    "query_text",
    "input_text",
    "seeker_query",
    # Raw responses, completions & answers
    "response",
    "responses",
    "raw_response",
    "raw_responses",
    "completion",
    "completions",
    "answer",
    "teaching",
    "response_text",
    "answer_text",
    "final_answer",
    # Transcripts
    "transcript",
    "transcripts",
    "raw_transcript",
    "transcript_text",
    "audio_transcript",
    # Retrieved documents & content
    "retrieval.documents",
    "retrieved_documents",
    "retrieved_text",
    "retrieved_document_text",
    "document_content",
    "doc_text",
    "chunk_text",
    "passage_text",
    "documents",
    "source_docs",
    "source_text",
    "context_text",
    # Credentials & secrets
    "credentials",
    "credential",
    "password",
    "passwords",
    "passwd",
    "secret",
    "secrets",
    "secret_key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "auth_header",
    "auth_token",
    "access_token",
    "refresh_token",
    "bearer_token",
    "cookie",
    "set-cookie",
    "token",
    # Internal safety state & seeker identities
    "internal_safety_state",
    "hidden_safety_state",
    "safety_state",
    "safety_events",
    "user_id",
    "seeker_id",
    "user_identity",
    "identity",
})

BLOCKLIST_PREFIXES: tuple[str, ...] = (
    "input.value",
    "output.value",
    "llm.prompts",
    "llm.completions",
    "llm.input_messages",
    "llm.output_messages",
    "retrieval.documents",
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.content.",
)

_SENTINEL_REGEX = re.compile(r"sentinel[_\-\w]*", re.IGNORECASE)
_AUTH_HEADER_REGEX = re.compile(r"(?:bearer|basic)\s+[^\s,;&]+", re.IGNORECASE)
_TOKEN_PARAM_REGEX = re.compile(
    r"(?:token|jwt|api[_-]?key|secret|password|passwd|auth)[=:\s]+[^\s,;&]+",
    re.IGNORECASE,
)
_KEY_PATTERN_REGEX = re.compile(
    r"\b(?:sk-[a-zA-Z0-9_\-]{16,}|ghp_[a-zA-Z0-9]{20,}|ey[a-zA-Z0-9_-]{10,}\.ey[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+)\b",
    re.IGNORECASE,
)


def _is_safe_key(key: str) -> bool:
    if key in SAFE_METADATA_ALLOWLIST:
        return True
    return any(p.search(key) for p in SAFE_KEY_PATTERNS)


def _is_blocked_key(key: str) -> bool:
    if _is_safe_key(key):
        return False
    lower = key.lower()
    if lower in SENSITIVE_BLOCKLIST:
        return True
    if any(lower.startswith(prefix) for prefix in BLOCKLIST_PREFIXES):
        return True
    for term in (
        "password",
        "secret",
        "credential",
        "auth_token",
        "api_key",
        "internal_safety",
        "safety_state",
    ):
        if term in lower:
            return True
    return False


def _is_sensitive_string(val: str) -> bool:
    if not isinstance(val, str) or not val:
        return False
    return bool(
        _SENTINEL_REGEX.search(val)
        or _AUTH_HEADER_REGEX.search(val)
        or _TOKEN_PARAM_REGEX.search(val)
        or _KEY_PATTERN_REGEX.search(val)
    )


def _sanitize_value(val: Any) -> Any:
    if isinstance(val, str):
        if _is_sensitive_string(val):
            return "[REDACTED]"
        return val
    elif isinstance(val, (list, tuple)):
        return [_sanitize_value(item) for item in val]
    elif isinstance(val, dict):
        return sanitize_span_attributes(val)
    return val


def sanitize_span_attributes(attributes: dict[str, Any] | Any) -> dict[str, Any]:
    """Sanitize span attributes before export.

    - Removes blocked keys (input.value, output.value, llm.prompts,
      llm.completions, retrieval.documents, transcript, credentials, etc.).
    - Ensures safe metadata (token counts, route, trace_id, duration, status,
      scores, versions, hashes) are preserved.
    - Replaces sensitive string values matching auth/token/sentinel patterns
      with '[REDACTED]'.
    """
    if not attributes:
        return {}
    sanitized: dict[str, Any] = {}
    for k, v in attributes.items():
        if _is_blocked_key(str(k)):
            continue
        sanitized[k] = _sanitize_value(v)
    return sanitized


class PrivacyRedactionSpanProcessor(SpanProcessor):
    """SpanProcessor that sanitizes span attributes before export.

    Enforces that content-bearing prompts, responses, completions,
    transcripts, retrieved documents, credentials, and internal safety state
    are stripped or redacted, while correlation identifiers, route metadata,
    token counts, and quality scores remain intact.
    """

    ALLOWLIST_KEYS = SAFE_METADATA_ALLOWLIST
    BLOCKLIST_KEYS = SENSITIVE_BLOCKLIST

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        pass

    def on_end(self, span: Any) -> None:
        if hasattr(span, "_attributes") and span._attributes is not None:
            sanitized = self.sanitize_span_attributes(dict(span._attributes))
            try:
                from opentelemetry.attributes import BoundedAttributes

                maxlen = getattr(span._attributes, "maxlen", None)
                span._attributes = BoundedAttributes(maxlen=maxlen, attributes=sanitized)
            except Exception:
                span._attributes = sanitized

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    @staticmethod
    def sanitize_span_attributes(attributes: dict[str, Any] | Any) -> dict[str, Any]:
        return sanitize_span_attributes(attributes)


def _is_enabled() -> bool:
    return os.getenv("OTEL_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _collector_reachable(endpoint: str, timeout: float = 1.5) -> Optional[bool]:
    """Best-effort TCP probe of the OTLP collector.

    AMK-F-001: ``OTEL_ENABLED`` defaults to true and the gRPC exporter connects
    lazily, so ``init_observability`` logged "tracing initialized" and returned
    True whether or not anything was listening. The Jaeger service in
    docker-compose.yml sits behind ``profiles: [observability]`` and therefore
    does not start with a plain ``docker compose up``, so the normal state of
    this system was: tracing reports healthy, every span is dropped, and the
    first person to go looking for a trace during an incident finds nothing.

    Returns True/False, or None when the endpoint could not be parsed (in which
    case we say nothing rather than guess).
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(endpoint if "//" in endpoint else f"//{endpoint}")
    host, port = parsed.hostname, parsed.port
    if not host:
        return None
    if port is None:
        port = 4317
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# LangChainInstrumentor records every LangGraph node's full input/output state
# (retrieved documents included) as span attributes. Uncapped, one export batch
# reached 4.4-10.8 MB (2026-09-26) against the collector's 4 MB gRPC limit, so
# whole batches of traces were dropped. The SDK reads these natively; setdefault
# keeps an operator's own value authoritative.
_EXPORT_SIZE_DEFAULTS = {
    "OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT": "4096",
    "OTEL_BSP_MAX_EXPORT_BATCH_SIZE": "32",
}


def _apply_export_size_defaults() -> None:
    for key, value in _EXPORT_SIZE_DEFAULTS.items():
        os.environ.setdefault(key, value)


def init_observability(app: FastAPI) -> bool:
    """
    Initialize OpenTelemetry tracing.

    Returns True when tracing is active or already initialized. Returns False
    when tracing is disabled, missing optional packages, or initialization fails.
    """
    global _INITIALIZED

    if not _is_enabled():
        logger.info("OpenTelemetry tracing disabled by OTEL_ENABLED=false.")
        return False

    if _INITIALIZED:
        logger.debug("OpenTelemetry tracing already initialized; skipping.")
        return True

    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.info("OpenTelemetry packages not installed; skipping tracing. (%s)", exc)
        return False

    try:
        service_name = os.getenv("OTEL_SERVICE_NAME", "mukthiguru-backend")
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
        excluded_urls = os.getenv(
            "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS",
            DEFAULT_FASTAPI_EXCLUDED_URLS,
        )

        _apply_export_size_defaults()
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(PrivacyRedactionSpanProcessor())
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded_urls)
        LangChainInstrumentor().instrument()

        _INITIALIZED = True
        logger.info(
            "OpenTelemetry tracing initialized: service=%s endpoint=%s excluded_urls=%s",
            service_name,
            endpoint,
            excluded_urls,
        )

        # Say so out loud when the spans have nowhere to go. Tracing that
        # silently discards everything is worse than tracing that is off,
        # because it reads as covered.
        if _collector_reachable(endpoint) is False:
            logger.warning(
                "OpenTelemetry is ENABLED but no OTLP collector is listening at %s — "
                "every span produced by this process will be discarded. "
                "Start one with `docker compose --profile observability up -d jaeger` "
                "(UI on :16686), point OTEL_EXPORTER_OTLP_ENDPOINT at an existing "
                "collector, or set OTEL_ENABLED=false to stop paying for spans "
                "nobody receives.",
                endpoint,
            )
        return True
    except Exception as exc:
        logger.warning("Failed to initialize OpenTelemetry tracing: %s", exc)
        return False
