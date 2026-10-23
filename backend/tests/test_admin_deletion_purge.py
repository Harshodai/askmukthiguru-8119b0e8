"""Outside audit MULTI-001: the admin deletion endpoint must run the purge, not only log it."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api import compliance
from services.tenant_context import set_tenant_from_request


def _call(container):
    fn = getattr(compliance.request_data_deletion, "__wrapped__", compliance.request_data_deletion)
    return asyncio.run(fn(request=MagicMock(), user_id="u-1", _admin={"id": "admin"}))


@pytest.fixture
def container(monkeypatch):
    c = MagicMock()
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


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
