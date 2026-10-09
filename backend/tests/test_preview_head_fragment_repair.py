"""The head-fragment repair preview is pure and read-only."""

import hashlib
from pathlib import Path

from scripts.ops.preview_first_person_head_fragment_repair import preview_clip

_LONG = (
    "When you are in a beautiful state your mind becomes calm and clear and you "
    "see every situation with fresh eyes and so decisions come easily to you."
)


def test_clean_clip_is_not_previewed():
    assert preview_clip(_LONG) is None


def test_head_fragment_gets_a_shrink_proposal_with_matching_hash():
    r = preview_clip("Changes. " + _LONG)
    assert r is not None and r["repairable_by_shrink"]
    assert r["proposed_text"] == _LONG
    assert r["proposed_sha256"] == hashlib.sha256(_LONG.encode()).hexdigest()


def test_script_never_calls_a_qdrant_write():
    src = Path("scripts/ops/preview_first_person_head_fragment_repair.py").read_text()
    for call in ("upsert", "delete", "set_payload", "overwrite_payload", "update_vectors"):
        assert call not in src
