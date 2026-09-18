"""
OpenTelemetry setup for Mukthi Guru.

Tracing is optional and must never block application startup. Jaeger receives
OTLP spans from FastAPI, LangChain/LangGraph, and manually-instrumented direct
LLM gateways.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

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
