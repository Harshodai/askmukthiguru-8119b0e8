import os
import sys

# Ensure JWT_SECRET is set for import-time validation
os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET", "mock_jwt_secret_for_testing_12345")
os.environ["SARVAM_API_KEY"] = os.environ.get("SARVAM_API_KEY", "mock_sarvam_key_for_testing")

from dotenv import load_dotenv

# Add backend/ to sys.path so that 'from services...' imports work when
# pytest runs from the repo root (e.g. `pytest backend/tests/`).
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Force loading .env.test for all tests
test_env_path = os.path.join(_BACKEND_DIR, ".env.test")
if os.path.exists(test_env_path):
    load_dotenv(test_env_path, override=True)
