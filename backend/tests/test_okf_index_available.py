"""Regression guard: the OKF compiled index must reach the container.

``rag_okf_injection_enabled`` defaults to True and ``retrieval.py`` resolves the index
to ``/app/memory/okf/compiled.json`` inside the image. The index lives at the repo root
(``memory/okf/``), not under ``backend/``, so ``COPY backend/ .`` alone leaves it absent —
``_load_okf_entries()`` then caches ``[]`` and the canonical knowledge layer contributes
nothing to any answer, in production only.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

import rag.nodes.retrieval as retrieval

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILES = [
    _REPO_ROOT / "backend" / "Dockerfile",
    _REPO_ROOT / "backend" / "Dockerfile.railway",
]


@pytest.fixture(autouse=True)
def _reset_okf_cache():
    retrieval._OKF_CACHE = None
    yield
    retrieval._OKF_CACHE = None


@pytest.mark.parametrize("dockerfile", _DOCKERFILES, ids=lambda p: p.name)
def test_dockerfile_copies_okf_index(dockerfile: Path):
    """Each backend image must copy the repo-root memory/ tree into /app/memory."""
    assert dockerfile.exists(), f"{dockerfile} is missing"
    body = dockerfile.read_text(encoding="utf-8")
    assert re.search(
        r"^COPY\s+(?:--\S+\s+)*memory/\s+(?:\./memory/?|memory/?|/app/memory/?)\s*$",
        body,
        re.MULTILINE,
    ), (
        f"{dockerfile.name} does not copy memory/ — OKF injection is silently "
        "disabled in the built image"
    )


def test_okf_index_loads_from_repo_root():
    """The checked-in index resolves and parses."""
    assert retrieval._OKF_COMPILED_PATH.exists()
    assert len(retrieval._load_okf_entries()) > 0


def test_missing_index_warns_instead_of_failing_silently(tmp_path, monkeypatch, caplog):
    """A missing index must be loud — it strips the knowledge layer from every answer."""
    monkeypatch.setattr(retrieval, "_OKF_COMPILED_PATH", tmp_path / "absent.json")

    with caplog.at_level(logging.WARNING, logger=retrieval.logger.name):
        assert retrieval._load_okf_entries() == []

    assert any(
        "OKF compiled index missing" in r.message for r in caplog.records
    ), "missing OKF index was swallowed without a warning"
