"""Evidence rules of the graded capture runner (plan item F4, 2026-10-31)."""

from __future__ import annotations

import pytest

from scripts.ops.graded_capture import (
    CITATION_IDENTITY_FIELDS,
    _ask,
    build_row,
    cache_proof,
    refuse_if_evidence_exists,
    stamp_row,
    validity,
)


def test_a_cache_proof_that_says_cached_or_unreachable_blocks_the_run():
    assert cache_proof(0, "caches empty").ok
    assert not cache_proof(1, "2 exact-cache keys present").ok
    # exit 2 is "unreachable": unknown is not empty, so it must not pass
    assert not cache_proof(2, "redis unreachable").ok
    assert cache_proof(0, "").ok is True  # exit 0 is the prover's contract; output may be empty


def test_a_run_id_with_a_log_is_never_overwritten(tmp_path):
    run = tmp_path / "run1"
    run.mkdir()
    refuse_if_evidence_exists(run)  # empty directory is fine
    (run / "backend.log").write_text("evidence")
    with pytest.raises(FileExistsError):
        refuse_if_evidence_exists(run)


def test_existing_rows_or_manifest_also_block_a_rerun(tmp_path):
    for name in ("rows.jsonl", "manifest.json"):
        run = tmp_path / name.split(".")[0]
        run.mkdir()
        (run / name).write_text("{}")
        with pytest.raises(FileExistsError):
            refuse_if_evidence_exists(run)


def test_rows_are_stamped_with_commit_container_and_run():
    row = stamp_row({"id": "q1"}, sha="abc123", container_id="c0ffee", run_id="r1")
    assert (row["sha"], row["container_id"], row["run_id"]) == ("abc123", "c0ffee", "r1")


def test_row_keeps_server_latency_next_to_wall_clock():
    result = {
        "response": "A clip.",
        "route_decision": "first_person_bridge",
        "model_used": None,
        "latency_ms": 5321,
        "citations": [{"text_snippet": "A clip.", "speaker": "Sri Krishnaji", "url": "u"}],
        "safety_notices": ["n"],
    }
    row = build_row({"id": "q1", "question": "q"}, result, 202, 6.2)
    assert row["latency_ms"] == 5321 and row["sec"] == 6.2
    assert row["citations"][0]["speaker"] == "Sri Krishnaji"
    assert row["notices"] == ["n"]


def test_a_served_row_records_the_identity_of_the_point_it_served():
    """H-26: point/span identity is kept per citation, not only the URL."""
    result = {
        "response": "A clip.",
        "route_decision": "first_person_bridge",
        "citations": [
            {
                "text_snippet": "A clip.",
                "url": "https://youtu.be/x?t=10",
                "point_id": "5f0c1e9a-1d2b-4c3d-8e4f-000000000001",
                "source_span_id": "span-7",
                "start_ms": 10000,
                "end_ms": 22000,
                "completeness_status": "complete",
                "boundary_status": "clean",
            }
        ],
    }
    row = build_row({"id": "q1", "question": "q"}, result, 200, 6.2)
    citation = row["citations"][0]
    assert citation["point_id"].endswith("0001")
    assert citation["source_span_id"] == "span-7"
    assert (citation["start_ms"], citation["end_ms"]) == (10000, 22000)
    assert citation["completeness_status"] == "complete"
    assert citation["boundary_status"] == "clean"
    assert row["citation_fields_unavailable"] == []


def test_missing_identity_fields_are_named_not_invented():
    """The current public projection carries none of them; the row says so."""
    result = {
        "response": "A clip.",
        "route_decision": "first_person_bridge",
        "citations": [{"text_snippet": "A clip.", "url": "u", "start_ms": 10000}],
    }
    row = build_row({"id": "q1", "question": "q"}, result, 200, 6.2)
    citation = row["citations"][0]
    assert citation["start_ms"] == 10000
    assert citation["point_id"] is None and citation["source_span_id"] is None
    assert row["citation_fields_unavailable"] == sorted(
        f for f in CITATION_IDENTITY_FIELDS if f != "start_ms"
    )


def test_an_abstained_row_claims_no_missing_citation_fields():
    row = build_row({"id": "q1", "question": "q"}, {"response": "abstain"}, 200, 1.0)
    assert row["citations"] == []
    assert row["citation_fields_unavailable"] == []


def test_a_run_whose_log_shows_a_blocked_llm_is_invalid():
    bad = "Answerability check indeterminate (timeout/error): OpenRouter spend limit reached"
    verdict = validity(bad, (1.0, 2.0), (3.0, 4.0), preflight_ok=True)
    assert verdict["valid"] is False and verdict["reasons"]
    assert verdict["spend_after"] == {"day": 3.0, "month": 4.0}


def test_a_clean_log_and_a_passing_preflight_make_a_valid_run():
    assert validity("all good\n", (1.0, 2.0), (1.5, 2.5), preflight_ok=True)["valid"] is True
    assert validity("all good\n", (1.0, 2.0), (1.5, 2.5), preflight_ok=False)["valid"] is False


