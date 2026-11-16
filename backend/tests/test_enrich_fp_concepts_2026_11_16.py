"""U7 concept enrichment: pure-function checks (no Qdrant, Memgraph or model)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "enrich_fp_concepts", Path(__file__).resolve().parents[1] / "scripts/ops/enrich_fp_concepts.py"
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

TEXT = "Living in a Beautiful State, your karma and Karmic patterns settle."


def test_matching_is_whole_word_casefolded_and_exact_case_output():
    m = mod.Matcher({"Beautiful State": [], "Karma": ["karmic clearing"], "ego": []})
    assert m.match(TEXT) == {"Beautiful State", "Karma"}
    assert m.match("karmas, egos") == set()
    assert mod.Matcher({"ab": []}).match("ab ab") == set()  # surfaces under 3 chars ignored


def test_graph_vocab_drops_people_and_stop_terms():
    g = {
        "neighbors": {
            "Karma": [
                {"entity_id": "Dharma", "labels": ["base", "Concept"]},
                {"entity_id": "Sri Krishnaji", "labels": ["base", "Teacher"]},
                {"entity_id": "Teaching", "labels": ["base"]},
                {"entity_id": None, "labels": ["Concept"]},
            ]
        }
    }
    assert mod.graph_entity_vocab(g) == {"Dharma"}


def test_patch_touches_only_allowed_keys_and_never_text_hash_or_id():
    payload = {
        "verbatim_text": TEXT,
        "source_text_hash": "h",
        "transcript_hash": "t",
        "source_span_id": "s1",
        "video_id": "abcdefghijk",
    }
    before = dict(payload)
    patch = mod.propose_patch(
        payload,
        mod.Matcher({"Karma": []}),
        mod.Matcher({"karmic": []}),
        {"abcdefghijk": {"Title"}},
        {"s1": ["peace"]},
    )
    assert set(patch) <= set(mod.ALLOWED_KEYS)
    assert not {"verbatim_text", "source_text_hash", "transcript_hash", "id"} & set(patch)
    assert payload == before  # input payload not mutated
    assert patch["entity_ids"] == ["Karma"] and patch["topic_ids"] == ["karmic", "peace"]
    with pytest.raises(ValueError):
        mod.assert_patch_safe({"verbatim_text": "x"})


def test_share_cap_drops_over_represented_concepts():
    patches = {str(i): {"topic_ids": ["common", f"u{i}"]} for i in range(8)}
    dropped = mod.apply_share_cap(patches, 8, 0.25)
    assert dropped == {"common": 8}
    assert all(v == {"topic_ids": [f"u{k}"]} for k, v in patches.items())


class _Client:
    def __init__(self):
        self.calls = []

    def set_payload(self, **kw):
        self.calls.append(kw)


def _apply(client, **over):
    args = dict(keys=mod.ALLOWED_KEYS, snapshot_confirmed=True, approved_by="owner")
    args.update(over)
    return mod.apply_patches(client, "c", {"p1": {"topic_ids": ["x"]}}, {"p1": {}}, **args)


def test_apply_refuses_without_snapshot_or_approver_or_bad_keys():
    c = _Client()
    with pytest.raises(PermissionError):
        _apply(c, snapshot_confirmed=False)
    with pytest.raises(PermissionError):
        _apply(c, approved_by="  ")
    with pytest.raises(ValueError):
        _apply(c, keys=("verbatim_text",))
    assert c.calls == []


def test_apply_is_additive_only_and_writes_listed_keys():
    c = _Client()
    with pytest.raises(ValueError):
        mod.apply_patches(
            c, "c", {"p1": {"topic_ids": ["x"]}}, {"p1": {"topic_ids": ["old"]}},
            keys=("topic_ids",), snapshot_confirmed=True, approved_by="owner",
        )
    assert _apply(c, keys=("topic_ids",)) == 1
    assert c.calls == [{"collection_name": "c", "payload": {"topic_ids": ["x"]}, "points": ["p1"], "wait": True}]
