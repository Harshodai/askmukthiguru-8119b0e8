#!/usr/bin/env python3
"""Unified benchmark harness entry point for AskMukthiGuru.

CLI: python -m benchmarks.run [OPTIONS]
Delegates directly to evaluation.bench, providing a single entry point for all
benchmark and evaluation modes (retrieval, e2e, voice, all) across all 9
question banks.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evaluation.bench import main

if __name__ == "__main__":
    raise SystemExit(main())
