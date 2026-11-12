#!/usr/bin/env python3
"""Block Lovable-bot PRs that change sensitive paths without a human review label.

NEW-LOV-02. Reads changed file paths (one per line) on stdin. Environment:
  PR_AUTHOR  login of the PR author
  PR_LABELS  comma-separated label names

Exit 1 only when the author is the Lovable bot, a protected path changed, and the
label `lovable-reviewed` is absent. Human PRs are never blocked here. This script
never merges anything.
"""

from __future__ import annotations

import os
import sys

BOT_LOGIN = "gpt-engineer-app[bot]"
REVIEW_LABEL = "lovable-reviewed"

PROTECTED_PREFIXES = (
    "supabase/migrations/",
    "supabase/functions/",
    "src/integrations/supabase/",
)
PROTECTED_NAMES = {"package.json", "package-lock.json"}


def is_protected(path: str) -> bool:
    path = path.strip().removeprefix("./")
    if not path:
        return False
    base = path.rsplit("/", 1)[-1]
    if path.startswith(PROTECTED_PREFIXES):
        return True
    if path in PROTECTED_NAMES:
        return True
    if base.startswith("bun.lock") and "/" not in path:
        return True
    if base.startswith(".env"):
        return True
    return "/" not in path and path.endswith(".md")  # root markdown only


def violations(paths: list[str]) -> list[str]:
    return [p.strip() for p in paths if is_protected(p)]


def main() -> int:
    author = os.environ.get("PR_AUTHOR", "")
    labels = {x.strip() for x in os.environ.get("PR_LABELS", "").split(",") if x.strip()}
    found = violations(sys.stdin.read().splitlines())
    if author != BOT_LOGIN:
        print(f"author {author!r} is not {BOT_LOGIN}; this job does not block it.")
        return 0
    if not found:
        print("Lovable PR touches no protected path.")
        return 0
    if REVIEW_LABEL in labels:
        print(f"Protected paths changed, label {REVIEW_LABEL!r} present:")
        print("\n".join(found))
        return 0
    print(f"FAIL: a {BOT_LOGIN} PR changes protected paths without label {REVIEW_LABEL!r}:")
    print("\n".join(found))
    print("A human must review these files, then add the label.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
