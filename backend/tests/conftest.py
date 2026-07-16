import os
import sys
import warnings

# Suppress all warnings ruthlessly during testing — must be set BEFORE any
# third-party imports to catch import-time warnings.
warnings.filterwarnings("ignore")

# The LangChainPendingDeprecationWarning (langchain_core bug) has a mismatch
# between its instance class and the category argument passed to warnings.warn,
# so filterwarnings("ignore") doesn't suppress it. Catch it with a static filter
# before any third-party import triggers it.
_orig_warn_fn = warnings.warn

def _suppress_langchain_warn(*args, **kwargs):
    if args and "allowed_objects" in str(args[0]):
        return
    return _orig_warn_fn(*args, **kwargs)

warnings.warn = _suppress_langchain_warn

# Add backend/ to sys.path first so that 'app' and 'services' imports resolve
# regardless of whether pytest is invoked from the repo root or backend/.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

# Configure threading limits before heavy numerical libraries are imported.
from app.core.threading_config import configure_threading

configure_threading()

# Point REDIS_URL to local host-mapped Redis for testing
os.environ["REDIS_URL"] = "redis://:mukthiguru_redis_pass@127.0.0.1:6379/0"
os.environ["IS_PRODUCTION"] = "false"



# Ensure JWT_SECRET is set for import-time validation
os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET", "mock_jwt_secret_for_testing_12345")
os.environ["SARVAM_API_KEY"] = os.environ.get("SARVAM_API_KEY", "mock_sarvam_key_for_testing")

from dotenv import load_dotenv

# Force loading .env.test for all tests
test_env_path = os.path.join(_BACKEND_DIR, ".env.test")
if os.path.exists(test_env_path):
    load_dotenv(test_env_path, override=True)

# Disable rate limiting during tests to avoid Redis connections
from app.core.limiter import limiter

limiter.enabled = False

import asyncio
import logging

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture
def supabase_client():
    """Provide a real Supabase client if SUPABASE_URL and SUPABASE_KEY are set.

    Skips the test with a clear message if either env var is missing,
    allowing tests to run in CI or environments without Supabase.
    """
    from app.config import settings

    supabase_url = settings.supabase_url
    supabase_key = settings.supabase_key

    if not supabase_url or not supabase_key or supabase_key == "":
        pytest.skip(
            "SUPABASE_URL or SUPABASE_KEY not set — skipping Supabase integration test. "
            "Set both in backend/.env or backend/.env.test to run."
        )

    try:
        from supabase import create_client

        client = create_client(supabase_url, supabase_key)
        # Verify connectivity with a lightweight request
        try:
            client.table("_prisma_migrations").select("*", count="exact").limit(1).execute()
        except Exception:
            pytest.skip(
                f"Supabase at {supabase_url} is not reachable — "
                "start the local Supabase stack with 'npx supabase start'"
            )
        logger.info("Supabase client initialized for %s", supabase_url)
        yield client
    except Exception as e:
        pytest.skip(f"Supabase client initialization failed: {e}")


@pytest.fixture(autouse=True)
def _restore_event_loop():
    # ponytail: asyncio.run() closes and unsets the thread's current event loop;
    # downstream tests using get_event_loop() then raise RuntimeError. Keep a
    # current loop alive before and after each test so cross-file ordering works.
    asyncio.set_event_loop(asyncio.new_event_loop())
    yield
    asyncio.set_event_loop(asyncio.new_event_loop())


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    # ponytail: app.dependency_overrides is a dict on the single shared `app`
    # object imported by every test module; several tests (test_edge_cases.py,
    # test_chat_endpoint.py) set app.dependency_overrides[get_container] /
    # [get_current_user_from_supabase] and never clear it, so it leaks into
    # every test that runs later in the same process and shares `app` (e.g.
    # test_health.py's client = TestClient(app) — the exact failure this fixes).
    # Snapshot + restore rather than blind-clear, in case a future test wants
    # a genuinely persistent override across its own sub-tests.
    from app.main import app as _app

    saved = dict(_app.dependency_overrides)
    yield
    _app.dependency_overrides.clear()
    _app.dependency_overrides.update(saved)

