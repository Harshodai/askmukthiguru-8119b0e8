# Alias top-level `ingest` package to the real implementation under backend/ingest.
import os
import sys
import importlib

_repo_root = os.path.dirname(os.path.abspath(__file__))
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

_real_ingest = importlib.import_module("backend.ingest")
sys.modules[__name__] = _real_ingest
