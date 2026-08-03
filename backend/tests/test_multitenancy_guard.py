"""Regression tests: multitenancy guard enforcement.

Ensures that Qdrant search/upsert operations cannot proceed without
explicit tenant context (teacher_id), preventing cross-tenant data leaks.
"""

import pytest

from services.qdrant.multitenancy_guard import (
    MultitenancyViolation,
    enforce_multitenancy,
)


@enforce_multitenancy
def dummy_search(query_vector, teacher_id=None, **kwargs):
    """Mock search function for testing."""
    return {"teacher_id": teacher_id, "results": 42}


@enforce_multitenancy
def dummy_upsert(texts, teacher_id=None, **kwargs):
    """Mock upsert function for testing."""
    return {"teacher_id": teacher_id, "upserted": len(texts)}


class TestMultitenancyGuard:
    """Multitenancy enforcement tests."""

    def test_search_without_teacher_id_raises(self):
        """Search without teacher_id must raise MultitenancyViolation."""
        with pytest.raises(MultitenancyViolation) as exc_info:
            dummy_search([1, 2, 3])

        assert "teacher_id" in str(exc_info.value)
        assert "cross-tenant" in str(exc_info.value)

    def test_search_with_teacher_id_succeeds(self):
        """Search with teacher_id must succeed."""
        result = dummy_search([1, 2, 3], teacher_id="sri-preethaji")
        assert result["teacher_id"] == "sri-preethaji"
        assert result["results"] == 42

    def test_upsert_without_teacher_id_raises(self):
        """Upsert without teacher_id must raise MultitenancyViolation."""
        with pytest.raises(MultitenancyViolation):
            dummy_upsert(["text1", "text2"])

    def test_upsert_with_teacher_id_succeeds(self):
        """Upsert with teacher_id must succeed."""
        result = dummy_upsert(["text1", "text2"], teacher_id="sri-krishnaji")
        assert result["teacher_id"] == "sri-krishnaji"
        assert result["upserted"] == 2

    def test_skip_tenant_check_allows_bypass(self):
        """skip_tenant_check=True allows tests to bypass guard."""
        result = dummy_search([1, 2, 3], skip_tenant_check=True)
        assert result["teacher_id"] is None  # No teacher_id, but still works
        assert result["results"] == 42

    def test_multiple_teachers_isolated(self):
        """Different teachers get different tenant context."""
        result1 = dummy_search([1, 2, 3], teacher_id="preethaji")
        result2 = dummy_search([1, 2, 3], teacher_id="krishnaji")

        assert result1["teacher_id"] == "preethaji"
        assert result2["teacher_id"] == "krishnaji"
        assert result1["teacher_id"] != result2["teacher_id"]

    def test_error_message_is_clear(self):
        """Error message guides users on how to fix."""
        with pytest.raises(MultitenancyViolation) as exc_info:
            dummy_search([1, 2, 3])

        msg = str(exc_info.value)
        assert "dummy_search()" in msg  # Function name
        assert "teacher_id" in msg  # Parameter name
        assert "skip_tenant_check" in msg  # Escape hatch


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
