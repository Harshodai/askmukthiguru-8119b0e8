"""The launch-subscriber purge RPC is service_role-only, so it must use the service key."""
from unittest.mock import MagicMock, patch

from tasks import retention_tasks


def test_purge_prefers_service_role_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "supabase_service_key", "service-key", raising=False)
    monkeypatch.setattr(settings, "supabase_key", "anon-key", raising=False)
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = 3
    with patch("supabase.create_client", return_value=client) as create:
        assert retention_tasks.purge_launch_subscribers() == 3
    assert create.call_args.args[1] == "service-key"