def test_the_frozen_116_are_labelled_a_tuning_set():
    from scripts.ops.graded_capture import _items

    items = _items(include_frozen=True, include_unanswerable=False)
    assert items and all(i["split"] == "tuning" for i in items)


def test_the_benchmark_items_are_onboarded():
    from scripts.ops.graded_capture import _items

    items = _items(include_frozen=False, include_unanswerable=False, include_benchmarks=True)
    assert len(items) == 52
    assert all(i["set"] == "benchmark" for i in items)
    on_topic = [i for i in items if i["kind"] == "on_topic"]
    compound = [i for i in items if i["kind"] == "compound"]
    ooc = [i for i in items if i["kind"] == "out_of_corpus"]
    assert len(on_topic) == 29
    assert len(compound) == 10
    assert len(ooc) == 13


def test_the_approved_bar_file_is_consistent():
    import json
    from pathlib import Path

    bar = json.loads(
        (
            Path(__file__).resolve().parents[2] / "evals/first_person/grading_pass_bar.json"
        ).read_text()
    )
    assert bar["approved"] is True and bar["approved_by"] == "Harsha"
    assert bar["min_showable_rate"] == 0.85 and bar["max_harmful"] == 0
    assert bar["p95_latency_s"] == 10


# ── Auth error detection and invalidation in capture logs ────────────────────


def test_log_with_openrouter_401_auth_error_is_invalid():
    bad = (
        "INFO: Started server\n"
        "ERROR: OpenRouter auth error (401) during generate (model=anthropic/claude-3.5-haiku) — graceful degradation\n"
        "INFO: 200 OK"
    )
    verdict = validity(bad, (1.0, 2.0), (3.0, 4.0), preflight_ok=True)
    assert verdict["valid"] is False
    assert any("auth error" in r.lower() for r in verdict["reasons"])


def test_log_with_openrouter_403_auth_error_is_invalid():
    bad = "OpenRouter auth error (403) during generate — graceful degradation"
    verdict = validity(bad, (1.0, 2.0), (3.0, 4.0), preflight_ok=True)
    assert verdict["valid"] is False
    assert any("auth error" in r.lower() for r in verdict["reasons"])


def test_log_with_openrouter_unauthorized_error_is_invalid():
    bad = "OpenRouter error 401 Unauthorized: {'error': {'message': 'User not found', 'code': 401}}"
    verdict = validity(bad, (1.0, 2.0), (3.0, 4.0), preflight_ok=True)
    assert verdict["valid"] is False


def test_log_with_authentication_error_is_invalid():
    bad = "httpx.HTTPStatusError: AuthenticationError: Invalid API key provided"
    verdict = validity(bad, (1.0, 2.0), (3.0, 4.0), preflight_ok=True)
    assert verdict["valid"] is False


def test_check_log_clean_detects_auth_errors_explicitly():
    from scripts.ops.graded_capture import check_log_clean

    check = check_log_clean("2026-11-08 ERROR OpenRouter auth error (401) during chat")
    assert check.ok is False
    assert "auth error" in check.detail.lower()


def test_the_question_bank_items_are_onboarded_as_strings():
    from scripts.ops.graded_capture import _items

    items = _items(
        include_frozen=False,
        include_unanswerable=False,
        include_benchmarks=False,
        include_question_bank=True,
    )
    assert len(items) == 421
    assert all(i["set"] == "question_bank" for i in items)
    assert all(isinstance(i["question"], str) for i in items)
    assert all(len(i["id"]) > 3 for i in items)
    # verify only the intentional empty probe is empty
    empty_q = [i for i in items if not i["question"]]
    assert len(empty_q) == 1
    assert empty_q[0]["category"] == "malformed_input"


def test_manifest_flags_never_carry_a_secret_value(monkeypatch):
    """The manifest is evidence that gets shared. A key must not reach it (graded-run handoff, 2026-11-12)."""
    import json

    from scripts.ops import graded_capture

    secret = "sk-or-v1-NOT-A-REAL-KEY"

    def fake_run(cmd, *a, **k):
        if cmd[:2] == ["docker", "inspect"]:
            return json.dumps(
                [{"Id": "abc123def456789", "Image": "sha256:x", "State": {"StartedAt": "t"}}]
            )
        return f"OPENROUTER_API_KEY={secret}\nOPENROUTER_BASE_URL=https://example.test\nFIRST_PERSON_ACTIVE_COLLECTION=first_person_v10\n"

    monkeypatch.setattr(graded_capture, "_run", fake_run)
    facts = graded_capture._container_facts("backend")
    assert secret not in json.dumps(facts)
    assert facts["flags"]["OPENROUTER_API_KEY"] == "***REDACTED***"
    assert facts["flags"]["FIRST_PERSON_ACTIVE_COLLECTION"] == "first_person_v10"


def test_intent_router_flags_are_recorded_in_the_manifest():
    from scripts.ops.graded_capture import ENV_PREFIXES

    assert "INTENT_ROUTER_AMBIGUOUS_DOMAIN_ENABLED".startswith(ENV_PREFIXES)
    assert "FIRST_PERSON_JUDGE_MODEL".startswith(ENV_PREFIXES)
    assert not "PATH".startswith(ENV_PREFIXES)


