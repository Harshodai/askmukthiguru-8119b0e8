"""Ritual teaching-pool curation gate (backend/app/api/ritual.py).

Audit 2026-10-04: the Love cluster holds 2 covid-lockdown + 3 promo quotes and
a covid joke ("let me have corona...") was served LIVE as Today's Teaching.
These tests pin the denylist gate: denylisted quotes are never served, the
date-seeded determinism is preserved, and an emptied pool falls back to the
honestly-labelled practice-prompt pool instead of serving nothing.
"""

from __future__ import annotations

from datetime import date, timedelta

import app.api.ritual as ritual


def _denied_texts() -> set[str]:
    return {text for text, _ in ritual._CURATED_DENYLIST}


def test_denylist_covers_covid_joke_and_promo_quotes():
    """The exact quotes from the audit are curated out, each with a reason."""
    denied = _denied_texts()
    assert any("let me have corona" in text for text in denied)
    assert any("coronavirus itself" in text for text in denied)
    assert any("youth leadership festival" in text for text in denied)
    assert all(reason for _, reason in ritual._CURATED_DENYLIST)


def test_denylisted_quotes_never_served_across_60_day_sweep():
    """No date in a 60-day window may serve a denylisted quote."""
    denied = _denied_texts()
    assert denied  # the gate itself must be non-empty
    ritual._teaching_pool.cache_clear()
    try:
        pool = ritual._teaching_pool()
        assert len(pool) >= 5
        pool_texts = {item["text"].lower() for item in pool}
        assert not (pool_texts & denied)
        start = date(2026, 1, 1)
        served = {
            ritual._teaching_for((start + timedelta(days=i)).isoformat())["text"] for i in range(60)
        }
        assert served <= {item["text"] for item in pool}
        assert not ({text.lower() for text in served} & denied)
        assert "corona" not in " ".join(served).lower()
    finally:
        ritual._teaching_pool.cache_clear()


def test_determinism_preserved_after_curation():
    """Same UTC date → same teaching, every call."""
    assert ritual._teaching_for("2026-10-04") == ritual._teaching_for("2026-10-04")
    assert ritual._teaching_for("2026-10-04")["kind"] == "verbatim_quote"


def test_pool_emptied_by_denylist_falls_back_to_practice_prompts(monkeypatch):
    """If curation would empty the pool, serve practice prompts — never nothing."""
    monkeypatch.setattr(ritual, "_is_denylisted", lambda fingerprint: True)
    ritual._teaching_pool.cache_clear()
    try:
        pool = ritual._teaching_pool()
        assert pool == ritual._FALLBACK_PROMPTS
        teaching = ritual._teaching_for("2026-10-04")
        assert teaching["kind"] == "practice_prompt"
        assert teaching["attribution"] == "AskMukthiGuru practice guide"
    finally:
        ritual._teaching_pool.cache_clear()
