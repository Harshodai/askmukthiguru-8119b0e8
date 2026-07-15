from __future__ import annotations

import os as _os
import sys as _sys
_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _SCRIPT_DIR in _sys.path:
    _sys.path.remove(_SCRIPT_DIR)
_BACKEND = _os.path.dirname(_SCRIPT_DIR)
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

"""
Mukthi Guru — ContainerBuilder re-export.

The Builder implementation lives in services/container_builder.py.
This module provides a stable import path under the app package for
callers that want the builder directly, without reaching across
package boundaries.
"""

from services.container_builder import ContainerBuilder

__all__ = ["ContainerBuilder"]


if __name__ == "__main__":
    # Self-check: module imports cleanly and the class is accessible.
    assert ContainerBuilder is not None
    print("C2 OK")