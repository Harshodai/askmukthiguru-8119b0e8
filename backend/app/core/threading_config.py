"""Threading environment configuration.

Keep this module dependency-free so it can be imported before any heavy
libraries (torch, numpy, sentence-transformers, etc.) are loaded.
"""

from __future__ import annotations

import os


def configure_threading() -> None:
    """Set CPU-threading environment variables to avoid oversubscription.

    Uses os.environ.setdefault so that explicitly provided values are never
    overwritten. Should be called once at process startup before importing
    numerical libraries.
    """
    for key, value in (
        ("OMP_NUM_THREADS", "1"),
        ("MKL_NUM_THREADS", "1"),
        ("OPENBLAS_NUM_THREADS", "1"),
        ("VECLIB_MAXIMUM_THREADS", "1"),
        ("NUMEXPR_NUM_THREADS", "1"),
    ):
        os.environ.setdefault(key, value)
