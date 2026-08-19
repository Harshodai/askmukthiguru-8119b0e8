"""Multitenancy enforcement: guard decorator for search/upsert operations.

Ensures all Qdrant operations include teacher_id (or other tenant isolator).
Raises loud if called without tenant context, preventing cross-tenant data leaks.
"""

import functools
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


class MultitenancyViolation(Exception):
    """Raised when a Qdrant operation is missing required tenant context."""

    pass


def enforce_multitenancy(func: Callable) -> Callable:
    """Decorator: enforce that search/upsert includes teacher_id or tenant filter.

    Usage:
        @enforce_multitenancy
        def search(self, query_vector, teacher_id=None, **kwargs):
            ...

    Raises:
        MultitenancyViolation: if teacher_id is None
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        teacher_id = kwargs.get("teacher_id")

        # teacher_id can be missing only for:
        # - Internal tests (marked with skip_tenant_check=True)
        # - Admin operations that explicitly override
        skip_check = kwargs.pop("skip_tenant_check", False)

        if not skip_check and teacher_id is None:
            raise MultitenancyViolation(
                f"{func.__qualname__}() called without teacher_id. "
                "This could cause cross-tenant data leaks. "
                "Pass teacher_id=... or skip_tenant_check=True for tests."
            )

        return func(*args, **kwargs)

    return wrapper


def require_tenant_context(func: Callable) -> Callable:
    """Alias: enforce_multitenancy with clearer name."""
    return enforce_multitenancy(func)


if __name__ == "__main__":
    # Self-check
    @enforce_multitenancy
    def dummy_search(query_vector, teacher_id=None):
        return f"searched with teacher_id={teacher_id}"

    # Should fail
    try:
        dummy_search([1, 2, 3])
        print("✗ Should have raised MultitenancyViolation")
    except MultitenancyViolation as e:
        print(f"✓ Correctly raised: {e}")

    # Should pass
    result = dummy_search([1, 2, 3], teacher_id="sri-preethaji")
    print(f"✓ With teacher_id: {result}")

    # Should pass with skip
    result = dummy_search([1, 2, 3], skip_tenant_check=True)
    print(f"✓ With skip_tenant_check: {result}")
