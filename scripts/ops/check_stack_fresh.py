#!/usr/bin/env python3
"""Fail if the running Docker stack is older than the code or .env it is supposed to test.

Repeated lesson: fixes sat un-restarted, so live tests ran on stale code (env_file changes need a
recreate, not a restart; frontend changes need a rebuild). Run before ANY live/Docker verification:
    make verify-stack-fresh        exit 0 fresh, 1 stale, 2 cannot tell (treated as NOT fresh)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTAINER = "mukthiguru-backend"
WATCH = ["backend", "memory/okf/compiled.json", "config", ".env"]


def ts(s: str) -> float:
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00"))  # docker emits nanoseconds
    return datetime.fromisoformat(s).timestamp()


def verdict(
    started: float, image_created: float, code_changed: float, env_changed: float
) -> tuple[int, str]:
    if code_changed > image_created:
        return (
            1,
            "code changed after the image was built: rebuild (`docker compose build backend`) then recreate",
        )
    if env_changed > started:
        return (
            1,
            ".env changed after the container started: recreate (`up -d --no-deps --force-recreate backend`), restart is not enough",
        )
    return 0, "stack is newer than code and .env"


def newest_mtime(paths: list[str]) -> float:
    best = 0.0
    for p in paths:
        base = ROOT / p
        files = [base] if base.is_file() else base.rglob("*.py") if base.exists() else []
        for f in files:
            if ".venv" in f.parts or "__pycache__" in f.parts or "tests" in f.parts:
                continue
            best = max(best, f.stat().st_mtime)
    return best


def main() -> int:
    r = subprocess.run(["docker", "inspect", CONTAINER], capture_output=True, text=True)
    if r.returncode != 0:
        print(
            f"CANNOT TELL: {CONTAINER} not inspectable ({r.stderr.strip()[:100]}). Treat as NOT fresh."
        )
        return 2
    c = json.loads(r.stdout)[0]
    img = json.loads(
        subprocess.run(["docker", "inspect", c["Image"]], capture_output=True, text=True).stdout
    )[0]
    code = newest_mtime([p for p in WATCH if p != ".env"])
    env = newest_mtime([".env"])
    rc, why = verdict(ts(c["State"]["StartedAt"]), ts(img["Created"]), code, env)
    print(("FRESH: " if rc == 0 else "STALE: ") + why)
    return rc


if __name__ == "__main__":
    sys.exit(main())
