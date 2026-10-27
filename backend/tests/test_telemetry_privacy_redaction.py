"""Tests for Telemetry Privacy & Data Redaction (SPEC-quality-observability Story 9).

Verifies that:
1. `sanitize_span_attributes` strips content-bearing prompts, responses, completions,
   retrieved document text, transcripts, credentials, tokens, and internal safety state.
2. Allowlisted operational metadata (token counts, route, trace_id, duration, status,
   scores, versions, hashes) is preserved.
3. String values containing sensitive auth headers, API tokens, or sentinel values
   are replaced with `[REDACTED]`.
4. `PrivacyRedactionSpanProcessor` sanitizes spans before export when used with an
   `InMemorySpanExporter`, while preserving trace correlation (trace ID and span ID).
5. `init_observability` registers `PrivacyRedactionSpanProcessor` before the export processor.
"""

from __future__ import annotations

from typing import Any
from fastapi import FastAPI
import pytest

from app.observability import (
    PrivacyRedactionSpanProcessor,
    init_observability,
    sanitize_span_attributes,
)


# ---------------------------------------------------------------------------
# Unit tests: sanitize_span_attributes
# ---------------------------------------------------------------------------

def test_sanitize_span_attributes_strips_sensitive_keys():
    """Blocked keys (prompts, completions, documents, transcripts, credentials) must be stripped."""
    sensitive_attrs: dict[str, Any] = {
        # Raw prompts & user input
        "input.value": "SENTINEL_SECRET_PROMPT_123",
        "prompt": "SENTINEL_SECRET_PROMPT_123",
        "raw_prompt": "SENTINEL_SECRET_PROMPT_123",
        "llm.prompts": ["SENTINEL_SECRET_PROMPT_123"],
        "llm.prompts.0": "SENTINEL_SECRET_PROMPT_123",
        "llm.input_messages.0.message.content": "SENTINEL_SECRET_PROMPT_123",
        "gen_ai.prompt": "SENTINEL_SECRET_PROMPT_123",
        # Raw completions & responses
        "output.value": "SENTINEL_SECRET_COMPLETION_456",
        "response": "SENTINEL_SECRET_COMPLETION_456",
        "raw_response": "SENTINEL_SECRET_COMPLETION_456",
        "completion": "SENTINEL_SECRET_COMPLETION_456",
        "llm.completions": ["SENTINEL_SECRET_COMPLETION_456"],
        "llm.completions.0": "SENTINEL_SECRET_COMPLETION_456",
        "llm.output_messages.0.message.content": "SENTINEL_SECRET_COMPLETION_456",
        "gen_ai.completion": "SENTINEL_SECRET_COMPLETION_456",
        # Transcripts
        "transcript": "SENTINEL_TRANSCRIPT_XYZ",
        "raw_transcript": "SENTINEL_TRANSCRIPT_XYZ",
        "audio_transcript": "SENTINEL_TRANSCRIPT_XYZ",
        # Retrieved documents & content
        "retrieval.documents": [{"page_content": "SENTINEL_DOC_TEXT_001"}],
        "retrieval.documents.0.document.content": "SENTINEL_DOC_TEXT_001",
        "retrieved_documents": ["SENTINEL_DOC_TEXT_001"],
        "document_content": "SENTINEL_DOC_TEXT_001",
        "chunk_text": "SENTINEL_DOC_TEXT_001",
        # Credentials, passwords & tokens
        "credentials": "SENTINEL_SECRET_CREDENTIALS_KEY",
        "password": "SENTINEL_SECRET_PASSWORD_123",
        "secret": "SENTINEL_SECRET_TOKEN_456",
        "token": "SENTINEL_AUTH_TOKEN_789",
        "api_key": "SENTINEL_API_KEY_ABC",
        "authorization": "Bearer SENTINEL_AUTH_TOKEN",
        # Safety state & seeker identities
        "internal_safety_state": {"intent": "self_harm", "confidence": 0.99},
        "hidden_safety_state": {"rule_triggered": "crisis"},
        "user_id": "usr_sentinel_12345",
        "seeker_id": "skr_sentinel_67890",
    }

    sanitized = sanitize_span_attributes(sensitive_attrs)

    # Every blocked sensitive key must be completely stripped
    for key in sensitive_attrs:
        assert key not in sanitized, f"Expected blocked key '{key}' to be stripped"

    # No sentinel text may survive in any key or value
    sanitized_str = str(sanitized)
    assert "SENTINEL" not in sanitized_str, "Sensitive sentinel leaked into sanitized attributes"


