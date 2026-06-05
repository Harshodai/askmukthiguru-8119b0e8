import os
import sys

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
