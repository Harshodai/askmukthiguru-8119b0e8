"""Budget reservations settle by what actually happened (graded-run plan F3, 2026-10-31).

The $0.03 per-call reservation used to be refunded only on a success path. A call cancelled
before it was sent, one that hit a connect error, or one that got an HTTP error with a usage
body all kept the full reservation, which over-counted and exhausted the daily cap mid-run.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import settings
from app.openrouter_budget import BudgetReservation
from services.openrouter_service import OpenRouterService


class _Guard:
    """Records refunds; stands in for OpenRouterBudgetGuard."""

    def __init__(self):
        self.refunds: list[float] = []

    async def refund(self, amount_usd: float) -> None:
        self.refunds.append(round(amount_usd, 6))

    def refund_local(self, amount_usd: float) -> None:  # pragma: no cover - local ledger path
        self.refunds.append(round(amount_usd, 6))


def _reservation(amount=0.03):
    guard = _Guard()
    return guard, BudgetReservation(guard, amount)


# ── the reservation rule itself ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_never_sent_refunds_in_full():
    guard, res = _reservation()
    await res.finalize(request_sent=False)
    assert guard.refunds == [0.03]


@pytest.mark.asyncio
async def test_response_with_cost_settles_at_that_cost():
    guard, res = _reservation()
    await res.finalize(request_sent=True, response_arrived=True, response_cost_usd=0.0004)
    assert guard.refunds == [pytest.approx(0.0296)]


@pytest.mark.asyncio
async def test_sent_without_a_response_keeps_the_reservation():
    guard, res = _reservation()
    await res.finalize(request_sent=True, response_arrived=False)
    assert guard.refunds == []


@pytest.mark.asyncio
async def test_response_without_a_cost_keeps_the_reservation():
    guard, res = _reservation()
    await res.finalize(request_sent=True, response_arrived=True, response_cost_usd=None)
    assert guard.refunds == []


@pytest.mark.asyncio
async def test_finalize_after_settle_never_refunds_twice():
    guard, res = _reservation()
    await res.settle(0.001)
    await res.finalize(request_sent=False)
    assert len(guard.refunds) == 1


# ── through the real call path ───────────────────────────────────────────────


def _service_with(monkeypatch, client, reservation):
    async def fake_get_client(self):
        return client

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    svc = OpenRouterService()

    class _BudgetGuard:
        async def reserve(self):
            return reservation

    svc._budget_guard = _BudgetGuard()
    return svc


class _OkResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1, "cost": 0.0004},
        }


@pytest.mark.asyncio
async def test_success_refunds_the_unused_reservation(monkeypatch):
    class Client:
        async def post(self, *a, **k):
            return _OkResponse()

    guard, res = _reservation()
    svc = _service_with(monkeypatch, Client(), res)
    assert await svc.generate(system_prompt="s", user_prompt="u") == "ok"
    assert guard.refunds == [pytest.approx(0.0296)]


@pytest.mark.asyncio
async def test_http_500_with_a_usage_body_settles_at_that_cost(monkeypatch):
    class Resp:
        status_code = 500

        def raise_for_status(self):
            req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            raise httpx.HTTPStatusError("boom", request=req, response=httpx.Response(500))

        def json(self):
            return {"usage": {"cost": 0.002}}

    class Client:
        async def post(self, *a, **k):
            return Resp()

    guard, res = _reservation()
    svc = _service_with(monkeypatch, Client(), res)
    await svc.generate(system_prompt="s", user_prompt="u")  # degrades gracefully, never raises
    assert guard.refunds == [pytest.approx(0.028)]


@pytest.mark.asyncio
async def test_connect_error_refunds_in_full(monkeypatch):
    class Client:
        async def post(self, *a, **k):
            raise httpx.ConnectError("no route")

    guard, res = _reservation()
    svc = _service_with(monkeypatch, Client(), res)
    await svc.generate(system_prompt="s", user_prompt="u")
    assert guard.refunds == [0.03]


@pytest.mark.asyncio
async def test_timeout_after_send_keeps_the_reservation(monkeypatch):
    class Client:
        async def post(self, *a, **k):
            raise httpx.ReadTimeout("slow")

    guard, res = _reservation()
    svc = _service_with(monkeypatch, Client(), res)
    await svc.generate(system_prompt="s", user_prompt="u")
    assert guard.refunds == []


@pytest.mark.asyncio
async def test_cancel_before_the_post_refunds_in_full(monkeypatch):
    gate = asyncio.Event()

    async def slow_get_client(self):
        gate.set()
        await asyncio.sleep(30)  # cancelled here, before any request exists

    monkeypatch.setattr(OpenRouterService, "_get_http_client", slow_get_client)
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    guard, res = _reservation()
    svc = OpenRouterService()

    class _BudgetGuard:
        async def reserve(self):
            return res

    svc._budget_guard = _BudgetGuard()
    task = asyncio.create_task(svc.generate(system_prompt="s", user_prompt="u"))
    await gate.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert guard.refunds == [0.03]
