"""A rate-limited or over-quota seeker must still be shown the helplines."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware import crisis_support_on_refusal as mod
from services.crisis_helplines import format_helplines_block

LEGACY = {"error": "Anonymous quota exceeded", "quota_exceeded": True, "remaining": 0}


async def _refuse(request):
    return JSONResponse(LEGACY, status_code=429, headers={"Retry-After": "30"})


async def _ok(request):
    return JSONResponse({"answer": "x"})


async def _refuse_text(request):
    return PlainTextResponse("slow down", status_code=429)


def _client() -> TestClient:
    app = Starlette(
        routes=[
            Route("/api/chat", _refuse, methods=["POST"]),
            Route("/api/chat/ok", _ok, methods=["POST"]),
            Route("/api/chat/text", _refuse_text, methods=["POST"]),
            Route("/api/auth/anon-session", _refuse, methods=["POST"]),
            Route("/api/admin/thing", _refuse, methods=["POST"]),
        ]
    )
    app.add_middleware(mod.CrisisSupportOnRefusalMiddleware)
    return TestClient(app)


@pytest.mark.parametrize("path", ["/api/chat", "/api/auth/anon-session"])
def test_refusal_keeps_legacy_body_and_adds_verified_lines(path):
    r = _client().post(path)
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "30"
    body = r.json()
    assert {k: body[k] for k in LEGACY} == LEGACY
    assert body["crisis_support"]["text"] == format_helplines_block(verified_only=True)
    assert "14416" in body["crisis_support"]["text"]  # Tele-MANAS, the phone-verified line


def test_success_and_other_surfaces_are_untouched():
    c = _client()
    assert c.post("/api/chat/ok").json() == {"answer": "x"}
    assert c.post("/api/admin/thing").json() == LEGACY


def test_non_json_refusal_passes_through():
    r = _client().post("/api/chat/text")
    assert r.status_code == 429 and r.text == "slow down"


def test_unreadable_helpline_source_still_returns_the_legacy_refusal(monkeypatch):
    def _boom(**_):
        raise OSError("helplines.yaml missing")

    monkeypatch.setattr("services.crisis_helplines.format_helplines_block", _boom)
    r = _client().post("/api/chat")
    assert r.status_code == 429 and r.json() == LEGACY


def test_real_app_registers_the_middleware():
    from app.main import app

    assert any(m.cls is mod.CrisisSupportOnRefusalMiddleware for m in app.user_middleware)
