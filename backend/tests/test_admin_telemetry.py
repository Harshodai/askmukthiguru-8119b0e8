from app.admin_telemetry import operations_snapshot, trace_detail, trace_summary


def test_trace_summary_allowlists_operational_fields_only():
    summary = trace_summary(
        {
            "id": "trace-1",
            "query_text": "private seeker question",
            "session_id": "private-session",
            "latency_ms": 123,
            "status": "ok",
            "response_text": "private answer",
            "judge_reasoning": "private reviewer note",
            "faithfulness": 0.9,
            "spans": [{"name": "retrieve", "duration_ms": 20, "attributes": {"secret": 1}}],
        }
    )

    assert summary == {
        "id": "trace-1",
        "latency_ms": 123,
        "status": "ok",
        "faithfulness": 0.9,
        "spans": [{"name": "retrieve", "duration_ms": 20}],
    }


def test_trace_detail_removes_content_sources_and_identifiers():
    detail = trace_detail(
        {
            "query": {"id": "trace-1", "query_text": "private", "session_id": "session", "model": "google/gemini"},
            "response": {"response_text": "private", "judge_reasoning": "private", "confidence": 0.8},
            "retrieval": {"top_k": 4, "source_docs": ["private-source"], "scores": [0.9]},
            "spans": [{"name": "generate", "duration_ms": 40, "attributes": {"prompt": "private"}}],
            "triggers": [{"trigger_name": "cache", "metadata": {"content": "private"}}],
            "safety": [{"severity": "low", "excerpt": "private"}],
        }
    )

    rendered = repr(detail)
    assert "private" not in rendered
    assert "session" not in rendered
    assert detail["retrieval"] == {"top_k": 4}
    assert detail["response"] == {"confidence": 0.8}


def test_operations_snapshot_is_aggregate_and_versioned():
    snapshot = operations_snapshot(
        [{"id": "one", "status": "ok", "latency_ms": 100, "cost_estimate": 0.01}],
        model_policy_id="gemini-flash-budget-v1",
        budget_guard_enabled=False,
    )

    assert snapshot["sample_size"] == 1
    assert snapshot["average_latency_ms"] == 100.0
    assert snapshot["model_policy_id"] == "gemini-flash-budget-v1"
    assert snapshot["budget_guard_enabled"] is False
