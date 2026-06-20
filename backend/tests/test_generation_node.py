"""Tests for generation node budget capping and SarvamCloudService DI."""

import inspect

import pytest

from rag.nodes import _services


class TestGenerationTokenBudget:
    """Validate structurally that the budget masking bug is fixed."""

    def test_max_500_removed(self):
        """Check that max(500, ...) was removed from generation.py."""
        from rag.nodes import generation
        source = inspect.getsource(generation)
        assert "max(500, allowed_knowledge_tokens)" not in source, "Old max(500, ...) pattern still present"

    def test_allowed_knowledge_tokens_clamped_to_zero(self):
        """allowed_knowledge_tokens must be clamped to at least 0."""
        from rag.nodes import generation
        source = inspect.getsource(generation)
        assert "max(0, max_budget - (sys_tokens + base_user_tokens + 250))" in source, "Budget clamped to zero not found"


class TestSarvamCloudDI:
    """Confirm SarvamCloudService is injected via DI, not a lazy node singleton."""

    def test_sarvam_cloud_injected_into_services(self):
        """_sarvam_cloud must be a module-level attribute."""
        assert hasattr(_services, "_sarvam_cloud"), "_sarvam_cloud not in _services"

    def test_no_module_level_lazy_singleton(self):
        """Ensure the module-level _sarvam_cloud_service global was removed."""
        from rag.nodes import generation
        assert "_sarvam_cloud_service" not in generation.__dict__, "Lazy singleton still present in generation"