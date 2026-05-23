"""
OpenTelemetry setup for Mukthi Guru.

Tracing is optional and must never block application startup. Jaeger receives
OTLP spans from FastAPI, LangChain/LangGraph, and manually-instrumented direct
LLM gateways.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)

_INITIALIZED = False

DEFAULT_FASTAPI_EXCLUDED_URLS = r"^(?!.*\/api\/chat(?:\/stream)?(?:\?.*)?$).*"


def _is_enabled() -> bool:
    return os.getenv("OTEL_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


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

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
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
        return True
    except Exception as exc:
        logger.warning("Failed to initialize OpenTelemetry tracing: %s", exc)
        return False