def test_sanitize_span_attributes_preserves_allowlisted_metadata():
    """Allowlisted operational metadata must be retained verbatim."""
    safe_attrs: dict[str, Any] = {
        # Correlation identifiers
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "span_id": "00f067aa0ba902b7",
        "parent_id": "5fb397be34d23b0f",
        "query_id": "qid_12345",
        # HTTP & Route
        "http.status_code": 200,
        "http.route": "/api/chat",
        "http.method": "POST",
        "http.target": "/api/chat",
        "route": "chat",
        "route_name": "api_chat",
        "route_decision": "direct_answer",
        # Token counts
        "prompt_tokens": 42,
        "completion_tokens": 84,
        "total_tokens": 126,
        "llm.token_count.prompt": 42,
        "llm.token_count.completion": 84,
        "llm.token_count.total": 126,
        "gen_ai.usage.input_tokens": 42,
        "gen_ai.usage.output_tokens": 84,
        "gen_ai.usage.total_tokens": 126,
        "gen_ai.usage.cost": 0.0035,
        # Timings
        "latency_ms": 182.4,
        "duration_ms": 182.4,
        "start_ms": 1000.0,
        "end_ms": 1182.4,
        # Scores & Quality metrics
        "faithfulness": 0.95,
        "faithfulness_score": 0.95,
        "answer_relevancy": 0.91,
        "context_precision": 0.88,
        "context_recall": 0.94,
        "hallucination_flag": False,
        "confidence": 0.96,
        "cost_estimate": 0.0035,
        "cost_usd": 0.0035,
        "score": 0.92,
        "top_k": 5,
        # Query classification & Intent
        "query_class": "spiritual_inquiry",
        "query_tier": "fast",
        "tier": "fast",
        "intent": "QUERY",
        "model": "google/gemini-2.5-flash",
        "gen_ai.system": "openrouter",
        "gen_ai.request.model": "google/gemini-2.5-flash",
        "gen_ai.response.model": "google/gemini-2.5-flash",
        # Status & Reason
        "status": "ok",
        "status_code": 200,
        "grounding_state": "grounded",
        "gate_status": "pass",
        "success": True,
        # Versions & Hashes
        "version": "1.0.0",
        "prompt_version_id": "pv_guru_v1",
        "corpus_version": "fp-context-transcript-v2",
        "schema_version": "v2",
        "hash": "e3b0c44298fc1c149afbf4c8996fb924",
        "split_hash": "a1b2c3d4e5f6",
        "transcript_hash": "f6e5d4c3b2a1",
    }

    sanitized = sanitize_span_attributes(safe_attrs)

    for key, expected_value in safe_attrs.items():
        assert key in sanitized, f"Expected safe key '{key}' to be preserved"
        assert sanitized[key] == expected_value, f"Mismatch for '{key}': {sanitized[key]} != {expected_value}"


def test_sanitize_span_attributes_redacts_auth_and_sentinel_patterns():
    """String values matching auth tokens, credentials, or sentinels in retained keys must be redacted."""
    attrs_with_sensitive_strings: dict[str, Any] = {
        "http.route": "/api/chat",
        "custom_meta": "SENTINEL_CUSTOM_METADATA_VALUE",
        "authorization_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "basic_auth": "Basic dXNlcm5hbWU6cGFzc3dvcmQ=",
        "query_param_token": "token=my_secret_access_token_12345",
        "custom_key_ref": "sk-proj-12345678901234567890abcdef",
    }

    sanitized = sanitize_span_attributes(attrs_with_sensitive_strings)

    assert sanitized["http.route"] == "/api/chat"
    assert sanitized["custom_meta"] == "[REDACTED]"
    assert sanitized["authorization_header"] == "[REDACTED]"
    assert sanitized["basic_auth"] == "[REDACTED]"
    assert sanitized["query_param_token"] == "[REDACTED]"
    assert sanitized["custom_key_ref"] == "[REDACTED]"

    assert "SENTINEL" not in str(sanitized)


def test_sanitize_span_attributes_handles_empty_and_nested_structures():
    """Verify empty dict, None, and nested collections with sentinels are handled safely."""
    assert sanitize_span_attributes({}) == {}
    assert sanitize_span_attributes(None) == {}

    nested_attrs = {
        "http.status_code": 200,
        "tags": ["prod", "SENTINEL_TAG_SECRET"],
        "details": {
            "prompt": "SENTINEL_NESTED_PROMPT",  # blocked key inside dict -> stripped
            "secret_note": "SENTINEL_SECRET_NOTE",  # blocked key containing secret -> stripped
            "safe_metric": 42,
            "custom_note": "Bearer SENTINEL_NESTED_BEARER",  # retained key with auth value -> redacted
        },
    }

    sanitized = sanitize_span_attributes(nested_attrs)
    assert sanitized["http.status_code"] == 200
    assert sanitized["tags"] == ["prod", "[REDACTED]"]
    assert "prompt" not in sanitized["details"]
    assert "secret_note" not in sanitized["details"]
    assert sanitized["details"]["safe_metric"] == 42
    assert sanitized["details"]["custom_note"] == "[REDACTED]"
    assert "SENTINEL" not in str(sanitized)


