#!/usr/bin/env python3
"""CLI: python -m scripts.okf_compile

Rebuild the OKF compiled index from memory/okf/ markdown files.
"""

import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.memory.compiler import compile_okf

if __name__ == "__main__":
    path = compile_okf()
    print(f"OKF compiled → {path}")
