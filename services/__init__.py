# Alias top-level `services` package to the implementation under backend/services.
import os, sys, importlib
_repo_root = os.path.dirname(os.path.abspath(__file__))
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)
_real_services = importlib.import_module("backend.services")
sys.modules[__name__] = _real_services
