"""Tests for OKF store and key teaching extraction boilerplate cleaning."""

from __future__ import annotations

import json

import pytest

from services.memory.okf_store import (
    OKF_DIR,
    _extract_key_teachings,
    clean_teaching_sentence,
)


@pytest.mark.unit
def test_clean_teaching_sentence_strips_leading_prefixes():
    """Verify that leading teacher / speaker attribution prefixes are stripped and capitalized."""
    cases = [
        (
            "Sri Preethaji says: peace is the foundation of genuine love and harmony.",
            "Peace is the foundation of genuine love and harmony.",
        ),
        (
            "Sri Krishnaji says: The truth of suffering is clear to the silent mind.",
            "The truth of suffering is clear to the silent mind.",
        ),
        (
            "The speaker encourages: Practice daily contemplation to discover stillness.",
            "Practice daily contemplation to discover stillness.",
        ),
        (
            "The speaker encourages the listener to observe inner conflict without judgment.",
            "Observe inner conflict without judgment.",
        ),
        (
            "The speaker emphasizes the importance of cultivating compassion in relationships.",
            "Cultivating compassion in relationships.",
        ),
        (
            "The speaker argues that the mind's tendency to suffer is a fundamental aspect of human existence.",
            "The mind's tendency to suffer is a fundamental aspect of human existence.",
        ),
        (
            'Sri Preethaji says:** "An unagitated consciousness is the seat of abundance and fortune."',
            "An unagitated consciousness is the seat of abundance and fortune.",
        ),
        (
            "Sri Preethaji and Sri Krishnaji teach to connect deeply with nature every day.",
            "Connect deeply with nature every day.",
        ),
        (
            "Teaching Point 1**: Changing the fuel for aspiration involves focusing on what one loves.",
            "Changing the fuel for aspiration involves focusing on what one loves.",
        ),
    ]
    for raw, expected in cases:
        result = clean_teaching_sentence(raw)
        assert result == expected, f"Failed for {raw!r}: expected {expected!r}, got {result!r}"


@pytest.mark.unit
def test_clean_teaching_sentence_strips_trailing_parentheticals_and_attributions():
    """Verify trailing parenthetical attributions and dash signatures are stripped."""
    cases = [
        (
            "The universe is cyclical (Sri Preethaji says).",
            "The universe is cyclical.",
        ),
        (
            "Prolonged depression causes isolation and alienation from others. (Unknown speaker)",
            "Prolonged depression causes isolation and alienation from others.",
        ),
        (
            "Suffering arises from holding onto judgments and labels. (Unknown Channel)",
            "Suffering arises from holding onto judgments and labels.",
        ),
        (
            "Every human experience is sacred (Sri Preethaji & Sri Krishnaji).",
            "Every human experience is sacred.",
        ),
        (
            "Enlightenment is the liberation from fear — Sri Preethaji",
            "Enlightenment is the liberation from fear.",
        ),
        (
            "Inner stillness leads to immense clarity and creative breakthroughs. — Unknown Channel",
            "Inner stillness leads to immense clarity and creative breakthroughs.",
        ),
        (
            "Mother Earth is described as a good soul to fall in love with (Unknown Channel).",
            "Mother Earth is described as a good soul to fall in love with.",
        ),
    ]
    for raw, expected in cases:
        result = clean_teaching_sentence(raw)
        assert result == expected, f"Failed for {raw!r}: expected {expected!r}, got {result!r}"


@pytest.mark.unit
def test_clean_teaching_sentence_drops_malformed_and_truncated():
    """Verify malformed quote fragments, cut-off sentences, and short lines are dropped."""
    bad_cases = [
        'Abundance has been a way of life for the teachers, and the key to it "has not',
        'To truly know the speaker\'s nature, a secret is offered: "I am e".',
        "% of these thoughts are negative. (Sri Preethaji)",
        '"You move away from oneness when you begin to see the other as" — Sri Preethaji',
        "Short text.",
        "The practice is the fourth phase of the Soul Sync meditation, following the",
        "Soul Sync was created with the sacred intention of awakening people to the",
        'Sri Preethaji says to ask a divine feminine energy to "dissolve the traces of anger and greed from your consciousness and fill you w[ith positive qualities]."',
    ]
    for bad in bad_cases:
        result = clean_teaching_sentence(bad)
        assert result is None, f"Expected {bad!r} to be dropped, but got {result!r}"


