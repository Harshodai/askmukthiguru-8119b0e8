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
