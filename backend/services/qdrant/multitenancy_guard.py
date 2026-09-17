"""Multitenancy enforcement: guard decorator for search/upsert operations.

Ensures all Qdrant operations include tenant_id, teacher_id, or an authorized
CorpusScope. Prevents cross-tenant and cross-teacher data leaks.

Architecture & Security Invariants (Launch Gate 0.3):
1. No self-granted escape hatches: caller-supplied `skip_tenant_check=True`
   is disallowed in enforce mode. Exemptions require an explicit named
   operation registered in ALLOWED_UNSCOPED_OPERATIONS via TenantExemptionContext.
2. Dual-mode rollout:
   - "log": dry-run audit mode (logs warnings without raising, for safe staging observation).
   - "enforce": strict mode (raises MultitenancyViolation on unscoped calls).
3. Universal context extraction: checks TenantContext.get(), scope.tenant_id,
   teacher_id, tenant_id, and chunk metadata.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import logging
import traceback
from collections.abc import Callable
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Single source of truth for authorized unscoped system operations
ALLOWED_UNSCOPED_OPERATIONS: frozenset[str] = frozenset(
    {
        "qdrant_backup",
        "launch_gate_qdrant_integrity",
        "schema_migration",
        "collection_health_check",
        "test_fixture_cleanup",
        "system_admin_reindex",
        "benchmark_warmup",
    }
)

# Context variable tracking active authorized exemption tokens
_exemption_token: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "tenant_exemption_token", default=None
)


class MultitenancyViolation(Exception):
    """Raised when a Qdrant operation is missing required tenant context."""

    pass


class TenantExemptionContext:
    """Context manager for granting authorized exemptions to unscoped system operations.

    Usage:
        with TenantExemptionContext("qdrant_backup"):
            client.search(...)
    """

    def __init__(self, operation_name: str) -> None:
        if operation_name not in ALLOWED_UNSCOPED_OPERATIONS:
            raise MultitenancyViolation(
                f"Operation '{operation_name}' is not in ALLOWED_UNSCOPED_OPERATIONS: "
                f"{sorted(ALLOWED_UNSCOPED_OPERATIONS)}"
            )
        self.operation_name = operation_name
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> TenantExemptionContext:
        self._token = _exemption_token.set(self.operation_name)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._token is not None:
            _exemption_token.reset(self._token)
            self._token = None

    async def __aenter__(self) -> TenantExemptionContext:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


def get_guard_mode() -> str:
    """Return current enforcement mode: 'log', 'enforce', or 'disabled'.

    Reads via Settings only (never os.environ directly) — every other config
    value in this repo goes through Settings so it's visible to the
    dead-config scan and the .env/.env.example contract; a direct env read
    here would silently bypass both. Settings itself is env-driven, so
    MULTITENANCY_GUARD_MODE still works as an override, just through the one
    sanctioned path.
    """
    try:
        from app.config import settings

        return getattr(settings, "multitenancy_guard_mode", "log").strip().lower()
    except Exception:
        return "log"


def is_caller_exempt() -> tuple[bool, Optional[str]]:
    """Check if current execution context is covered by an authorized exemption."""
    token = _exemption_token.get()
    if token and token in ALLOWED_UNSCOPED_OPERATIONS:
        return True, token
    return False, None


def extract_tenant_context(func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    """Extract tenant, teacher, or scope context from parameters or thread context."""
    context: dict[str, Any] = {}

    # 1. Thread-local TenantContext
    try:
        from services.tenant_context import TenantContext

        ctx_val = TenantContext.get()
        if ctx_val and isinstance(ctx_val, str) and ctx_val.strip():
            context["tenant_context"] = ctx_val.strip()
    except Exception:
        pass

    # 2. Inspect signature bindings
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        all_params = bound.arguments
    except Exception:
        all_params = kwargs

    # Explicit tenant_id or teacher_id
    if "tenant_id" in all_params and all_params["tenant_id"]:
        context["tenant_id"] = str(all_params["tenant_id"]).strip()
    if "teacher_id" in all_params and all_params["teacher_id"]:
        context["teacher_id"] = str(all_params["teacher_id"]).strip()

    # Scope object (e.g. CorpusScope)
    scope = all_params.get("scope") or kwargs.get("scope")
    if scope is not None:
        s_tenant = getattr(scope, "tenant_id", None)
        s_teacher = getattr(scope, "teacher_id", None)
        if s_tenant and isinstance(s_tenant, str) and s_tenant.strip():
            context["scope_tenant_id"] = s_tenant.strip()
        if s_teacher and isinstance(s_teacher, str) and s_teacher.strip():
            context["scope_teacher_id"] = s_teacher.strip()

    # Metadata dictionaries (e.g. for upsert_chunks)
    metadatas = all_params.get("metadatas") or kwargs.get("metadatas")
    if metadatas and isinstance(metadatas, (list, tuple)) and len(metadatas) > 0:
        first_meta = metadatas[0]
        if isinstance(first_meta, dict):
            if first_meta.get("tenant_id"):
                context["metadata_tenant_id"] = first_meta["tenant_id"]
            if first_meta.get("teacher_id") or first_meta.get("teacher_ids"):
                context["metadata_teacher_id"] = first_meta.get("teacher_id") or first_meta.get(
                    "teacher_ids"
                )

    return context


def enforce_multitenancy(func: Callable) -> Callable:
    """Decorator enforcing that Qdrant operations possess verified tenant context.

    Behavior:
    - If tenant context is present or caller has an active TenantExemptionContext: succeeds.
    - If context is missing:
      - In 'enforce' mode: raises MultitenancyViolation.
      - In 'log' mode: logs MULTITENANCY_AUDIT_WARNING with traceback and allows execution.
      - In 'disabled' mode: allows execution silently.
    - Self-granted `skip_tenant_check=True` in kwargs is rejected in enforce mode.
    """
    func_name = getattr(func, "__qualname__", getattr(func, "__name__", "unnamed_operation"))
    is_async = asyncio.iscoroutinefunction(func) or inspect.iscoroutinefunction(func)

    def _validate_call(args: tuple, kwargs: dict) -> bool:
        mode = get_guard_mode()
        if mode == "disabled":
            return True

        # Check authorized exemption
        is_exempt, op_name = is_caller_exempt()
        if is_exempt:
            return True

        # Check self-granted skip_tenant_check escape hatch
        has_self_granted_skip = kwargs.get("skip_tenant_check", False)

        context = extract_tenant_context(func, args, kwargs)
        has_context = bool(
            context.get("tenant_context")
            or context.get("tenant_id")
            or context.get("teacher_id")
            or context.get("scope_tenant_id")
            or context.get("scope_teacher_id")
            or context.get("metadata_tenant_id")
            or context.get("metadata_teacher_id")
        )

        if has_context:
            return True

        # Missing tenant context
        if mode == "enforce":
            if has_self_granted_skip:
                raise MultitenancyViolation(
                    f"{func_name}() attempted self-granted skip_tenant_check=True. "
                    "Caller-supplied bypasses are disallowed in enforce mode. "
                    "Wrap with TenantExemptionContext(<allowed_op>) if running an authorized system task."
                )
            raise MultitenancyViolation(
                f"{func_name}() called without verified tenant or teacher context. "
                "This could cause cross-tenant data leaks. "
                "Provide tenant_id, teacher_id, CorpusScope, or run within TenantContext. "
                "For authorized unscoped maintenance, use TenantExemptionContext."
            )

        # Log mode (dry run)
        stack_summary = "".join(traceback.format_stack(limit=5)[:-1])
        logger.warning(
            "MULTITENANCY_AUDIT_WARNING: %s called without tenant context in dry-run mode. "
            "Self-granted skip=%s. Call stack:\n%s",
            func_name,
            has_self_granted_skip,
            stack_summary,
        )
        return True

    if is_async:

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Clean up skip_tenant_check parameter so target function doesn't crash on unexpected kwarg
            kwargs_copy = dict(kwargs)
            _validate_call(args, kwargs_copy)
            kwargs_copy.pop("skip_tenant_check", None)
            return await func(*args, **kwargs_copy)

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        kwargs_copy = dict(kwargs)
        _validate_call(args, kwargs_copy)
        kwargs_copy.pop("skip_tenant_check", None)
        return func(*args, **kwargs_copy)

    return sync_wrapper


def require_tenant_context(func: Callable) -> Callable:
    """Alias for enforce_multitenancy with clearer semantic naming."""
    return enforce_multitenancy(func)
