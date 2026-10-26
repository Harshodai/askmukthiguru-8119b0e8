"""Outside audit MULTI-001: the admin deletion endpoint must run the purge, not only log it."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import compliance
from services.tenant_context import set_tenant_from_request


def _call(container, req=None):
    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    if req is None:
        req = MagicMock()
        req.query_params = {"tenant_id": "test-tenant"}
        req.headers = {}
    return asyncio.run(fn(request=req, user_id="u-1", _admin={"id": "admin", "is_superuser": True}))


@pytest.fixture
def container(monkeypatch):
    c = MagicMock()
    # Lookup succeeds on every table and finds no rows (admin override is then accepted).
    c.supabase = MagicMock()
    lookup = c.supabase.table.return_value.select.return_value.eq.return_value
    lookup.order.return_value.range.return_value.execute.return_value.data = []
    c.memory_service.purge_all_user_data = AsyncMock(return_value={"qdrant": 3})
    monkeypatch.setattr(compliance, "get_container", lambda: c)
    return c


def test_purge_runs_and_completion_is_recorded(container):
    out = _call(container)
    container.memory_service.purge_all_user_data.assert_awaited_once_with("u-1")
    assert out["status"] == "deletion_completed" and out["result"] == {"qdrant": 3}
    assert container.compliance_logger.write_record.call_args.args[0]["status"] == "completed"


def test_purge_failure_is_recorded_and_not_reported_as_done(container):
    container.memory_service.purge_all_user_data = AsyncMock(side_effect=RuntimeError("down"))
    with pytest.raises(HTTPException) as exc:
        _call(container)
    assert exc.value.status_code == 502
    assert container.compliance_logger.write_record.call_args.args[0]["status"] == "purge_failed"


def test_partial_purge_errors_are_not_reported_as_done(container):
    container.memory_service.purge_all_user_data = AsyncMock(
        return_value={"errors": ["qdrant: ConnectionError"]}
    )
    with pytest.raises(HTTPException) as exc:
        _call(container)
    assert exc.value.status_code == 502
    assert (
        container.compliance_logger.write_record.call_args.args[0]["status"] == "purge_incomplete"
    )


def test_endpoint_sets_tenant_context_like_other_routes():
    import inspect

    default = inspect.signature(compliance.request_data_deletion).parameters["_tenant"].default
    assert default.dependency is set_tenant_from_request


def test_missing_memory_service_is_501_and_recorded_pending(container):
    container.memory_service = None
    with pytest.raises(HTTPException) as exc:
        _call(container)
    assert exc.value.status_code == 501
    assert container.compliance_logger.write_record.call_args.args[0]["status"] == "pending"


def test_cross_tenant_purge_scopes_to_target_tenant(container):
    from services.tenant_context import TenantContext

    captured_tenants = []

    async def _mock_purge(user_id):
        captured_tenants.append(TenantContext.get())
        return {"qdrant": 1}

    container.memory_service.purge_all_user_data = _mock_purge

    req = MagicMock()
    req.query_params = {"tenant_id": "tenant-b"}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    out = asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert out["status"] == "deletion_completed"
    assert captured_tenants == ["tenant-b"]


def test_tenant_lookup_via_supabase_success(container):
    from services.tenant_context import TenantContext

    captured_tenants = []

    async def _mock_purge(user_id):
        captured_tenants.append(TenantContext.get())
        return {"qdrant": 1}

    container.memory_service.purge_all_user_data = _mock_purge

    mock_client = MagicMock()
    mock_data = [{"tenant_id": "resolved-tenant-1"}]
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = mock_data
    container.supabase = mock_client

    req = MagicMock()
    req.query_params = {}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    out = asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert out["status"] == "deletion_completed"
    assert captured_tenants == ["resolved-tenant-1"]


def test_multi_tenant_lookup_and_purge_all_tenants(container):
    from services.tenant_context import TenantContext

    captured_tenants = []

    async def _mock_purge(user_id):
        captured_tenants.append(TenantContext.get())
        return {"qdrant": 1}

    container.memory_service.purge_all_user_data = _mock_purge

    mock_client = MagicMock()

    def _mock_table(table_name):
        t_mock = MagicMock()
        if table_name == "canonical_memories":
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
                {"tenant_id": "tenant-a"}
            ]
        elif table_name == "guru_memories":
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
                {"tenant_id": "tenant-b"}
            ]
        else:
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = []
        return t_mock

    mock_client.table.side_effect = _mock_table
    container.supabase = mock_client

    req = MagicMock()
    req.query_params = {}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    out = asyncio.run(
        fn(request=req, user_id="u-multi", _admin={"id": "admin", "is_superuser": True})
    )

    assert out["status"] == "deletion_completed"
    assert set(captured_tenants) == {"tenant-a", "tenant-b"}
    assert container.compliance_logger.write_record.call_args.args[0]["status"] == "completed"


def test_multi_tenant_purge_partial_failure_attempts_all_and_records_audit(container):
    from services.tenant_context import TenantContext

    attempted_tenants = []

    async def _mock_purge(user_id):
        cur = TenantContext.get()
        attempted_tenants.append(cur)
        if cur == "tenant-b":
            raise RuntimeError("tenant-b store down")
        return {"qdrant": 1}

    container.memory_service.purge_all_user_data = _mock_purge

    mock_client = MagicMock()

    def _mock_table(table_name):
        t_mock = MagicMock()
        if table_name == "canonical_memories":
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
                {"tenant_id": "tenant-a"}
            ]
        elif table_name == "guru_memories":
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
                {"tenant_id": "tenant-b"}
            ]
        else:
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = []
        return t_mock

    mock_client.table.side_effect = _mock_table
    container.supabase = mock_client

    req = MagicMock()
    req.query_params = {}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            fn(request=req, user_id="u-multi", _admin={"id": "admin", "is_superuser": True})
        )

    assert exc.value.status_code == 502
    assert "Purge incomplete or failed" in exc.value.detail
    assert "tenant-b" in exc.value.detail
    # Both tenants were attempted despite tenant-b failing
    assert set(attempted_tenants) == {"tenant-a", "tenant-b"}
    call_kwargs = container.compliance_logger.write_record.call_args.args[0]
    assert call_kwargs["status"] == "purge_incomplete"
    assert "tenant-b" in call_kwargs["failed_tenants"]


def test_tenant_override_can_retry_previously_failed_tenant(container):
    """A failed tenant with no remaining rows must still be retryable by explicit override."""
    from services.tenant_context import TenantContext

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {"tenant_id": "tenant-a"}
    ]
    container.supabase = mock_client
    container.compliance_logger.list_sessions_for_user.return_value = [
        {
            "action": "gdpr_deletion_request",
            "status": "purge_incomplete",
            "failed_tenants": {"tenant-b": "RuntimeError"},
        }
    ]

    captured_tenants = []

    async def _mock_purge(user_id):
        captured_tenants.append(TenantContext.get())
        return {"qdrant": 1}

    container.memory_service.purge_all_user_data = _mock_purge

    req = MagicMock()
    req.query_params = {"tenant_id": "tenant-b"}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    out = asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert out["status"] == "deletion_completed"
    assert captured_tenants == ["tenant-b"]


def test_non_purge_records_do_not_shadow_last_failed_tenant(container):
    """Lookup/pending records after a failed purge must not hide its failed tenant."""
    from services.tenant_context import TenantContext

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {"tenant_id": "tenant-a"}
    ]
    container.supabase = mock_client
    container.compliance_logger.list_sessions_for_user.return_value = [
        {
            "action": "gdpr_deletion_request",
            "status": "purge_incomplete",
            "failed_tenants": {"tenant-b": "RuntimeError"},
        },
        {"action": "gdpr_deletion_request", "status": "pending"},
        {"action": "gdpr_deletion_request", "status": "tenant_lookup_failed"},
    ]

    captured_tenants = []

    async def _mock_purge(user_id):
        captured_tenants.append(TenantContext.get())
        return {"qdrant": 1}

    container.memory_service.purge_all_user_data = _mock_purge

    req = MagicMock()
    req.query_params = {"tenant_id": "tenant-b"}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    out = asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert out["status"] == "deletion_completed"
    assert captured_tenants == ["tenant-b"]


def test_completed_purge_supersedes_older_failed_tenant(container):
    """The newest purge outcome wins: an older failed tenant is not retryable after completion."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {"tenant_id": "tenant-a"}
    ]
    container.supabase = mock_client
    container.compliance_logger.list_sessions_for_user.return_value = [
        {
            "action": "gdpr_deletion_request",
            "status": "purge_incomplete",
            "failed_tenants": {"tenant-b": "RuntimeError"},
        },
        {"action": "gdpr_deletion_request", "status": "completed"},
    ]

    req = MagicMock()
    req.query_params = {"tenant_id": "tenant-b"}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert exc.value.status_code == 409
    container.memory_service.purge_all_user_data.assert_not_called()


