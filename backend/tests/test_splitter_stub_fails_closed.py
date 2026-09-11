"""The repo-root text-splitter stub must never chunk a real corpus.

`langchain_text_splitters/` at the REPO ROOT is a test stub. Because the repo
root precedes site-packages on sys.path for any process started there, it
shadows the real library for:

  * `python3 -m pytest backend/tests/` — the command root CLAUDE.md documents
  * scripts/ingestion/ingest_four_sacred_secrets.py:21
  * scripts/ingestion/bulk_ingest_whisper.py:245
  * scripts/ingestion/bulk_ingest_async.py:381
  * backend/ingest/{pipeline,adaptive_chunking,video_pipeline}.py

A corpus ingested from the repo root was split by the stub; one ingested from
backend/ used the real library. Nothing in the Qdrant payload distinguishes
them. The stub previously emitted a RuntimeWarning and carried on, so the
divergent chunks were written anyway.

It now raises ImportError outside pytest. This pins that, and pins that the
guard keys on pytest rather than on something a production run could satisfy.
"""

from __future__ import annotations

import pathlib

import pytest

STUB = pathlib.Path(__file__).resolve().parents[2] / "langchain_text_splitters" / "__init__.py"


@pytest.fixture(scope="module")
def stub_source() -> str:
    if not STUB.exists():
        pytest.skip("root stub removed — the shadowing hazard is gone entirely")
    return STUB.read_text(encoding="utf-8")


def test_stub_raises_outside_pytest_rather_than_warning(stub_source: str):
    assert "raise ImportError(" in stub_source, (
        "the stub must fail closed outside pytest — a warning lets a production "
        "ingest proceed and write differently-chunked vectors"
    )
    assert (
        "warnings.warn(" not in stub_source
    ), "a warning here is not a guard; it was the original defect"


def test_guard_keys_on_pytest(stub_source: str):
    """The escape hatch must be pytest itself, not an env var a script could set."""
    assert 'os.environ.get("PYTEST_CURRENT_TEST")' in stub_source


def test_real_package_is_what_backend_resolves():
    """Running from backend/, the import must reach site-packages, not the stub."""
    import langchain_text_splitters as mod

    resolved = pathlib.Path(mod.__file__).resolve()
    assert "site-packages" in str(resolved), (
        f"backend/ resolved the splitter to {resolved} — expected the real "
        "installed package, not the repo-root stub"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
