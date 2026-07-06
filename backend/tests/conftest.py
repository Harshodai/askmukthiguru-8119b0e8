import os
import sys
import warnings

# Suppress all warnings ruthlessly during testing
warnings.filterwarnings("ignore")

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
import pytest


@pytest.fixture(autouse=True)
def _restore_event_loop():
    # ponytail: asyncio.run() closes and unsets the thread's current event loop;
    # downstream tests using get_event_loop() then raise RuntimeError. Keep a
    # current loop alive before and after each test so cross-file ordering works.
    asyncio.set_event_loop(asyncio.new_event_loop())
    yield
    asyncio.set_event_loop(asyncio.new_event_loop())

