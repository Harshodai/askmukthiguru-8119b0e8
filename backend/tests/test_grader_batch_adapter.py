"""Batch grading adapter (report item 11): one Anthropic submission per stage.

The adapter exists so a large grading run does not meet OpenRouter's 429 wall and can
be billed at the provider's batch rate. These tests run against an httpx MockTransport:
no key, no network, no paid call. The security contract is tested too — a credential
client may only talk https to the Anthropic host.
"""

from __future__ import annotations

import json

import httpx
import pytest

from scripts.ops.grade_served_answers import (
    GraderCredentialError,
    _anthropic_batch_asker,
    _validated_anthropic_base_url,
    grade_rows_batched,
)


def _rows(count: int) -> list[dict]:
    return [
        {
            "id": f"r{i}",
            "question": f"question {i}",
            "answer": f"answer {i}",
            "citations": [{"text": "clip", "speaker": "Sri Krishnaji", "url": "https://x"}],
            "sha": "deadbeef",
        }
        for i in range(count)
    ]


def _batch_transport(replies: dict[int, str], *, states: list[str] | None = None):
    """MockTransport that plays submit -> poll -> results for one batch."""
    states = states or ["in_progress", "ended"]
    seen: dict[str, list] = {"posts": [], "gets": [], "headers": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"].append(dict(request.headers))
        url = str(request.url)
        if request.method == "POST" and url.endswith("/messages/batches"):
            seen["posts"].append(json.loads(request.content))
            return httpx.Response(
                200, json={"id": "msgbatch_1", "processing_status": "in_progress"}
            )
        if request.method == "GET" and url.endswith("/results"):
            lines = [
                json.dumps(
                    {
                        "custom_id": f"row-{index:05d}",
                        "result": {
                            "type": "succeeded",
                            "message": {"content": [{"type": "text", "text": text}]},
                        },
                    }
                )
                for index, text in sorted(replies.items())
            ]
            return httpx.Response(200, text="\n".join(lines))
        if request.method == "GET" and "/messages/batches/msgbatch_1" in url:
            state = states[min(len(seen["gets"]), len(states) - 1)]
            seen["gets"].append(state)
            payload = {"id": "msgbatch_1", "processing_status": state}
            if state == "ended":
                payload["results_url"] = (
                    "https://api.anthropic.com/v1/messages/batches/msgbatch_1/results"
                )
            return httpx.Response(200, json=payload)
        return httpx.Response(404, text=f"unexpected {request.method} {url}")

    return httpx.MockTransport(handler), seen


def _anthropic_settings(monkeypatch, *, key: str = "test-key") -> None:
    """Pin the settings the asker reads.

    ``settings.anthropic_base_url`` is deliberately patched: the local ``.env`` points it
    at a local Ollama-compatible endpoint, and batch mode must refuse that host rather
    than send a credential to it.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", key, raising=False)
    monkeypatch.setattr(
        settings, "anthropic_base_url", "https://api.anthropic.com/v1", raising=False
    )
    monkeypatch.setattr(settings, "anthropic_api_version", "2023-06-01", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)


def _asker(monkeypatch, transport):
    _anthropic_settings(monkeypatch)
    client = httpx.Client(transport=transport, follow_redirects=False)
    return _anthropic_batch_asker("claude-sonnet-4-6", client=client, poll_interval_s=0)


def test_submission_carries_every_row_in_one_request(monkeypatch):
    transport, seen = _batch_transport({0: '{"verdict": "showable"}', 1: '{"verdict": "unsure"}'})
    asker = _asker(monkeypatch, transport)

    replies = asker("RUBRIC", ["prompt a", "prompt b"])

    assert replies == ['{"verdict": "showable"}', '{"verdict": "unsure"}']
    assert len(seen["posts"]) == 1, "one submission per stage, not one call per row"
    sent = seen["posts"][0]["requests"]
    assert [r["custom_id"] for r in sent] == ["row-00000", "row-00001"]
    assert sent[0]["params"]["messages"][0]["content"] == "prompt a"
    assert sent[0]["params"]["system"] == "RUBRIC"
    assert sent[0]["params"]["temperature"] == 0


def test_polling_waits_until_the_batch_ends(monkeypatch):
    transport, seen = _batch_transport({0: "ok"}, states=["in_progress", "in_progress", "ended"])
    asker = _asker(monkeypatch, transport)

    assert asker("RUBRIC", ["prompt"]) == ["ok"]
    assert seen["gets"] == ["in_progress", "in_progress", "ended"]


def test_credentials_go_only_to_the_anthropic_host(monkeypatch):
    transport, seen = _batch_transport({0: "ok"})
    asker = _asker(monkeypatch, transport)

    asker("RUBRIC", ["prompt"])

    sent_headers = seen["headers"][0]
    assert sent_headers["x-api-key"] == "test-key"
    assert sent_headers["anthropic-version"] == "2023-06-01"


def test_a_failed_request_becomes_an_empty_reply_never_a_pass(monkeypatch):

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"id": "msgbatch_1"})
        if "results" in str(request.url):
            return httpx.Response(
                200,
                text="\n".join(
                    [
                        json.dumps(
                            {
                                "custom_id": "row-00000",
                                "result": {
                                    "type": "succeeded",
                                    "message": {"content": [{"type": "text", "text": "kept"}]},
                                },
                            }
                        ),
                        json.dumps({"custom_id": "row-00001", "result": {"type": "errored"}}),
                    ]
                ),
            )
        return httpx.Response(
            200,
            json={
                "processing_status": "ended",
                "results_url": "https://api.anthropic.com/v1/messages/batches/msgbatch_1/results",
            },
        )

    asker = _asker(monkeypatch, httpx.MockTransport(handler))

    assert asker("RUBRIC", ["a", "b"]) == ["kept", ""]


def test_missing_key_refuses_before_any_paid_call(monkeypatch):
    _anthropic_settings(monkeypatch, key="")

    with pytest.raises(GraderCredentialError) as excinfo:
        _anthropic_batch_asker("claude-sonnet-4-6")

    assert excinfo.value.auth_status == "missing_credentials"
    assert "--batch" in str(excinfo.value)


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://api.anthropic.com/v1", "insecure_base_url"),
        ("https://evil.example.com/v1", "untrusted_host"),
        ("https://api.anthropic.com.evil.example/v1", "untrusted_host"),
    ],
)
def test_base_url_must_be_https_on_an_anthropic_host(url: str, reason: str):
    with pytest.raises(GraderCredentialError) as excinfo:
        _validated_anthropic_base_url(url)
    assert excinfo.value.auth_status == reason


def test_http_401_is_a_credential_error_not_a_grade(monkeypatch):
    _anthropic_settings(monkeypatch, key="bad-key")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(401, text="bad key")),
        follow_redirects=False,
    )
    asker = _anthropic_batch_asker("claude-sonnet-4-6", client=client, poll_interval_s=0)

    with pytest.raises(GraderCredentialError) as excinfo:
        asker("RUBRIC", ["prompt"])

    assert excinfo.value.auth_status == "unauthorized_401"


def test_batched_grade_keeps_the_synchronous_report_shape():
    rows = _rows(3)
    calls: list[int] = []

    def ask_many(system: str, users: list[str]) -> list[str]:
        calls.append(len(users))
        return ['{"verdict": "showable", "harmful": false, "reasons": ["ok"]}'] * len(users)

    result = grade_rows_batched(rows, ask_many, ask_many, sample_fraction=0.0, seed=7)

    # The strong judge always re-checks at least one showable row (max(1, ...)), so a
    # 0.0 fraction asks about one row rather than skipping the cross-check entirely.
    assert calls == [3, 1]
    assert set(result) == {"first", "second", "second_pass_ids", "agreement", "final"}
    assert set(result["final"]) == {"r0", "r1", "r2"}
    assert all(grade["verdict"] == "showable" for grade in result["final"].values())


def test_batched_second_pass_asks_only_the_selected_rows():
    rows = _rows(4)
    asked: list[list[str]] = []

    def first(system: str, users: list[str]) -> list[str]:
        asked.append(users)
        return [
            '{"verdict": "not_showable", "harmful": false, "reasons": ["no"]}'
            if "question 1" in user
            else '{"verdict": "showable", "harmful": false, "reasons": ["ok"]}'
            for user in users
        ]

    def second(system: str, users: list[str]) -> list[str]:
        asked.append(users)
        return ['{"verdict": "not_showable", "harmful": false, "reasons": ["no"]}'] * len(users)

    result = grade_rows_batched(rows, first, second, sample_fraction=0.0, seed=7)

    assert len(asked[0]) == 4
    assert all(f"question {i}" in asked[0][i] for i in range(4))
    # Every non-showable row is re-graded by the strong judge even at fraction 0.
    # r1 is re-graded because it was not showable, plus the always-on sample of one.
    assert "r1" in result["second_pass_ids"]
    assert len(result["second_pass_ids"]) == 2
    asked_ids = {
        grade_id
        for grade_id in result["second_pass_ids"]
        if f"question {grade_id[1:]}" in " ".join(asked[1])
    }
    assert asked_ids == set(result["second_pass_ids"])
    assert result["final"]["r1"]["verdict"] == "not_showable"
