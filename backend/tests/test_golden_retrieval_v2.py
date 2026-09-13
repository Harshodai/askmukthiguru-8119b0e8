"""Freeze the v2 golden retrieval labels (Task 9, D1/D2).

v2 corrects 5 stale labels evidenced in L-DOCKER-19 and verified live on
2026-09-13 against spiritual_wisdom_contextual (70 points under the canonical
Amazon URL, 0 under the bare PDF filename), adds 20 human-authored seeker
paraphrases with qrels inherited verbatim from their parents, and excludes 2
term-match false positives. Any future label change must update this file.
"""

import json
from pathlib import Path

from benchmarks.retrieval_metrics import normalize_source_key

GOLDEN = Path(__file__).resolve().parents[1] / "evaluation" / "datasets" / "golden_retrieval_v1.json"
AMZ = "https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"
BARE = "The_Four_Sacred_Secrets.pdf"


def _load():
    return json.loads(GOLDEN.read_text())


def test_golden_version_is_frozen_v2():
    golden = _load()
    assert golden["version"] == "v2"
    assert len(golden["items"]) == 88
    scored = [it for it in golden["items"] if not it.get("excluded")]
    assert len(scored) == 86


def test_three_key_mismatch_labels_use_canonical_url():
    by_id = {it["id"]: it for it in _load()["items"]}
    for qid in ("doctrine_four_secrets-000", "doctrine_founders-021", "doctrine_founders-026"):
        item = by_id[qid]
        assert item["correct_sources"] == [AMZ], qid
        assert item["previous_correct_sources"] == [BARE], qid
        assert "L-DOCKER-19" in item["relabel_reason"], qid


def test_four_secrets_count_matches_live_doc_size():
    by_id = {it["id"]: it for it in _load()["items"]}
    item = by_id["doctrine_four_secrets-000"]
    assert item["correct_chunks"] == 70
    assert item["previous_correct_chunks"] == 384


def test_two_content_stale_labels_are_excluded_with_reasons():
    by_id = {it["id"]: it for it in _load()["items"]}
    for qid in ("doctrine_manifest-042", "doctrine_deeksha-060"):
        item = by_id[qid]
        assert item["excluded"] is True, qid
        assert item["exclude_reason"], qid


def test_twenty_human_paraphrases_have_valid_parents_and_qrels():
    golden = _load()
    by_id = {it["id"]: it for it in golden["items"]}
    derived = [it for it in golden["items"] if it.get("derived_from")]
    assert len(derived) == 20
    for item in derived:
        parent = by_id[item["derived_from"]]
        assert not parent.get("excluded")
        assert item["correct_sources"] == parent["correct_sources"]
        assert item["must_mention"] == parent["must_mention"]
        assert item["correct_sources"] != [BARE]


def test_canonical_key_normalization():
    assert normalize_source_key(BARE) == AMZ
    assert normalize_source_key(AMZ + "#reviews") == AMZ
    assert normalize_source_key("https://WWW.YOUTUBE.COM/watch?v=x") == "https://www.youtube.com/watch?v=x"
    assert normalize_source_key("gold") == "gold"
