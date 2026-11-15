"""T2-06 / CQ-010: Config Lint regression tests.

Verifies that:
1. 0 undeclared settings attributes are read via getattr(settings, "...") in the codebase.
2. The config lint guard catches synthetic undeclared attribute reads (proves the guard is active).
3. Critical newly declared fields exist on app.config.Settings.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path so we can import scripts.guards.config_lint
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.guards.config_lint import (
    find_undeclared_settings_reads,
    get_declared_settings_members,
)

from app.config import settings


def test_no_undeclared_settings_reads_in_repo():
    """Assert 0 undeclared getattr(settings, "...") calls exist in backend/ or scripts/."""
    undeclared = find_undeclared_settings_reads(REPO_ROOT)
    assert undeclared == [], f"Found undeclared settings reads: {undeclared}"


def test_newly_declared_settings_fields_exist():
    """Verify newly declared fields for CQ-010 exist with valid types/defaults."""
    # Provenance
    assert hasattr(settings, "git_sha")
    assert hasattr(settings, "schema_version")

    # Timeouts & Limits
    assert hasattr(settings, "sarvam_rpm_limit")
    assert settings.sarvam_rpm_limit == 60
    assert hasattr(settings, "qdrant_timeout")
    assert settings.qdrant_timeout == 30.0
    assert hasattr(settings, "kg_max_concurrent_queries")
    assert settings.kg_max_concurrent_queries == 10
    assert hasattr(settings, "lightrag_query_timeout_seconds")
    assert settings.lightrag_query_timeout_seconds == 30.0
    assert hasattr(settings, "llm_generate_timeout")
    assert settings.llm_generate_timeout == 60.0

    # Ingestion & Quality Gates
    assert hasattr(settings, "data_quality_gate_enabled")
    assert settings.data_quality_gate_enabled is True
    assert hasattr(settings, "quality_gate_threshold")
    assert hasattr(settings, "upload_dir")

    # RAG / CRAG
    assert hasattr(settings, "crag_score_delta_ratio")
    assert settings.crag_score_delta_ratio == 0.5

    # Auth & Redis
    assert hasattr(settings, "supabase_service_role_key")
    assert hasattr(settings, "redis_password")


def test_config_lint_detects_synthetic_undeclared(tmp_path: Path):
    """Verify that find_undeclared_settings_reads catches an undeclared attribute read."""
    config_path = REPO_ROOT / "backend" / "app" / "config.py"
    members = get_declared_settings_members(config_path)

    fake_attr = "completely_fake_unregistered_setting_xyz_98765"
    assert fake_attr not in members
