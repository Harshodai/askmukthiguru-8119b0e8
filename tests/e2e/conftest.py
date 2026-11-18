"""conftest.py — Opaque-box E2E test configuration and shared fixtures.

Architectural guidelines:
1. Injects backend/ and repository root into sys.path.
2. Configures runtime environment: IS_PRODUCTION=false, ENABLE_TEST_AUTH=true,
   OTEL_ENABLED=false, PYTHON_MEMORY_LIMIT_MB=0.
3. Sets app.dependencies.startup_complete = True for un-stubbed serving paths.
4. Leaves genuine answering gates, relevance scoring, and word floors active.
   DOES NOT import gate-neutralizing stubs from backend/tests/conftest.py.
5. Provides fixtures for authenticated, unauthenticated, and incognito seekers,
   an in-memory authentic teaching store, and auto-resetting rate limiters.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Callable, Dict, Generator, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# 1. Path Injections & Process Environment
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"

for _p in (str(_REPO_ROOT), str(_BACKEND_DIR)):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

os.environ.setdefault("IS_PRODUCTION", "false")
os.environ.setdefault("ENABLE_TEST_AUTH", "true")
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("PYTHON_MEMORY_LIMIT_MB", "0")
os.environ.setdefault("PYTEST_CURRENT_TEST", "tests/e2e (call)")

import app.dependencies as _app_deps
from app.config import settings
from app.main import app
from services.auth_service import get_current_user_from_supabase, get_optional_user

# ---------------------------------------------------------------------------
# 2. Canonical Synthetic Teaching Constants
# ---------------------------------------------------------------------------
TEST_VIDEO_ID = "dQw4w9WgXcQ"  # 11-char YouTube ID shape
TEST_VIDEO_URL = f"https://www.youtube.com/watch?v={TEST_VIDEO_ID}"
TEST_TEACHING_TEXT_PREETHAJI = (
    "Awareness sees the movement of thought without following it, and in "
    "that seeing the mind grows still on its own."
)
TEST_TEACHING_TEXT_KRISHNAJI = (
    "When you observe your inner state without resistance or judgment, "
    "a profound transformation happens naturally in your consciousness."
)
TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


# ---------------------------------------------------------------------------
# 3. Environment & Startup Posture Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _ensure_e2e_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure process environment matches testing posture and gates remain real."""
    monkeypatch.setattr(_app_deps, "startup_complete", True, raising=False)
    monkeypatch.setattr(settings, "enable_test_auth", True, raising=False)
    monkeypatch.setattr(settings, "is_production", False, raising=False)
    monkeypatch.setattr(settings, "queue_enabled", False, raising=False)
    # Ensure legacy and context slots point to active context collection in v10-only terminal posture
    monkeypatch.setattr(settings, "first_person_collection", "first_person_v10", raising=False)
    monkeypatch.setattr(settings, "first_person_context_collection", "first_person_v10", raising=False)
    monkeypatch.setattr(settings, "first_person_active_collection", "first_person_v10", raising=False)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True, raising=False)
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True, raising=False)
    # Ensure YouTube availability check succeeds for test synthetic video IDs
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available",
        lambda _vid: True,
        raising=False,
    )
    # Authoritative licensing check succeeds for synthetic licensed clips
    monkeypatch.setattr(
        "services.first_person_rights.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        raising=False,
    )
    monkeypatch.setattr(
        "app.pipeline.stages.first_person_bridge.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        raising=False,
    )
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        raising=False,
    )
    monkeypatch.setattr(
        "services.first_person_store.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        raising=False,
    )
    monkeypatch.setattr(
        "app.pipeline.stages.personalize_stage.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        raising=False,
    )


@pytest.fixture(autouse=True)
def rate_limit_reset() -> Generator[None, None, None]:
    """Reset rate limiter singletons between tests to prevent test pollution."""
    from app.core.limiter import limiter
    import app.main as _main_mod

    try:
        limiter.reset()
    except Exception:
        pass
    admin_rl = getattr(_main_mod, "_ADMIN_RATE_LIMITER", None)
    if admin_rl is not None and hasattr(admin_rl, "reset_all"):
        try:
            admin_rl.reset_all()
        except Exception:
            pass
    auth_rl = getattr(_main_mod, "_AUTH_RATE_LIMITER", None)
    if auth_rl is not None and hasattr(auth_rl, "reset_all"):
        try:
            auth_rl.reset_all()
        except Exception:
            pass
    yield