def test_input_files_are_fingerprinted_by_sha_and_row_count(tmp_path, monkeypatch):
    import hashlib

    from scripts.ops import graded_capture as gc

    jl = tmp_path / "a.jsonl"
    jl.write_text('{"id": 1}\n\n{"id": 2}\n')
    js = tmp_path / "b.json"
    js.write_text('{"questions": [{"id": 1}, {"id": 2}, {"id": 3}]}')
    monkeypatch.setattr(gc, "REPO", tmp_path)
    fp = gc.input_fingerprints([jl, js, tmp_path / "missing.jsonl"])
    assert fp["a.jsonl"] == {"sha256": hashlib.sha256(jl.read_bytes()).hexdigest(), "rows": 2}
    assert fp["b.json"]["rows"] == 3 and len(fp) == 2


# ── transport retries (2026-11-16: graded-9-live measured the limiter, not the app) ──


class _Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}

    def json(self):
        return self._body


class _Client:
    """Scripted client: chat POSTs answer from ``chats`` in order; the session POST always works."""

    def __init__(self, chats):
        self.chats = list(chats)
        self.chat_calls = 0

    def post(self, url, **_kw):
        if url.endswith("/api/auth/anon-session"):
            return _Resp(200, {"token": "t"})
        self.chat_calls += 1
        return self.chats.pop(0) if len(self.chats) > 1 else self.chats[0]


def _ask_with(chats):
    sleeps: list[float] = []
    client = _Client(chats)
    out = _ask(client, "http://x", {"token": None, "used": 0}, "q", sleeps.append)
    return out, sleeps, client


def test_429_then_success_is_retried_and_counted():
    (http, result, retries, completed), sleeps, _ = _ask_with(
        [_Resp(429), _Resp(429), _Resp(200, {"response": "ok"})]
    )
    assert (http, retries, completed, result["response"]) == (200, 2, True, "ok")
    assert sleeps == [2.0, 4.0]  # exponential from 2 s


def test_retry_after_header_is_honoured_and_capped():
    _, sleeps, _ = _ask_with([_Resp(429, headers={"retry-after": "7"}), _Resp(200)])
    assert sleeps == [7.0]
    _, sleeps, _ = _ask_with([_Resp(503, headers={"retry-after": "500"}), _Resp(200)])
    assert sleeps == [60.0]


def test_503_without_retry_after_and_other_4xx_are_not_retried():
    for status in (503, 400, 401, 404):
        (http, _, retries, completed), sleeps, client = _ask_with([_Resp(status)])
        assert (http, retries, completed, sleeps, client.chat_calls) == (status, 0, False, [], 1)


def test_persistent_429_stops_after_five_attempts_and_is_a_transport_failure():
    (http, result, retries, completed), sleeps, client = _ask_with([_Resp(429)])
    assert (http, result, retries, completed) == (429, {}, 4, False)
    assert client.chat_calls == 5 and sleeps == [2.0, 4.0, 8.0, 16.0]


def test_transport_failure_invalidates_the_run_with_a_bounded_id_list():
    ids = [f"ua{i}" for i in range(12)]
    v = validity("", (0, 0), (0, 0), True, ids)
    assert v["valid"] is False
    (reason,) = v["reasons"]
    assert reason.startswith("12 rows failed at transport") and "ua9" in reason
    assert "ua10" not in reason and reason.endswith("...")
    assert validity("", (0, 0), (0, 0), True, [])["valid"] is True


def test_row_records_retries_and_transport_failure():
    row = build_row({"id": "q"}, {}, 429, 1.0, transport_retries=4, transport_failed=True)
    assert row["transport_retries"] == 4 and row["transport_failed"] is True
    assert build_row({"id": "q"}, {}, 200, 1.0)["transport_failed"] is False


# ── pacing (2026-11-16: stay under the 20/minute chat limit instead of retrying it) ──


def test_pacer_spaces_consecutive_calls_with_a_fake_clock():
    from scripts.ops.graded_capture import Pacer

    now = [100.0]
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    pace = Pacer(3.2, sleep=sleep, clock=lambda: now[0])
    pace()  # first call never waits
    now[0] += 1.0
    pace()  # 1.0 s elapsed: waits the remaining 2.2 s
    now[0] += 5.0
    pace()  # already past the interval: no wait
    assert slept == [pytest.approx(2.2)]


def test_ask_paces_chat_posts_only_not_session_or_polls():
    paced: list[int] = []
    client = _Client([_Resp(200, {"response": "ok"})])
    _ask(
        client, "http://x", {"token": None, "used": 0}, "q", lambda s: None, lambda: paced.append(1)
    )
    assert paced == [1]  # one chat POST; the anon-session POST was not paced


def test_default_interval_is_above_the_chat_limit_spacing():
    from scripts.ops.graded_capture import DEFAULT_MIN_INTERVAL_S

    assert DEFAULT_MIN_INTERVAL_S > 60 / 20
