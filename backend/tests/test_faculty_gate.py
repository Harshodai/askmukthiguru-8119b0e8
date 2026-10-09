"""Faculty gate: fail-closed shared-secret check in front of the LLM-spending routes."""

import pytest
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.faculty_gate import FacultyGateMiddleware, is_gated

CODE = "correct-horse-battery"


async def ok(request):
    return JSONResponse({"ok": True})


async def stream(request):
    async def gen():
        yield b"data: one\n\n"
        yield b"data: two\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def make_client():
    app = Starlette(
        routes=[
            Route("/api/chat", ok, methods=["POST", "OPTIONS"]),
            Route("/api/chat/stream", stream, methods=["POST"]),
            Route("/api/first-person/query", ok, methods=["POST"]),
            Route("/api/jobs/abc", ok, methods=["GET"]),
            Route("/api/health", ok, methods=["GET"]),
            Route("/api/capabilities", ok, methods=["GET"]),
        ]
    )
    app.add_middleware(FacultyGateMiddleware, access_code=CODE)
    app.add_middleware(CORSMiddleware, allow_origins=["https://faculty.example"], allow_methods=["*"], allow_headers=["X-Faculty-Code"])
    return TestClient(app)


@pytest.mark.parametrize("path", ["/api/chat", "/api/first-person/query", "/api/jobs/abc"])
def test_missing_code_is_rejected(path):
    r = make_client().request("POST" if "jobs" not in path else "GET", path)
    assert r.status_code == 401
    assert r.headers["x-faculty-gate"] == "denied"


def test_wrong_code_is_rejected():
    assert make_client().post("/api/chat", headers={"X-Faculty-Code": CODE + "x"}).status_code == 401
    assert make_client().post("/api/chat", headers={"X-Faculty-Code": ""}).status_code == 401


def test_correct_code_passes():
    assert make_client().post("/api/chat", headers={"X-Faculty-Code": CODE}).json() == {"ok": True}


def test_sse_stream_passes_through_unbuffered():
    r = make_client().post("/api/chat/stream", headers={"X-Faculty-Code": CODE})
    assert r.status_code == 200 and r.text == "data: one\n\ndata: two\n\n"


def test_health_and_ungated_paths_are_open():
    c = make_client()
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/capabilities").status_code == 200


def test_cors_preflight_is_not_blocked():
    r = make_client().options(
        "/api/chat",
        headers={
            "Origin": "https://faculty.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Faculty-Code",
        },
    )
    assert r.status_code == 200


def test_rejection_carries_cors_headers_when_cors_wraps_the_gate():
    r = make_client().post("/api/chat", headers={"Origin": "https://faculty.example"})
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == "https://faculty.example"


def test_empty_code_cannot_build_the_middleware():
    with pytest.raises(ValueError):
        FacultyGateMiddleware(Starlette(), access_code="")


def test_is_gated_prefixes():
    assert is_gated("/api/chat/stream") and is_gated("/api/first-person/query")
    assert not is_gated("/api/health") and not is_gated("/api/healthz") and not is_gated("/internal/metrics")
