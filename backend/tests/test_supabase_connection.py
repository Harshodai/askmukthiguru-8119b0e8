"""Tests for Supabase client initialization and connectivity.

These tests verify that the Supabase client can be initialized from
environment configuration and that basic connectivity works.
All tests skip gracefully when SUPABASE_URL / SUPABASE_KEY are not set
or when the Supabase server is unreachable.
"""

import pytest


def test_supabase_settings_loaded():
    """Verify that the Settings model carries supabase_url and supabase_key."""
    from app.config import settings

    assert hasattr(settings, "supabase_url")
    assert hasattr(settings, "supabase_key")


def test_supabase_client_initializes(supabase_client):
    """Verify the client object is created and connectivity is confirmed.

    The supabase_client fixture already performs a lightweight connectivity
    check — if this test runs at all, both initialization and basic
    connectivity succeeded.
    """
    assert supabase_client is not None


def test_supabase_list_tables(supabase_client):
    """Verify we can list tables from the public schema."""
    response = supabase_client.table("_prisma_migrations").select("*", count="exact").limit(1).execute()
    assert response is not None
    assert hasattr(response, "data")


def test_supabase_rpc_health(supabase_client):
    """Call a no-op RPC to verify the service is responsive."""
    try:
        response = supabase_client.rpc("version").execute()
        assert response is not None
    except Exception as exc:
        msg = str(exc).lower()
        if "function version() does not exist" in msg or "could not find" in msg:
            pytest.skip("No 'version' RPC function defined in this Supabase project")
        raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
