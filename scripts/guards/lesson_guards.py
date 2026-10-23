#!/usr/bin/env python3
"""Mechanical guards for lessons that repeated even though lessons.md recorded them.

  publication FILES...  L-PUBLIC-REPO-1   block NEW clip-text/audio/dump files in the public repo
  claims FILES...       L-GO-NEEDS-COMMAND-1 / L-PRELAUNCH-SKIP-1  block unqualified "ready/GO/green" in added doc lines

Run by pre-commit (local hooks) and by the CI pre-commit step, so --no-verify does not bypass them.
Diff base for `claims`: $GUARD_BASE, else staged changes, else HEAD~1.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOW = ROOT / "scripts/guards/publication_allowlist.txt"

BANNED_EXT = {".wav", ".mp3", ".m4a", ".flac", ".mp4", ".mov", ".dump", ".rdb"}
BANNED_PATH = re.compile(
    r"(^|/)(transcripts?|audio_archive|gold_set[^/]*)/|(^|/)labeling_[^/]*\.csv$"
)
# Code is exempt only inside gold_set dirs; transcripts/ and audio_archive/ hold data even as .py.
DATA_ONLY_DIR = re.compile(r"(^|/)(transcripts?|audio_archive)/")
TEXT_COLS = {
    "text",
    "verbatim",
    "verbatim_text",
    "clip_text",
    "transcript",
    "passage",
    "passage_text",
}


def allowed() -> set[str]:
    if not ALLOW.exists():
        return set()
    return {
        line.strip()
        for line in ALLOW.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def publication_problem(path: str) -> str | None:
    if path in allowed():
        return None
    p = Path(path)
    if p.suffix.lower() in BANNED_EXT:
        return f"{path}: audio/video/DB-dump file type; the repo is public (L-PUBLIC-REPO-1)"
    is_gold_code = p.suffix.lower() == ".py" and not DATA_ONLY_DIR.search(path)
    if BANNED_PATH.search(path) and not is_gold_code:
        return f"{path}: transcript/gold-set/labeling path holds teacher or clip text (L-PUBLIC-REPO-1)"
    full = ROOT / path
    if p.suffix.lower() == ".csv" and full.is_file():
        with full.open(newline="", encoding="utf-8", errors="replace") as fh:
            head = next(csv.reader(fh), [])
        hit = TEXT_COLS & {h.strip().lower() for h in head}
        if hit:
            return f"{path}: CSV has clip-text column {sorted(hit)} (L-PUBLIC-REPO-1)"
    return None


# An unqualified readiness claim. Allowed when the same line says how it was proven or that it is not.
CLAIM = re.compile(
    r"\b(PROD(UCTION)?[- ]READY|FACULTY[- ]READY|ALL GREEN|VERDICT:?\s*\**GO\b|\bGO\b\s*(verdict|for (prod|launch|faculty)))",
    re.I,
)
QUALIFIER = re.compile(
    r"NO-GO|NOT |UNPROVEN|UNVERIFIED|\bnever\b|\bwas\b|\bwere\b|false|claim-ok|`[^`]*(make|pytest|python|docker|curl|npm|gh |bash)[^`]*`|\bcmd:|\bcommand:",
    re.I,
)


def claim_problems(path: str, added: list[str]) -> list[str]:
    out = []
    for line in added:
        if CLAIM.search(line) and not QUALIFIER.search(line):
            out.append(f"{path}: unqualified claim: {line.strip()[:110]!r}")
    return out


def added_lines(path: str) -> list[str]:
    base = os.environ.get("GUARD_BASE")
    cmds = (
        [["git", "diff", "-U0", base, "--", path]]
        if base
        else [
            ["git", "diff", "--cached", "-U0", "--", path],
            ["git", "diff", "-U0", "HEAD~1", "--", path],
        ]
    )
    for cmd in cmds:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return [
                line[1:]
                for line in r.stdout.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
    return []


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in {"publication", "claims"}:
        print(__doc__)
        return 2
    mode, files = argv[1], argv[2:]
    problems: list[str] = []
    for f in files:
        if mode == "publication":
            msg = publication_problem(f)
            problems += [msg] if msg else []
        elif f.endswith(".md") and not f.startswith(("research/", "docs/audits/RELEASE_EVIDENCE")):
            problems += claim_problems(f, added_lines(f))
    for p in problems:
        print(f"GUARD FAIL {p}")
    if problems:
        print(
            "Fix: stage by path without the file / add the command + env + date to the line / mark UNPROVEN. "
            "Owner-approved exceptions: scripts/guards/publication_allowlist.txt or `claim-ok`."
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