@pytest.mark.unit
def test_clean_teaching_sentence_enforces_length_and_capitalization():
    """Verify sentences < 20 chars are dropped and lower-case beginnings are capitalized."""
    assert clean_teaching_sentence("Too short.") is None
    res = clean_teaching_sentence("sri preethaji says: love is the true nature of consciousness.")
    assert res == "Love is the true nature of consciousness."
    assert len(res) >= 20


@pytest.mark.unit
def test_extract_key_teachings_from_entry_dict():
    """Verify _extract_key_teachings extracts and cleans from both body and key_teachings list."""
    entry_with_body = {
        "title": "Gratitude Teaching",
        "body": (
            "## Summary\nPracticing gratitude is transformative.\n\n"
            "## Key Teachings\n"
            "- Sri Preethaji says: Gratitude transforms fear into deep peace.\n"
            "- Depression causes isolation and alienation from others. (Unknown speaker)\n"
            "- Short.\n"
            '- Incomplete quote "cuts off right\n'
        ),
    }
    extracted = _extract_key_teachings(entry_with_body)
    assert len(extracted) == 2
    assert extracted[0] == "Gratitude transforms fear into deep peace."
    assert extracted[1] == "Depression causes isolation and alienation from others."

    entry_with_list = {
        "title": "Direct List",
        "key_teachings": [
            "Sri Krishnaji says: The truth of suffering dissolves when observed clearly.",
            "Short.",
            "Awakened consciousness alters your state of being (Sri Preethaji says).",
        ],
    }
    extracted_list = _extract_key_teachings(entry_with_list)
    assert len(extracted_list) == 2
    assert extracted_list[0] == "The truth of suffering dissolves when observed clearly."
    assert extracted_list[1] == "Awakened consciousness alters your state of being."


