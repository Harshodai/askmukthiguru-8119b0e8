"""Docker build-context coverage: local non-runtime data must never enter the image.

.dockerignore patterns are matched relative to the build context root and,
unlike .gitignore, a bare pattern with no "/" (e.g. "data/") is anchored at
the root only — it does NOT recurse into subdirectories such as backend/data/.
The repo's root .dockerignore had a bare "data/" rule that looked like it
covered backend/data/book/ but never did, so an ignored local book/transcript
file could enter the image via `COPY backend/ .` in backend/Dockerfile.
(audit 2026-08-24, OH-P1-01)
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERIGNORE = _REPO_ROOT / ".dockerignore"


def _load_patterns() -> list[str]:
    lines = _DOCKERIGNORE.read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def _is_ignored(rel_path: str, patterns: list[str]) -> bool:
    for raw in patterns:
        pattern = raw.rstrip("/")
        if pattern.startswith("**/"):
            suffix = pattern[3:]
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(Path(rel_path).name, suffix):
                return True
        elif "/" in pattern:
            if rel_path == pattern or rel_path.startswith(pattern + "/"):
                return True
        else:
            # Bare pattern, no "/": Docker anchors it at the context root only.
            if rel_path == pattern:
                return True
    return False


def test_backend_data_book_excluded_from_build_context():
    patterns = _load_patterns()
    assert _is_ignored("backend/data/book/The_Four_Sacred_Secrets_structure.json", patterns)
    assert _is_ignored("backend/data/anything.txt", patterns)


def test_bare_data_pattern_does_not_recurse_into_backend():
    """Confirms the root cause: a bare `data/` rule matches ./data only, not backend/data/."""
    patterns = ["data/"]
    assert not _is_ignored("backend/data/book/foo.json", patterns)


if __name__ == "__main__":
    test_backend_data_book_excluded_from_build_context()
    test_bare_data_pattern_does_not_recurse_into_backend()
    print("ok")
