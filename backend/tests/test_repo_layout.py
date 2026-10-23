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

_HERE = Path(__file__).resolve()
if _HERE.parents[1].name == "app" or _HERE.parents[1] == Path("/app"):
    _BACKEND = Path("/app")
    _REPO_ROOT = Path("/")
else:
    _REPO_ROOT = _HERE.parents[2]
    _BACKEND = _REPO_ROOT / "backend"

_ROOT_OPS = _REPO_ROOT / "scripts" / "ops"
_BACKEND_OPS = _BACKEND / "scripts" / "ops"


def _script_names(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {
        p.name for p in directory.iterdir() if p.is_file() and p.suffix in {".py", ".sh", ".cjs"}
    }


# Scripts present in both trees must be tracked and pinned byte-identical.
# In container, /scripts/ops resolves to /app/scripts/ops (same directory).
# On host, every shared script is tracked and verified byte-identical by
# test_allowed_duplicate_ops_scripts_are_identical below.
_ALLOWED_DUPLICATES: frozenset[str] = frozenset(
    (_script_names(_ROOT_OPS) & _script_names(_BACKEND_OPS))
    if _ROOT_OPS.resolve() != _BACKEND_OPS.resolve()
    else set()
)


def test_ops_script_trees_do_not_share_filenames():
    """One canonical home per ops script — no unowned shadow copies."""
    if _ROOT_OPS.resolve() == _BACKEND_OPS.resolve():
        return
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
    assert sample.resolve().parents[2] == _BACKEND


if __name__ == "__main__":  # runnable self-check
    test_ops_script_trees_do_not_share_filenames()
    test_backend_ops_scripts_resolve_backend_as_their_import_root()
    print("repo layout self-check OK")


def test_allowed_duplicate_ops_scripts_are_identical():
    """Allowed duplicates must stay byte-identical so they cannot drift."""
    for name in sorted(_ALLOWED_DUPLICATES):
        root_copy = _ROOT_OPS / name
        backend_copy = _BACKEND_OPS / name
        if not (root_copy.exists() and backend_copy.exists()):
            continue
        assert root_copy.read_bytes() == backend_copy.read_bytes(), f"{name} copies drifted"


# ---------------------------------------------------------------------------
# Cross-tree drift guard (added 2026-10-22)
#
# The ops/ pin above only covered scripts/ops/ vs backend/scripts/ops/. Three
# more paths were duplicated OUTSIDE ops/ and had already drifted apart, in
# both directions:
#
#   scripts/verify_rls_policies.py  <- stale copy, missing the
#       canonical_memories RLS probe. CI ran backend/scripts/... (correct) but
#       the container runs /app/scripts/... (the stale copy), so a
#       `docker exec` security check silently skipped the most sensitive
#       table in the schema.
#   scripts/warm_cache.py           <- stale copy, no concurrency cap and no
#       raised LLM timeouts.
#   scripts/migrate_data.py         <- stale copy, prune_backups() unguarded,
#       so a prune failure aborted the whole migration.
#
# Root cause: the container bind-mounts repo-root `scripts/` at /app/scripts,
# shadowing the image's baked `backend/scripts`, so the ROOT copy is what runs
# in-container while `backend/` is the host-canonical tree. Nothing propagated
# edits between them. These pairs are now reconciled (backend/ holds the
# content winner) and pinned byte-identical below so the drift cannot recur.
# ---------------------------------------------------------------------------

# Pairs that are intentionally DIFFERENT tools sharing a name, not drift.
# scripts/eval/run_ragas_eval.py is the standalone RAGAS runner over a live
# backend (covered by tests/test_ragas_claim_ledger.py);
# backend/scripts/eval/run_ragas_eval.py is the older golden-set harness.
_DIFFERENT_TOOLS: frozenset[str] = frozenset({"eval/run_ragas_eval.py"})


def _shared_script_paths() -> set[str]:
    """Relative paths present in both script trees."""
    root = _REPO_ROOT / "scripts"
    backend = _BACKEND / "scripts"
    if not root.is_dir() or not backend.is_dir():
        return set()
    if root.resolve() == backend.resolve():
        return set()
    root_files = {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p.suffix in {".py", ".sh", ".cjs", ".mjs"}
    }
    backend_files = {
        str(p.relative_to(backend))
        for p in backend.rglob("*")
        if p.is_file() and p.suffix in {".py", ".sh", ".cjs", ".mjs"}
    }
    return root_files & backend_files


def test_cross_tree_shared_scripts_are_identical():
    """Every script present in both trees must be byte-identical.

    The container executes the repo-root copy (bind mount shadows the image's
    baked backend/scripts), so a drifted root copy means the container runs
    different code than the host — silently. This has already bitten once:
    the in-container RLS verifier skipped the canonical_memories probe.
    """
    shared = _shared_script_paths() - _DIFFERENT_TOOLS
    drifted = []
    for rel in sorted(shared):
        root_copy = _REPO_ROOT / "scripts" / rel
        backend_copy = _BACKEND / "scripts" / rel
        if not (root_copy.exists() and backend_copy.exists()):
            continue
        if root_copy.read_bytes() != backend_copy.read_bytes():
            drifted.append(rel)
    assert not drifted, (
        f"scripts/ and backend/scripts/ copies drifted: {drifted}. "
        "The container runs the repo-root copy (bind mount shadows the image's "
        "baked backend/scripts), so a drifted pair means in-container and "
        "on-host behaviour differ silently. Reconcile the pair "
        "(backend/scripts/ holds the canonical content), then re-run."
    )


def test_different_tools_stay_distinct():
    """The one intentional same-name/different-content pair must stay distinct.

    If these two ever converge, one of them is a redundant copy that should
    be deleted instead of pinned.
    """
    for rel in _DIFFERENT_TOOLS:
        root_copy = _REPO_ROOT / "scripts" / rel
        backend_copy = _BACKEND / "scripts" / rel
        if not (root_copy.exists() and backend_copy.exists()):
            continue
        assert root_copy.read_bytes() != backend_copy.read_bytes(), (
            f"{rel} is now byte-identical in both trees — either delete the "
            "redundant copy or drop it from _DIFFERENT_TOOLS with a reason."
        )
