#!/usr/bin/env python3
"""Mechanical guards for lessons that repeated even though lessons.md recorded them.

  publication FILES...  L-PUBLIC-REPO-1   block NEW clip-text/audio/dump files in the public repo
  claims FILES...       L-GO-NEEDS-COMMAND-1 / L-PRELAUNCH-SKIP-1  block unqualified "ready/GO/green" in added doc lines

Run by pre-commit (local hooks) and by the CI pre-commit step, so --no-verify does not bypass them.
Diff base for `claims`: $GUARD_BASE, else staged changes, else HEAD~1.
"""

from __future__ import annotations

import csv
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOW = ROOT / "scripts/guards/publication_allowlist.txt"
# Files that already violated a publication rule when that rule was introduced.
# Recorded, not approved: they stay visible here so the debt is countable, and the
# rule still blocks every file that is not listed. Removing an entry (after
# redacting the file) is progress; adding one needs the same owner decision as the
# allowlist (T-A1, L-PUBLIC-REPO-1).
BASELINE = ROOT / "scripts/guards/publication_baseline.txt"

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
# Same text-field policy as ``TEXT_COLS`` for CSV: a JSON/JSONL export that
# carries the teacher's words is the same disclosure whichever container it is in.
FORBIDDEN_JSON_KEYS = {
    "verbatim",
    "verbatim_text",
    "live_verbatim_text",
    "reconstructed_text",
    "source_transcript_text",
    "transcript",
    "clip_text",
    "passage",
    "passage_text",
}
HOME_PATH_RE = re.compile(r"/(?:Users|home)/[a-zA-Z0-9_-]+(?:/|$)")
# Machine-local launch config: an absolute interpreter path is the only valid
# value here, so the home-path rule cannot apply. Everything else is in scope.
HOME_PATH_EXEMPT = frozenset({".mcp.json"})


def _read_path_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")
    ]


def allowed() -> set[str]:
    """Owner-approved allowlist paths (exempt as recorded, T-A1)."""
    return set(_read_path_list(ALLOW))


def baseline_state() -> dict[str, str]:
    """Baseline path -> sha256 recorded when the violation was first logged.

    Format: ``<sha256>  <path>``. A bare path line carries no recorded state and
    is therefore NOT exempt (fail-closed): an unreviewed line would otherwise
    exempt whatever that path holds later.
    """
    state: dict[str, str] = {}
    for line in _read_path_list(BASELINE):
        parts = line.split(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            state[parts[1].strip()] = parts[0]
    return state


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def baseline_exempt(path: str) -> bool:
    """True only for an UNCHANGED baseline violation.

    The baseline records what was already committed when the rule landed. A file
    that changed afterwards (or that cannot be read) is checked normally, so the
    entry cannot be used to launder newly added teacher text or home paths.
    """
    recorded = baseline_state().get(path)
    if not recorded:
        return False
    return _file_sha256(ROOT / path) == recorded


REDACTED_VALUE = "[REDACTED]"


def _json_records(content: str) -> list:
    """Split a file into records: the whole document for JSON, per line for JSONL."""
    try:
        return [json.loads(content)]
    except ValueError:
        pass
    records: list = []
    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            # Not JSONL: keep the raw line so the substring check still runs.
            records.append({"__raw_line__": line})
    return records


def _unredacted_key(node: object) -> str | None:
    """First forbidden text key whose OWN value is not redacted.

    A record-level ``"redacted": true`` flag is not evidence about a value: a
    record can claim redaction and still carry the text. Only the value itself
    proves it.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FORBIDDEN_JSON_KEYS and isinstance(value, str):
                if value.strip() and value.strip() != REDACTED_VALUE:
                    return key
            hit = _unredacted_key(value)
            if hit:
                return hit
    elif isinstance(node, list):
        for item in node:
            hit = _unredacted_key(item)
            if hit:
                return hit
    return None


def _any_string_matches(node: object, pattern: re.Pattern[str]) -> bool:
    """True when any decoded string value (or dict key) in this record matches."""
    if isinstance(node, str):
        return bool(pattern.search(node))
    if isinstance(node, dict):
        return any(
            _any_string_matches(key, pattern) or _any_string_matches(value, pattern)
            for key, value in node.items()
        )
    if isinstance(node, list):
        return any(_any_string_matches(item, pattern) for item in node)
    return False


def _raw_line_key(line: str) -> str | None:
    """Invalid-JSON fallback: a forbidden key whose own value is a real string."""
    for key in FORBIDDEN_JSON_KEYS:
        for match in re.finditer(rf'"{re.escape(key)}"\s*:\s*"([^"]*)"', line):
            value = match.group(1).strip()
            if value and value != REDACTED_VALUE:
                return key
    return None


def publication_problem(path: str) -> str | None:
    if path in allowed() or baseline_exempt(path):
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
    if p.suffix.lower() in (".json", ".jsonl") and full.is_file():
        try:
            # Whole file, not the first 64 KB: sensitive records sit anywhere in
            # a large export, and truncation silently exempts everything after it.
            content = full.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            # Unreadable is not clean: a publication check that cannot read the
            # file cannot clear it.
            return f"{path}: unreadable for the publication check ({exc}) (L-PUBLIC-REPO-1)"
        records = _json_records(content)
        if path not in HOME_PATH_EXEMPT:
            # The raw regex misses JSON-escaped forms such as "\/Users\/x", so the
            # decoded string values are checked too. The raw check stays as the
            # fallback for lines that are not JSON at all.
            if HOME_PATH_RE.search(content) or any(
                _any_string_matches(record, HOME_PATH_RE)
                for record in records
                if not (isinstance(record, dict) and "__raw_line__" in record)
            ):
                return f"{path}: file contains local user home path (e.g. /Users/ or /home/)"
        # Each record is checked on its own: a redaction marker in one record must
        # never exempt unredacted text in another.
        for record in records:
            if isinstance(record, dict) and "__raw_line__" in record:
                hit = _raw_line_key(str(record["__raw_line__"]))
            else:
                hit = _unredacted_key(record)
            if hit:
                return f"{path}: JSON/JSONL has unredacted teacher text key '{hit}' (L-PUBLIC-REPO-1)"
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
