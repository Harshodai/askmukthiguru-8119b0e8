"""Regression guards for the OKF write path.

Three modules resolve the OKF directory. They must agree — and agree inside the
image too, where ``backend/`` IS ``/app`` and the old hand-rolled ``parents[3]`` /
``_BACKEND.parent`` forms silently produced ``/memory/okf``.

Separately: ``extract_okf(auto_approve=False)`` stages LLM-generated entries for
review. A recursive glob swept ``staging/`` straight into ``compiled.json``, so the
review gate never held and unreviewed doctrine reached the answer path.
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


def test_staged_entries_never_enter_the_compiled_index():
    """auto_approve=False writes to staging/ — compile must not pick it up."""
    before = len(OKFStore().list_entries())

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    probe = STAGING_DIR / "_pytest_unreviewed_probe.md"
    probe.write_text(
        '---\ntype: teaching\ntitle: "Unreviewed Probe"\n---\n\nnot yet approved\n',
        encoding="utf-8",
    )
    try:
        after = len(OKFStore().list_entries())
        assert after == before, (
            "staged, unreviewed OKF entries leaked into the compiled index — "
            "the review gate is a no-op"
        )
    finally:
        probe.unlink(missing_ok=True)
        try:
            STAGING_DIR.rmdir()
        except OSError:
            pass  # not empty — real staged entries present, leave them


@pytest.mark.parametrize(
    "provider", ["MultiProviderLLMService", "OpenRouterService", "OllamaService"]
)
def test_extractor_llm_chain_has_all_fallbacks(provider: str):
    """This is the copy ingestion/Celery/admin import; it must fall back to Ollama."""
    assert provider in inspect.getsource(extractor._call_llm), (
        f"{provider} missing from _call_llm — OKF extraction raises under LLM_PROVIDER=ollama"
    )


def test_only_one_extractor_copy_exists():
    """The repo-root duplicate drifted (lost the Ollama fallback) and had no importers."""
    repo_root = OKF_DIR.parent
    assert not (repo_root / "scripts" / "extract_okf_from_stores.py").exists(), (
        "root duplicate is back — it has no importers and silently diverges from "
        "backend/scripts/extract_okf_from_stores.py"
    )