# ---------------------------------------------------------------------------
# 4. In-Memory Authentic Teaching Store
# ---------------------------------------------------------------------------
class MockTeachingStore:
    """In-memory store providing authentic verified teaching clips."""

    def __init__(self) -> None:
        self.clips: dict[str, dict[str, Any]] = {}
        self._init_default_clips()

    def _init_default_clips(self) -> None:
        hash_preethaji = hashlib.sha256(TEST_TEACHING_TEXT_PREETHAJI.encode("utf-8")).hexdigest()
        hash_krishnaji = hashlib.sha256(TEST_TEACHING_TEXT_KRISHNAJI.encode("utf-8")).hexdigest()

        self.add_clip({
            "point_id": "authentic_preethaji_01",
            "video_id": TEST_VIDEO_ID,
            "start_ms": 99_000,
            "end_ms": 129_000,
            "speaker": "Sri Preethaji",
            "teacher_id": "preethaji",
            "verbatim_text": TEST_TEACHING_TEXT_PREETHAJI,
            "source_url": TEST_VIDEO_URL,
            "title": "On Quiet Observation and Meditation",
            "is_verbatim": True,
            "first_person_eligible": True,
            "rights_cleared": True,
            "domain_rights_status": "licensed",
            "transcript_hash": hash_preethaji,
            "source_text_hash": hash_preethaji,
            "speaker_verified": True,
            "corpus_version": "fp-context-transcript-v1",
        })

        self.add_clip({
            "point_id": "authentic_krishnaji_01",
            "video_id": "kR15hN4j101",
            "start_ms": 45_000,
            "end_ms": 75_000,
            "speaker": "Sri Krishnaji",
            "teacher_id": "krishnaji",
            "verbatim_text": TEST_TEACHING_TEXT_KRISHNAJI,
            "source_url": "https://www.youtube.com/watch?v=kR15hN4j101",
            "title": "Transformation in Consciousness",
            "is_verbatim": True,
            "first_person_eligible": True,
            "rights_cleared": True,
            "domain_rights_status": "licensed",
            "transcript_hash": hash_krishnaji,
            "source_text_hash": hash_krishnaji,
            "speaker_verified": True,
            "corpus_version": "fp-context-transcript-v1",
        })

    def add_clip(self, clip: dict[str, Any]) -> None:
        key = f"{clip['video_id']}:{clip['start_ms']}"
        self.clips[key] = clip

    def get_clip_by_video_and_start(
        self, video_id: str, timestamp_seconds: float, tolerance_s: float = 1.5
    ) -> Optional[dict[str, Any]]:
        target_ms = timestamp_seconds * 1000.0
        tol_ms = tolerance_s * 1000.0
        for clip in self.clips.values():
            if clip.get("video_id") == video_id:
                start_ms = clip.get("start_ms", 0.0)
                if abs(start_ms - target_ms) <= tol_ms:
                    return dict(clip)
        return None

    def get_clip_by_video_and_start_in_collection(
        self, collection: str, video_id: str, timestamp_seconds: float, tolerance_s: float = 1.5
    ) -> Optional[dict[str, Any]]:
        return self.get_clip_by_video_and_start(video_id, timestamp_seconds, tolerance_s)


@pytest.fixture
def mock_teaching_store(monkeypatch: pytest.MonkeyPatch) -> MockTeachingStore:
    """Fixture providing in-memory authentic clip store wired to personalize lookup."""
    store = MockTeachingStore()
    monkeypatch.setattr(
        "app.pipeline.stages.personalize_stage._store_for_request",
        lambda: store,
        raising=False,
    )
    monkeypatch.setattr(
        "services.first_person_serving_contract.legacy_slot_aliases_context",
        lambda *args: False,
        raising=False,
    )
    return store


# ---------------------------------------------------------------------------
# 5. Client Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def e2e_app() -> Any:
    """Configured FastAPI application instance with real answering gates."""
    return app


@pytest.fixture
def client(e2e_app: Any) -> Generator[TestClient, None, None]:
    """Base FastAPI TestClient."""
    with TestClient(e2e_app) as tc:
        yield tc


@pytest.fixture
def authenticated_client(e2e_app: Any) -> Generator[TestClient, None, None]:
    """TestClient authenticated as a registered seeker with verified identity."""
    async def _get_auth_user() -> dict[str, Any]:
        return {
            "id": TEST_USER_ID,
            "email": "seeker@askmukthiguru.org",
            "is_anonymous": False,
            "aal": "aal1",
        }

    app.dependency_overrides[get_optional_user] = _get_auth_user
    app.dependency_overrides[get_current_user_from_supabase] = _get_auth_user
    with TestClient(e2e_app) as tc:
        yield tc
    app.dependency_overrides.pop(get_optional_user, None)
    app.dependency_overrides.pop(get_current_user_from_supabase, None)


@pytest.fixture
def unauthenticated_client(e2e_app: Any) -> Generator[TestClient, None, None]:
    """TestClient simulating an anonymous unauthenticated seeker."""
    async def _get_anon_user() -> Optional[dict[str, Any]]:
        return None

    app.dependency_overrides[get_optional_user] = _get_anon_user
    with TestClient(e2e_app) as tc:
        yield tc
    app.dependency_overrides.pop(get_optional_user, None)


@pytest.fixture
def incognito_client(authenticated_client: TestClient) -> TestClient:
    """TestClient configured for temporary / incognito chat sessions."""
    return authenticated_client
