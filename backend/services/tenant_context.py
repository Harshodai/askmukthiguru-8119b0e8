"""
Unit 19 — Multi-Tenant Auth & Collection Namespacing

Provides a ContextVar-based tenant context so the request tenant ID
flows through the entire async call chain without thread-local leakage.

Design:
  - TenantContext: holds the active tenant_id for the current asyncio task
  - set_tenant_context(): FastAPI dependency that extracts tenant_id from JWT claims
  - get_tenant_collection(): maps tenant_id → Qdrant collection name
  - tenant_aware_search(): wraps QdrantService.search() with per-tenant collection routing

Soft migration mode (default):
  - Existing data on the "default" (legacy) collection is preserved.
  - New tenants get their own namespaced collection.
  - The legacy tenant uses QDRANT_COLLECTION as-is.

Collection naming: ``{base_collection}__tenant_{tenant_id}``
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Optional

from fastapi import Request

from app.config import settings

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# ContextVar: active tenant for the current asyncio task
# -----------------------------------------------------------------------
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default=settings.default_tenant_id)
_tenant_email_var: ContextVar[str] = ContextVar("tenant_email", default="")
_tenant_user_id_var: ContextVar[str] = ContextVar("tenant_user_id", default="")

_LEGACY_TENANT = settings.default_tenant_id
_COLLECTION_SEPARATOR = "__tenant_"


class TenantContext:
    """Accessor for the current request's tenant identity."""

    @staticmethod
    def get() -> str:
        """Return the tenant ID for the currently executing asyncio task."""
        return _tenant_id_var.get()

    @staticmethod
    def get_email() -> str:
        """Return the email of the authenticated user for the current task."""
        return _tenant_email_var.get()

    @staticmethod
    def get_user_id() -> str:
        """Return the user ID of the authenticated user for the current task."""
        return _tenant_user_id_var.get()

    @staticmethod
    def set(tenant_id: str, email: str = "", user_id: str = "") -> None:
        """Set the tenant context for the current asyncio task."""
        _tenant_id_var.set(tenant_id)
        _tenant_email_var.set(email)
        _tenant_user_id_var.set(user_id)

    @staticmethod
    def reset() -> None:
        """Reset the current task to the legacy tenant context.

        Test fixtures and explicit request teardown use this helper to avoid
        carrying an authenticated tenant into the next task or request.
        ContextVar defaults are not mutated; only the current context is reset.
        """
        _tenant_id_var.set(_LEGACY_TENANT)
        _tenant_email_var.set("")
        _tenant_user_id_var.set("")

    @staticmethod
    def is_legacy() -> bool:
        """True if the current tenant is the legacy (single-tenant) default."""
        return _tenant_id_var.get() == _LEGACY_TENANT


def get_tenant_collection(base_collection: str, tenant_id: Optional[str] = None) -> str:
    """Map a (base_collection, tenant_id) pair to a Qdrant collection name.

    Args:
        base_collection: The base collection name (from settings.qdrant_collection).
        tenant_id: The tenant ID. Defaults to the current request's tenant.

    Returns:
        Collection name string.
        - Legacy tenant → ``base_collection`` (unchanged, soft migration)
        - Named tenant → ``{base_collection}__tenant_{tenant_id}``
    """
    tid = tenant_id or TenantContext.get()
    if not tid or tid == _LEGACY_TENANT:
        return base_collection  # Soft-mode: keep existing data untouched
    # Sanitize: replace chars that are unsafe for collection names
    safe_tid = "".join(c if c.isalnum() or c in "-_" else "_" for c in tid)
    return f"{base_collection}{_COLLECTION_SEPARATOR}{safe_tid}"


# -----------------------------------------------------------------------
# FastAPI dependency: extract tenant_id from the resolved user dict
# -----------------------------------------------------------------------


def get_tenant_id_from_user(user: dict) -> str:
    """Extract the tenant ID from an authenticated user dict.

    Priority (first non-empty wins):
      1. ``user["tenant_id"]`` if the JWT carries an explicit tenant claim
      2. ``user["id"]`` (Supabase user UUID → per-user tenant isolation)
      3. ``"default"`` (legacy fallback)

    In a multi-tenant SaaS, orgs would be modelled as separate Supabase projects
    or as a custom ``tenant_id`` claim. For now we use the user ID as the tenant.

    DORMANT PATH WARNING: this only fires when ``request.state.user`` is set,
    and nothing in the codebase currently sets it (confirmed via full-repo
    grep) -- ``set_tenant_from_request`` therefore always falls through to
    ``_LEGACY_TENANT`` in production today. If a future change ever populates
    ``request.state.user`` for an authenticated caller, this branch activates
    and TenantContext.get() returns their Supabase UUID instead of the legacy
    tenant -- every CorpusScope(tenant_id=TenantContext.get() or ...) call
    then scopes retrieval to a tenant_id no ingested Qdrant point carries,
    silently zeroing RAG retrieval for every authenticated user (the same
    failure shape as the tenant/corpus outage fixed this session, just
    dormant rather than live, and via the authenticated path specifically).
    """
    return user.get("tenant_id") or user.get("id") or _LEGACY_TENANT


async def set_tenant_from_request(request: Request) -> None:
    """FastAPI dependency: populate the TenantContext for the current request.

    Must be used with ``Depends()`` in any router that should be tenant-aware.
    Because it operates on ContextVar, it scopes cleanly to the asyncio task —
    no cross-request leakage is possible.

    Usage in a router::

        @router.post("/ask")
        async def ask_endpoint(
            _tenant=Depends(set_tenant_from_request),
            ...
        ):
            ...

    The tenant context is then readable anywhere in the call chain via
    ``TenantContext.get()``.
    """
    # Try to read the resolved user from request.state (set by AuthBridge)
    user: dict = getattr(request.state, "user", {}) or {}
    tenant_id = get_tenant_id_from_user(user)
    email = user.get("email", "")
    user_id = user.get("id", "")
    TenantContext.set(tenant_id, email, user_id)
    logger.debug(f"TenantContext set: tenant_id={tenant_id}")
