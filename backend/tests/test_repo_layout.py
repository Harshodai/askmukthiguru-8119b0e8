"""Repo-layout invariants: which tree owns a script.

This repo has two script trees, and they are NOT mirrors of each other:

  ``scripts/``          repo-level tooling (screenshots, graph indexers, bulk
                        ingestion drivers, ops runbooks)
  ``backend/scripts/``  modules that import backend packages and are run as
                        ``python -m scripts.<name>`` from ``backend/``

They share a directory *name*, not a purpose, and no sync mechanism connects
them (verified empirically: creating or editing a file under
``backend/scripts/ops/`` does not propagate to ``scripts/ops/``).

That makes a same-named file in both trees a hazard rather than a convention:
whichever copy an operator runs becomes a coin flip, and the two drift silently.
It has already happened once — an untracked ``scripts/ops/corpus_audit.py``
appeared alongside the tracked ``backend/scripts/ops/corpus_audit.py`` and was
byte-identical only by luck. The root copy could not even work on its own:
``corpus_audit`` derives ``_BACKEND = Path(__file__).resolve().parents[2]``,
which from the repo root points at the repo root, not ``backend/``.

The deliberate duplicate — ``scripts/extract_okf_from_stores.py`` and its
``backend/`` twin — is a different thing: both copies are git-tracked and held
identical by ``test_okf_pipeline_integrity.py::test_extractor_copies_are_identical``.
A duplicate is acceptable *when it is tracked and a test pins the two together*.
An unowned, untracked shadow copy is not.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOT_OPS = _REPO_ROOT / "scripts" / "ops"
_BACKEND_OPS = _REPO_ROOT / "backend" / "scripts" / "ops"

# Scripts intentionally present in both trees. Anything listed here MUST also be
# pinned identical by a test — see the OKF extractor pair for the pattern.
# Empty by design: ops scripts have a single canonical home in backend/scripts/ops.
_ALLOWED_DUPLICATES: frozenset[str] = frozenset()


def _script_names(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {
        p.name for p in directory.iterdir() if p.is_file() and p.suffix in {".py", ".sh", ".cjs"}
    }


def test_ops_script_trees_do_not_share_filenames():
    """One canonical home per ops script — no unowned shadow copies."""
    overlap = (_script_names(_ROOT_OPS) & _script_names(_BACKEND_OPS)) - _ALLOWED_DUPLICATES
    assert not overlap, (
        f"same filename in both ops trees: {sorted(overlap)}. "
        "scripts/ops/ and backend/scripts/ops/ are separate trees, not mirrors — "
        "nothing syncs them, so two same-named files drift and whichever one an "
        "operator runs is a coin flip. Delete the copy that is not canonical, or, "
        "if the duplicate is genuinely needed, track BOTH copies in git, add the "
        "name to _ALLOWED_DUPLICATES, and pin them identical with a test "
        "(see test_okf_pipeline_integrity.py::test_extractor_copies_are_identical)."
    )


def test_backend_ops_scripts_resolve_backend_as_their_import_root():
    """A backend ops script computes parents[2] == backend/, which is why a copy of
    one at the repo root is broken: from there the same expression yields the repo
    root and the ``services.*`` imports resolve wrongly or not at all."""
    sample = _BACKEND_OPS / "corpus_audit.py"
    assert sample.is_file(), f"{sample} missing — canonical ops script moved?"
    assert sample.resolve().parents[2] == _REPO_ROOT / "backend"


if __name__ == "__main__":  # runnable self-check
    test_ops_script_trees_do_not_share_filenames()
    test_backend_ops_scripts_resolve_backend_as_their_import_root()
    print("repo layout self-check OK")
