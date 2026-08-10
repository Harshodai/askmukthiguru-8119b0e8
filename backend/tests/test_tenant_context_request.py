"""P1-BE-5: tenant context initialization from request.

Regression guard for the removed dead path ``app.main._init_tenant_context_from_request``.

That function called the async ``get_current_user_from_supabase(request)`` without
``await`` — it always received a coroutine, so ``user.get("tenant_id", ...)`` hit the
``.get`` on a coroutine, raised, and every request was stamped ``"default"``. Worse,
the function had no call sites at all: the tenant prefixing added in CRIT-4 uses the
``set_tenant_from_request`` dependency (services/tenant_context.py), which reads
``request.state.user`` and is wired into the routers.

These tests pin the working contract:
1. The dead function is gone (nothing imports or calls it).
2. The dependency path sets a real tenant, not "default".
"""

import pytest
from fastapi import Request

import app.main as main_module
from services.tenant_context import TenantContext, set_tenant_from_request


def test_dead_tenant_init_function_removed():
    assert not hasattr(main_module, "_init_tenant_context_from_request"), (
        "dead non-awaited tenant init must not exist"
    )


@pytest.mark.asyncio
async def test_set_tenant_from_request_populates_tenant_context():
    request = Request({"type": "http", "method": "POST", "path": "/api/chat"})
    request.state.user = {
        "id": "user-abc",
        "email": "seeker@example.com",
        "tenant_id": "tenant-42",
    }
    await set_tenant_from_request(request)
    assert TenantContext.get() == "tenant-42"
    assert TenantContext.get_email() == "seeker@example.com"
    assert TenantContext.get_user_id() == "user-abc"


@pytest.mark.asyncio
async def test_set_tenant_from_request_falls_back_to_user_id():
    request = Request({"type": "http", "method": "POST", "path": "/api/chat"})
    request.state.user = {"id": "user-abc", "email": "seeker@example.com"}
    await set_tenant_from_request(request)
    assert TenantContext.get() == "user-abc"
    assert TenantContext.get_email() == "seeker@example.com"