# ---------------------------------------------------------------------------
# Integration tests: PrivacyRedactionSpanProcessor with InMemorySpanExporter
# ---------------------------------------------------------------------------

def test_privacy_redaction_span_processor_with_in_memory_exporter():
    """Exported spans must have sensitive attributes stripped while trace ID, span ID, and safe metadata remain."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = TracerProvider()
    exporter = InMemorySpanExporter()

    # Add PrivacyRedactionSpanProcessor before the exporting processor
    provider.add_span_processor(PrivacyRedactionSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("test.privacy.redaction")

    with tracer.start_as_current_span("chat_flow") as span:
        # Sensitive attributes with unique sentinels
        span.set_attribute("input.value", "SENTINEL_SECRET_PROMPT_123")
        span.set_attribute("output.value", "SENTINEL_SECRET_COMPLETION_456")
        span.set_attribute("prompt", "SENTINEL_SECRET_PROMPT_123")
        span.set_attribute("transcript", "SENTINEL_TRANSCRIPT_XYZ")
        span.set_attribute("credentials", "SENTINEL_SECRET_CREDENTIALS")
        span.set_attribute("internal_safety_state", "crisis_bypass_attempt")

        # Allowlisted safe metadata
        span.set_attribute("http.route", "/api/chat")
        span.set_attribute("http.status_code", 200)
        span.set_attribute("prompt_tokens", 18)
        span.set_attribute("completion_tokens", 36)
        span.set_attribute("llm.token_count.prompt", 18)
        span.set_attribute("llm.token_count.completion", 36)
        span.set_attribute("latency_ms", 95.5)
        span.set_attribute("status", "ok")
        span.set_attribute("faithfulness_score", 0.97)

        # Retained key with sensitive value pattern
        span.set_attribute("note", "Bearer SENTINEL_TOKEN_ABC")

    finished_spans = exporter.get_finished_spans()
    assert len(finished_spans) == 1
    finished = finished_spans[0]

    # Verify trace context correlation survives
    assert finished.context.trace_id != 0
    assert finished.context.span_id != 0

    exported_attributes = dict(finished.attributes)

    # Sensitive attributes must be stripped
    assert "input.value" not in exported_attributes
    assert "output.value" not in exported_attributes
    assert "prompt" not in exported_attributes
    assert "transcript" not in exported_attributes
    assert "credentials" not in exported_attributes
    assert "internal_safety_state" not in exported_attributes

    # Safe metadata must remain intact
    assert exported_attributes["http.route"] == "/api/chat"
    assert exported_attributes["http.status_code"] == 200
    assert exported_attributes["prompt_tokens"] == 18
    assert exported_attributes["completion_tokens"] == 36
    assert exported_attributes["llm.token_count.prompt"] == 18
    assert exported_attributes["llm.token_count.completion"] == 36
    assert exported_attributes["latency_ms"] == 95.5
    assert exported_attributes["status"] == "ok"
    assert exported_attributes["faithfulness_score"] == 0.97

    # Sensitive value in retained key was redacted
    assert exported_attributes["note"] == "[REDACTED]"

    # Absolute proof: no sentinel string survived anywhere in exported attributes
    assert "SENTINEL" not in str(exported_attributes)


# ---------------------------------------------------------------------------
# Integration tests: init_observability registration
# ---------------------------------------------------------------------------

def test_init_observability_registers_privacy_redaction_processor(monkeypatch):
    """init_observability must register PrivacyRedactionSpanProcessor before BatchSpanProcessor."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from app import observability

    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setattr(observability, "_INITIALIZED", False)
    monkeypatch.setattr(observability, "_collector_reachable", lambda *a, **kw: False)

    app = FastAPI()
    result = init_observability(app)
    assert result is True

    provider = trace.get_tracer_provider()
    try:
        active_processors = provider._active_span_processor._span_processors

        # Verify PrivacyRedactionSpanProcessor is registered
        privacy_processors = [p for p in active_processors if isinstance(p, PrivacyRedactionSpanProcessor)]
        assert len(privacy_processors) == 1, "PrivacyRedactionSpanProcessor was not registered in TracerProvider"

        # Verify PrivacyRedactionSpanProcessor precedes BatchSpanProcessor
        processor_types = [type(p) for p in active_processors]
        privacy_idx = processor_types.index(PrivacyRedactionSpanProcessor)
        batch_idx = processor_types.index(BatchSpanProcessor)
        assert privacy_idx < batch_idx, "PrivacyRedactionSpanProcessor must run before BatchSpanProcessor"
    finally:
        provider.shutdown()
