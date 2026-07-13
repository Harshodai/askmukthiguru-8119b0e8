# Alias top-level `rag` package to the implementation under backend/rag.
import os, sys, importlib
_repo_root = os.path.dirname(os.path.abspath(__file__))
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)
_real_rag = importlib.import_module("backend.rag")
sys.modules[__name__] = _real_rag