def test_retry_after_purge_incomplete_without_override_includes_failed_tenants(container):
    """A retry with no override includes failed tenants from purge_incomplete even if missing from live rows."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {"tenant_id": "tenant-a"}
    ]
    container.supabase = mock_client
    container.compliance_logger.list_sessions_for_user.return_value = [
        {
            "action": "gdpr_deletion_request",
            "status": "purge_incomplete",
            "failed_tenants": {"tenant-b": "RuntimeError"},
        }
    ]

    captured_tenants: list[str] = []

    def _scope_capture(t, user_id=None):
        captured_tenants.append(t)
        return MagicMock(__enter__=MagicMock(), __exit__=MagicMock())

    container.memory_service.purge_all_user_data = AsyncMock(
        return_value={"status": "success", "purged": {}}
    )

    req = MagicMock()
    req.query_params = {}
    req.headers = {}

    with patch("app.api.compliance.TenantContext.scope", side_effect=_scope_capture):
        fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
        out = asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert out["status"] == "deletion_completed"
    assert captured_tenants == ["tenant-a", "tenant-b"]


def test_tenant_override_mismatch_returns_409(container):
    mock_client = MagicMock()
    mock_data = [{"tenant_id": "actual-tenant"}]
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = mock_data
    container.supabase = mock_client

    req = MagicMock()
    req.query_params = {"tenant_id": "wrong-tenant"}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert exc.value.status_code == 409
    assert "Tenant override mismatch" in exc.value.detail


def test_tenant_lookup_failure_returns_503_and_records_audit(container):
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.side_effect = RuntimeError(
        "database offline"
    )
    container.supabase = mock_client

    req = MagicMock()
    req.query_params = {}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert exc.value.status_code == 503
    assert "tenant_lookup_failed:RuntimeError" in exc.value.detail
    assert (
        container.compliance_logger.write_record.call_args.args[0]["status"]
        == "tenant_lookup_failed"
    )


def test_partial_table_lookup_failure_fails_closed(container):
    """When one table lookup raises and another returns a tenant, fail closed without override."""
    mock_client = MagicMock()

    def _mock_table(table_name):
        t_mock = MagicMock()
        if table_name == "canonical_memories":
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.side_effect = (
                RuntimeError("canonical table timeout")
            )
        elif table_name == "guru_memories":
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
                {"tenant_id": "tenant-found"}
            ]
        else:
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = []
        return t_mock

    mock_client.table.side_effect = _mock_table
    container.supabase = mock_client

    req = MagicMock()
    req.query_params = {}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fn(request=req, user_id="u-3", _admin={"id": "admin", "is_superuser": True}))

    assert exc.value.status_code == 503
    assert "tenant_lookup_failed:RuntimeError" in exc.value.detail
    assert (
        container.compliance_logger.write_record.call_args.args[0]["status"]
        == "tenant_lookup_failed"
    )


def test_tenant_lookup_missing_client_returns_503_and_records_audit(container):
    container.supabase = None
    container.memory_service._supabase = None

    req = MagicMock()
    req.query_params = {}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fn(request=req, user_id="u-2", _admin={"id": "admin", "is_superuser": True}))

    assert exc.value.status_code == 503
    assert "tenant_not_found" in exc.value.detail
    assert (
        container.compliance_logger.write_record.call_args.args[0]["status"]
        == "tenant_lookup_failed"
    )


def test_require_admin_rejects_non_superuser():
    with pytest.raises(HTTPException) as exc:
        compliance._require_admin({"id": "user-1", "is_superuser": False})
    assert exc.value.status_code == 403
    assert exc.value.detail == "Admin access required"


def _req(tenant=None):
    req = MagicMock()
    req.query_params = {"tenant_id": tenant} if tenant else {}
    req.headers = {}
    return req


def test_partial_lookup_failure_is_503_even_if_another_table_found_tenants(container):
    chain = container.supabase.table.return_value.select.return_value.eq.return_value
    chain.order.return_value.range.return_value.execute.side_effect = [
        MagicMock(data=[{"tenant_id": "t-a"}]),
        RuntimeError("boom"),
        MagicMock(data=[]),
    ]
    with pytest.raises(HTTPException) as exc:
        _call(container, _req())
    assert exc.value.status_code == 503 and "tenant_lookup_failed:RuntimeError" in exc.value.detail
    container.memory_service.purge_all_user_data.assert_not_called()


def test_override_rejected_when_lookup_failed_and_found_nothing(container):
    chain = container.supabase.table.return_value.select.return_value.eq.return_value
    chain.order.return_value.range.return_value.execute.side_effect = RuntimeError("boom")
    with pytest.raises(HTTPException) as exc:
        _call(container, _req("tenant-x"))
    assert exc.value.status_code == 503
    container.memory_service.purge_all_user_data.assert_not_called()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))


def test_http_exception_from_purge_is_recorded_and_does_not_abort_other_tenants(container):
    """A purge that raises HTTPException is a per-tenant failure, not a request abort.

    Re-raising it would skip the audit record for a deletion that was actually
    requested, and would leave later tenants unattempted.
    """
    from services.tenant_context import TenantContext

    attempted_tenants = []

    async def _mock_purge(user_id):
        cur = TenantContext.get()
        attempted_tenants.append(cur)
        if cur == "tenant-b":
            raise HTTPException(status_code=409, detail="tenant store busy")
        return {"qdrant": 1}

    container.memory_service.purge_all_user_data = _mock_purge

    mock_client = MagicMock()

    def _mock_table(table_name):
        t_mock = MagicMock()
        rows = {
            "canonical_memories": [{"tenant_id": "tenant-a"}],
            "guru_memories": [{"tenant_id": "tenant-b"}],
        }.get(table_name, [])
        (
            t_mock.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data
        ) = rows
        return t_mock

    mock_client.table.side_effect = _mock_table
    container.supabase = mock_client

    req = MagicMock()
    req.query_params = {}
    req.headers = {}

    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            fn(request=req, user_id="u-multi", _admin={"id": "admin", "is_superuser": True})
        )

    assert exc.value.status_code == 502
    assert set(attempted_tenants) == {"tenant-a", "tenant-b"}
    record = container.compliance_logger.write_record.call_args.args[0]
    assert record["status"] == "purge_incomplete"
    assert record["failed_tenants"]["tenant-b"] == "http_409"
