"""RLIMIT_DATA counts virtual memory (thread stacks, malloc arenas), not RSS.

Proven 2026-09-26: with RLIMIT_DATA at 512 MB and 400 MB of untouched private
mappings, the 13th thread fails with "can't start new thread". The backend's
virtual size runs ~3x RSS, so a ceiling near the container limit broke thread
creation at ~60% real use. Guard the config that keeps that from recurring.
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_compose_disables_rlimit_by_default_and_caps_malloc_arenas():
    compose = (BACKEND / "docker-compose.yml").read_text()
    assert "PYTHON_MEMORY_LIMIT_MB=${PYTHON_MEMORY_LIMIT_MB:-0}" in compose
    assert "MALLOC_ARENA_MAX=2" in compose


def test_images_cap_malloc_arenas():
    for name in ("Dockerfile", "Dockerfile.railway"):
        assert "MALLOC_ARENA_MAX=2" in (BACKEND / name).read_text(), name


def test_rlimit_is_exactly_the_configured_value_or_off():
    src = (BACKEND / "app" / "main.py").read_text()
    assert "_limit_bytes = _mb * 1024 * 1024" in src
    assert "if _mb > 0:" in src


def test_pytest_process_has_no_rlimit_data_ceiling():
    """L-CI-RLIMIT-1: tests/conftest.py must switch app.main's RLIMIT_DATA cap off.

    The 6144 MB default counts virtual memory; a full-suite pytest process
    exceeds it on CI runners ("can't start new thread", MemoryError, exit 134).
    Skipped only if the operator deliberately exported a ceiling.
    """
    import os
    import resource

    import pytest

    if os.environ.get("PYTHON_MEMORY_LIMIT_MB", "0") not in ("", "0"):
        pytest.skip("PYTHON_MEMORY_LIMIT_MB explicitly set by the operator")
    soft, _hard = resource.getrlimit(resource.RLIMIT_DATA)
    assert soft == resource.RLIM_INFINITY


def test_ci_pytest_steps_cap_malloc_arenas():
    root = BACKEND.parent / ".github" / "workflows"
    for name in ("lint-test.yml", "production-readiness.yml"):
        assert 'MALLOC_ARENA_MAX: "2"' in (root / name).read_text(), name
