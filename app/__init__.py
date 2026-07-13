# Alias package to expose the actual backend.app package as top-level `app`.
# This module replaces itself with the real package located at backend/app.
import os
import sys
import importlib

# Ensure the backend root directory is on sys.path for imports.
_repo_root = os.path.dirname(os.path.abspath(__file__))
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

# Import the genuine backend.app package.
_real_app = importlib.import_module("backend.app")

# Replace the current module entry with the real package so that subsequent imports
# (e.g., `from app.config import settings`) resolve to the backend implementation.
# Preserve any existing attributes on the stub (none in this case).
sys.modules[__name__] = _real_app

