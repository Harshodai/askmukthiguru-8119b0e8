import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import Request
from app.main import app
from app.sanitization import sanitize_user_input
from services.auth_service import get_current_user_from_supabase
from services.tenant_context import set_tenant_from_request, TenantContext
from app.dependencies import get_container

def test_sanitize_user_input_with_custom_limit():
    long_input = "a" * 3000
    cleaned = sanitize_user_input(long_input, max_length=10000)
    assert len(cleaned) == 3000

def test_chat_endpoint_accepts_long_input():
    client = TestClient(app)

    async def mock_get_user():
        return {"id": "test-user", "email": "test@example.com"}

    async def mock_set_tenant(request: Request):
        TenantContext.set("test-tenant", "test@example.com", "test-user")

    def mock_get_container():
        mock_container = MagicMock()
        mock_container.job_queue = None
        return mock_container

    # Set dependency overrides
    app.dependency_overrides[get_current_user_from_supabase] = mock_get_user
    app.dependency_overrides[set_tenant_from_request] = mock_set_tenant
    app.dependency_overrides[get_container] = mock_get_container

    try:
        # Mock RAG orchestrator
        with patch("app.orchestrator.ChatRequestOrchestrator.orchestrate") as mock_orch:
            mock_orch.return_value = {"status": "success"}
            
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "user_message": "a" * 3000
                }
            )
            assert response.status_code == 200
            
            # Assert the message passed to orchestrator is indeed 3000 chars, not truncated to 2000
            args = mock_orch.call_args[0]
            chat_body = args[1]
            assert len(chat_body.user_message) == 3000
    finally:
        # Clear overrides
        app.dependency_overrides.clear()