@pytest.mark.unit
def test_compiled_json_key_teachings_integrity():
    """Every compiled.json entry satisfies the OKF integrity contract.

    Count-INDEPENDENT by design (2026-09-29 audit, Section C): the old
    `== 715` assertion flaked when the deterministic single-video TEDx ingest
    legitimately grew the bundle to 717. Corruption is now checked against the
    entry schema — provenance, embedding dimension, teaching shape — so bundle
    growth/shrinkage can never flake this test while real corruption still
    fails it. The number below is only a truncation guard against a partial
    write; the authoritative bundle cross-check (compiled count == on-disk
    ``memory/okf/*.md`` count) lives in ``test_okf_doctrine_only``.
    """
    compiled_file = OKF_DIR / "compiled.json"
    if not compiled_file.exists():
        pytest.skip("compiled.json not found")

    with open(compiled_file, encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    # Truncation guard (not an exact-count invariant): bundle was 717 on 2026-09-29.
    assert len(entries) >= 715, f"compiled.json looks truncated: found {len(entries)} entries"

    # Schema-derived invariants — independent of how many entries exist.
    paths = [e.get("path") for e in entries]
    assert all(paths), "entry without a provenance `path`"
    assert len(set(paths)) == len(paths), "duplicate `path` values in compiled.json"

    for e in entries:
        title = e.get("title")
        assert title and str(title).strip(), f"entry with empty title: {e.get('path')}"
        source = str(e.get("source") or "")
        assert source.startswith(("http://", "https://")), (
            f"{title}: entry without citable HTTP(S) source: {source!r}"
        )
        assert len(e.get("embedding") or []) == 1024, (
            f"{title}: embedding must stay on the BGE-M3 1024-d contract"
        )
        assert "key_teachings" in e, f"Entry {title} missing 'key_teachings' field"
        kts = e["key_teachings"]
        assert isinstance(kts, list), f"Entry {title} key_teachings must be a list"
        for t in kts:
            assert len(t) >= 20, f"Teaching too short ({len(t)} chars): {t!r}"
            assert t.strip() == t and "\n" not in t, f"Teaching not single-line/trimmed: {t!r}"
            # `## Summary` / markdown headers leaking into a teaching are the
            # "summary presented as a quote" defect class this contract forbids.
            assert "##" not in t, f"Markdown header inside teaching: {t!r}"
            # Verify no leading boilerplate prefixes
            assert not t.startswith("Sri Preethaji says:"), f"Boilerplate remaining: {t!r}"
            assert not t.startswith("Sri Krishnaji says:"), f"Boilerplate remaining: {t!r}"
            assert not t.startswith("The speaker encourages:"), f"Boilerplate remaining: {t!r}"
            # Verify no trailing parenthetical speaker attributions
            assert not t.endswith("(Unknown speaker)"), f"Trailing attribution remaining: {t!r}"
            assert not t.endswith("(Sri Preethaji says)"), f"Trailing attribution remaining: {t!r}"
            assert not t.endswith("(Unknown Channel)"), f"Trailing attribution remaining: {t!r}"


@pytest.mark.unit
def test_match_verbatim_clusters_accuracy_and_schema():
    """Verify that match_verbatim_clusters returns canonical clusters with required schema."""
    from services.memory.okf_store import OKFStore, match_verbatim_clusters

    clusters_path = OKF_DIR / "verbatim_clusters.json"
    if not clusters_path.exists():
        pytest.skip("verbatim_clusters.json not found")

    with open(clusters_path, encoding="utf-8") as f:
        data = json.load(f)

    sample_cluster = data["clusters"][0]
    query_vec = sample_cluster["embedding"]
    assert len(query_vec) == 1024

    results = match_verbatim_clusters(query_vec, top_k=2)
    assert len(results) >= 1
    top = results[0]

    # Required schema checks
    assert top["cluster_id"] == sample_cluster["cluster_id"]
    assert top["score"] == pytest.approx(1.0, abs=1e-3)
    assert isinstance(top["clip_ids"], list)
    assert top["clip_count"] > 0
    assert isinstance(top["key_verbatim_quotes"], list)
    assert len(top["key_verbatim_quotes"]) > 0
    assert isinstance(top["reflection_questions"], list)
    assert len(top["reflection_questions"]) > 0

    # OKFStore delegation check
    store = OKFStore()
    store_results = store.match_verbatim_clusters(query_vec, top_k=2)
    assert len(store_results) == len(results)
    assert store_results[0]["cluster_id"] == top["cluster_id"]


@pytest.mark.unit
def test_match_verbatim_clusters_speed_under_1ms():
    """Sub-millisecond cosine matching over canonical verbatim clusters."""
    import time

    from services.memory.okf_store import match_verbatim_clusters

    clusters_path = OKF_DIR / "verbatim_clusters.json"
    if not clusters_path.exists():
        pytest.skip("verbatim_clusters.json not found")

    with open(clusters_path, encoding="utf-8") as f:
        data = json.load(f)

    query_vec = data["clusters"][0]["embedding"]
    # Warmup
    match_verbatim_clusters(query_vec, top_k=2)

    latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        match_verbatim_clusters(query_vec, top_k=2)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

    avg_ms = sum(latencies) / len(latencies)
    assert avg_ms < 1.0, f"Average latency too high: {avg_ms:.3f}ms"


@pytest.mark.unit
def test_match_verbatim_clusters_edge_cases(tmp_path):
    """Graceful handling of empty or wrong-dim vectors and missing files."""
    from services.memory.okf_store import match_verbatim_clusters

    assert match_verbatim_clusters([]) == []
    assert match_verbatim_clusters([0.1] * 512) == []
    assert match_verbatim_clusters([0.0] * 1024) == []
    assert match_verbatim_clusters([0.1] * 1024, clusters_path=tmp_path / "missing.json") == []
