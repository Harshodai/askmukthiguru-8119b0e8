"""The OKF bundle carries the gurus' teachings and nothing else.

Every entry here is embedded and injected verbatim into answers by
``rag/nodes/retrieval.py:_okf_match``, so whatever sits in this directory is quoted to
a seeker *as doctrine*. Three classes of contamination were found live and are locked
out below:

1. Engineering notes (RAG tuning, config postmortems) → moved to ``docs/engineering-notes/``.
2. Entries with no ``source`` → uncitable, so unattributable in a generated answer.
3. Extraction artifacts — RAPTOR debug headers, ``_(Source: unknown)_``, and the
   extraction LLM's own prompt commentary ("The user wants me to analyze a spiritual
   teaching and list the top 3-5 distinct topics"). ``generation.py`` rule 6 forbids
   exposing exactly that text, yet the knowledge layer contained it.

Bundle format: Google Cloud's Open Knowledge Format v0.1.
https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
"""

from __future__ import annotations

import json
import re

import pytest
import yaml

from services.memory.okf_store import (
    DOCTRINE_TYPES,
    OKF_DIR,
    RESERVED_FILENAMES,
    OKFStore,
)

_ARTIFACT_RE = re.compile(
    r"RAPTOR Level\s*:|_\(Source:\s*unknown\)_|The user (?:wants me to|has provided)"
    r"|Interpret the Input|Let me analyze|We are given|comma-separated list",
    re.IGNORECASE,
)

_CONCEPT_FILES = sorted(p for p in OKF_DIR.glob("*.md") if p.name not in RESERVED_FILENAMES)


def test_bundle_is_not_empty():
    assert _CONCEPT_FILES, f"no OKF concept documents in {OKF_DIR}"


@pytest.mark.parametrize("path", _CONCEPT_FILES, ids=lambda p: p.name)
def test_okf_v0_1_conformance(path):
    """OKF v0.1: every non-reserved .md parses as frontmatter with a non-empty `type`."""
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("---"), f"{path.name}: no YAML frontmatter"
    meta = yaml.safe_load(raw.split("---", 2)[1])
    assert isinstance(meta, dict), f"{path.name}: frontmatter is not a mapping"
    assert str(meta.get("type", "")).strip(), f"{path.name}: empty required field `type`"


@pytest.mark.parametrize("path", _CONCEPT_FILES, ids=lambda p: p.name)
def test_entry_is_doctrine(path):
    """Producer-defined type vocabulary — nothing outside it reaches the answer path."""
    meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
    assert str(meta["type"]).strip().lower() in DOCTRINE_TYPES, (
        f"{path.name}: type={meta['type']!r} is not a doctrine type {sorted(DOCTRINE_TYPES)}"
    )


@pytest.mark.parametrize("path", _CONCEPT_FILES, ids=lambda p: p.name)
def test_entry_is_citable(path):
    """No source → the answer cannot attribute the claim to the gurus."""
    meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
    assert str(meta.get("source", "") or "").strip(), f"{path.name}: missing `source`"


@pytest.mark.parametrize("path", _CONCEPT_FILES, ids=lambda p: p.name)
def test_entry_is_free_of_extraction_artifacts(path):
    body = path.read_text(encoding="utf-8").split("---", 2)[2]
    hit = _ARTIFACT_RE.search(body)
    assert not hit, f"{path.name}: extraction artifact in doctrine body: {hit.group(0)!r}"


def test_store_rejects_contaminated_entries(tmp_path):
    """The load-time gate, not just the on-disk state, keeps the bundle clean."""
    tmp_path.joinpath("good.md").write_text(
        "---\ntype: teaching\ntitle: T\nsource: youtube\n---\n\n"
        + ("Sri Preethaji teaches. " * 10),
        encoding="utf-8",
    )
    tmp_path.joinpath("runbook.md").write_text(
        "---\ntype: runbook\ntitle: Deploy\nsource: wiki\n---\n\n" + ("step " * 40),
        encoding="utf-8",
    )
    tmp_path.joinpath("nosource.md").write_text(
        "---\ntype: teaching\ntitle: X\n---\n\n" + ("body " * 40), encoding="utf-8"
    )
    tmp_path.joinpath("leaked.md").write_text(
        "---\ntype: teaching\ntitle: Y\nsource: qdrant\n---\n\n"
        "The user wants me to analyze a spiritual teaching. " + ("pad " * 30),
        encoding="utf-8",
    )
    titles = {e.title for e in OKFStore(directory=tmp_path).list_entries()}
    assert titles == {"T"}, f"gate let contaminated entries through: {titles}"


def test_compiled_index_matches_the_clean_bundle():
    compiled = json.loads((OKF_DIR / "compiled.json").read_text(encoding="utf-8"))
    entries = compiled.get("entries", [])
    assert len(entries) == len(OKFStore().list_entries()), (
        "compiled.json is stale — rerun compile_okf()"
    )
    for e in entries:
        assert e["type"] in DOCTRINE_TYPES
        assert e["source"], f"{e['title']}: compiled without provenance"
        assert e.get("description"), f"{e['title']}: compiled without OKF description"
        assert not _ARTIFACT_RE.search(e["body"]), f"{e['title']}: artifact in compiled body"
