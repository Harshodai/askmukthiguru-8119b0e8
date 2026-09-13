"""Regression and contract tests: multitenancy guard enforcement.

Ensures that Qdrant search/upsert operations cannot proceed without
verified tenant context (tenant_id, teacher_id, scope, or TenantContext),
preventing cross-tenant data leaks (Launch Gate 0.3).
"""

from __future__ import annotations

import logging

import pytest

from app.config import settings
from rag.corpus_scope import CorpusScope
from services.qdrant.indexer import QdrantIndexer
from services.qdrant.multitenancy_guard import (
    ALLOWED_UNSCOPED_OPERATIONS,
    MultitenancyViolation,
    TenantExemptionContext,
    enforce_multitenancy,
)
from services.qdrant.searcher import QdrantSearcher
from services.tenant_context import TenantContext


@enforce_multitenancy
def dummy_search(query_vector, teacher_id=None, scope=None, **kwargs):
    """Mock search function for testing."""
    return {"teacher_id": teacher_id, "scope": scope, "results": 42}


@enforce_multitenancy
def dummy_upsert(texts, teacher_id=None, metadatas=None, **kwargs):
    """Mock upsert function for testing."""
    return {"teacher_id": teacher_id, "metadatas": metadatas, "upserted": len(texts)}


class TestMultitenancyGuard:
    """Multitenancy enforcement tests under Gate 0.3."""

    @pytest.fixture(autouse=True)
    def clean_tenant_context(self):
        """Ensure each test starts with a clean tenant context and resets afterward."""
        TenantContext.clear()
        yield
        TenantContext.reset()

    def test_enforce_mode_search_without_context_raises(self, monkeypatch):
        """Search without tenant context must raise MultitenancyViolation in enforce mode."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "enforce")

        with pytest.raises(MultitenancyViolation) as exc_info:
            dummy_search([1, 2, 3])

        assert "dummy_search" in str(exc_info.value)
        assert "cross-tenant data leaks" in str(exc_info.value)

    def test_enforce_mode_search_with_teacher_id_succeeds(self, monkeypatch):
        """Search with teacher_id must succeed in enforce mode."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "enforce")

        result = dummy_search([1, 2, 3], teacher_id="sri-preethaji")
        assert result["teacher_id"] == "sri-preethaji"
        assert result["results"] == 42

    def test_enforce_mode_search_with_scope_succeeds(self, monkeypatch):
        """Search with CorpusScope must succeed in enforce mode."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "enforce")

        scope = CorpusScope(tenant_id="oneness", corpus_id="askmukthiguru", teacher_id="preethaji")
        result = dummy_search([1, 2, 3], scope=scope)
        assert result["scope"].tenant_id == "oneness"
        assert result["results"] == 42

    def test_enforce_mode_search_with_tenant_context_succeeds(self, monkeypatch):
        """Search inside TenantContext.scope(...) must succeed in enforce mode."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "enforce")
        with TenantContext.scope("tenant_abc"):
            result = dummy_search([1, 2, 3])
            assert result["results"] == 42

    def test_enforce_mode_upsert_without_context_raises(self, monkeypatch):
        """Upsert without tenant context must raise MultitenancyViolation in enforce mode."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "enforce")

        with pytest.raises(MultitenancyViolation):
            dummy_upsert(["text1", "text2"])

    def test_enforce_mode_upsert_with_metadata_context_succeeds(self, monkeypatch):
        """Upsert with metadata carrying tenant_id/teacher_id must succeed in enforce mode."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "enforce")

        metas = [{"source_url": "https://youtu.be/abc", "tenant_id": "oneness", "teacher_id": "ekam"}]
        result = dummy_upsert(["text1"], metadatas=metas)
        assert result["upserted"] == 1

    def test_self_granted_skip_tenant_check_rejected_in_enforce_mode(self, monkeypatch):
        """Caller passing skip_tenant_check=True must be rejected in enforce mode (no Swiss cheese)."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "enforce")

        with pytest.raises(MultitenancyViolation) as exc_info:
            dummy_search([1, 2, 3], skip_tenant_check=True)

        assert "self-granted skip_tenant_check" in str(exc_info.value)

    def test_tenant_exemption_context_allows_authorized_operation(self, monkeypatch):
        """TenantExemptionContext allows authorized system operations from the allowlist."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "enforce")

        assert "qdrant_backup" in ALLOWED_UNSCOPED_OPERATIONS

        with TenantExemptionContext("qdrant_backup"):
            result = dummy_search([1, 2, 3])
            assert result["results"] == 42

    def test_tenant_exemption_context_rejects_unauthorized_operation(self):
        """TenantExemptionContext rejects unauthorized operation names."""
        with pytest.raises(MultitenancyViolation) as exc_info:
            with TenantExemptionContext("unauthorized_hack_operation"):
                pass

        assert "unauthorized_hack_operation" in str(exc_info.value)
        assert "ALLOWED_UNSCOPED_OPERATIONS" in str(exc_info.value)

    def test_log_mode_does_not_raise(self, monkeypatch, caplog):
        """In log mode, unscoped operations emit an audit warning but do not raise."""
        monkeypatch.setattr(settings, "multitenancy_guard_mode", "log")

        with caplog.at_level(logging.WARNING):
            result = dummy_search([1, 2, 3])

        assert result["results"] == 42
        assert any("MULTITENANCY_AUDIT_WARNING" in rec.message for rec in caplog.records)

    def test_production_methods_are_wrapped_and_enumerated(self):
        """CI gate: verify all critical Qdrant entrypoints are decorated with enforce_multitenancy."""
        # QdrantSearcher.search
        assert hasattr(QdrantSearcher.search, "__wrapped__"), "QdrantSearcher.search must be decorated"

        # QdrantIndexer.upsert_chunks
        assert hasattr(QdrantIndexer.upsert_chunks, "__wrapped__"), "QdrantIndexer.upsert_chunks must be decorated"

    def test_multiple_teachers_isolated(self):
        """Different teachers get different tenant context."""
        result1 = dummy_search([1, 2, 3], teacher_id="preethaji")
        result2 = dummy_search([1, 2, 3], teacher_id="krishnaji")

        assert result1["teacher_id"] == "preethaji"
        assert result2["teacher_id"] == "krishnaji"
        assert result1["teacher_id"] != result2["teacher_id"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
