"""Regression guards for the OKF write path.

Three modules resolve the OKF directory. They must agree — and agree inside the
image too, where ``backend/`` IS ``/app`` and the old hand-rolled ``parents[3]`` /
``_BACKEND.parent`` forms silently produced ``/memory/okf``.

Separately: ``extract_okf(auto_approve=False)`` stages LLM-generated entries for
review. ``list_entries()`` uses ``rglob`` — the teacher-subdir layout
(``sri-preethaji/``, ``sri-krishnaji/``, ``shared/``) REQUIRES recursion — and keeps
``staging/`` and ``_scripts/`` out with an explicit ``_excluded_parts`` filter, NOT
glob depth. Both halves are load-bearing and guarded below: the filter must exclude
unreviewed dirs at any depth, and rglob must keep recursing into real teacher subdirs
(a revert to a non-recursive glob would silently drop every teaching from the index).
"""

from __future__ import annotations

import inspect

import pytest

import scripts.extract_okf_from_stores as extractor
from services.memory import compiler
from services.memory.okf_store import OKF_DIR, STAGING_DIR, OKFStore


def test_all_three_modules_resolve_the_same_okf_dir():
    assert OKF_DIR == compiler._OKF_DIR == extractor._OKF_DIR
    assert extractor._STAGING_DIR == STAGING_DIR
    assert STAGING_DIR.parent == OKF_DIR


def test_live_index_is_non_empty():
    assert OKF_DIR.exists(), f"OKF dir missing: {OKF_DIR}"
    assert len(OKFStore().list_entries()) > 0


def _doctrine_probe_text(title: str) -> str:
    """A fully valid teaching: ``type`` in DOCTRINE_TYPES, non-empty ``source``
    (provenance invariant), clean body (passes OKFQualityFilter). It is therefore
    indexed wherever it is allowed — which is exactly what lets the exclusion tests
    prove the *filter* (not some other invariant) is what keeps it out."""
    return (
        f'---\ntype: teaching\ntitle: "{title}"\nsource: "pytest probe"\n---\n\n'
        "A valid teaching body used only by the test suite. It is deliberately long "
        "enough to clear the OKFQualityFilter minimum body length, so these probes "
        "exercise the directory filter and glob recursion — not the length guard.\n"
    )


def _cleanup(probe, *created_dirs):
    probe.unlink(missing_ok=True)
    for d in created_dirs:  # innermost-first; only removes dirs left empty
        try:
            d.rmdir()
        except OSError:
            pass


def test_subdir_teachings_are_included():
    """rglob MUST recurse into teacher subdirs. A regression to a non-recursive
    ``glob`` (the old, wrong 'fix' for staging leakage) silently drops every
    ``sri-preethaji/`` / ``sri-krishnaji/`` / ``shared/`` teaching from the index."""
    before = len(OKFStore().list_entries())
    subdir = OKF_DIR / "sri-preethaji"
    created = not subdir.exists()
    subdir.mkdir(parents=True, exist_ok=True)
    probe = subdir / "_pytest_subdir_probe.md"
    probe.write_text(_doctrine_probe_text("Subdir Recursion Probe"), encoding="utf-8")
    try:
        after = len(OKFStore().list_entries())
        assert after == before + 1, (
            "a valid teaching in a teacher subdir was NOT indexed — list_entries() "
            "stopped recursing (non-recursive glob regression)"
        )
    finally:
        _cleanup(probe, *( (subdir,) if created else () ))


@pytest.mark.parametrize("excluded_dir", ["staging", "_scripts", "staging/nested"])
def test_excluded_dirs_never_enter_the_compiled_index(excluded_dir: str):
    """The review gate now rests on the ``_excluded_parts`` filter (rglob + filter),
    NOT on glob depth. A doctrine-valid file under staging/ or _scripts/ — at any
    depth — must stay out of the compiled index, or unreviewed doctrine reaches the
    answer path."""
    before = len(OKFStore().list_entries())
    leaf = OKF_DIR / excluded_dir
    leaf.mkdir(parents=True, exist_ok=True)
    probe = leaf / "_pytest_excluded_probe.md"
    probe.write_text(_doctrine_probe_text("Excluded Probe"), encoding="utf-8")
    try:
        after = len(OKFStore().list_entries())
        assert after == before, (
            f"a doctrine-valid file under {excluded_dir}/ leaked into the index — "
            "the _excluded_parts review gate is broken"
        )
    finally:
        # remove nested leaf first, then STAGING_DIR only if we left it empty
        _cleanup(probe, leaf, STAGING_DIR)


@pytest.mark.parametrize(
    "provider", ["MultiProviderLLMService", "OpenRouterService", "OllamaService"]
)
def test_extractor_llm_chain_has_all_fallbacks(provider: str):
    """This is the copy ingestion/Celery/admin import; it must fall back to Ollama."""
    assert provider in inspect.getsource(extractor._call_llm), (
        f"{provider} missing from _call_llm — OKF extraction raises under LLM_PROVIDER=ollama"
    )


def test_extractor_copies_are_identical():
    """Both extractor copies must exist and be identical to prevent runtime drift."""
    repo_root = OKF_DIR.parent.parent
    root_path = repo_root / "scripts" / "extract_okf_from_stores.py"
    backend_path = repo_root / "backend" / "scripts" / "extract_okf_from_stores.py"
    
    assert root_path.exists(), "root scripts/extract_okf_from_stores.py is missing"
    assert backend_path.exists(), "backend/scripts/extract_okf_from_stores.py is missing"
    
    assert root_path.read_text(encoding="utf-8") == backend_path.read_text(encoding="utf-8"), (
        "scripts/extract_okf_from_stores.py and backend/scripts/extract_okf_from_stores.py "
        "have diverged — make them identical"
    )
