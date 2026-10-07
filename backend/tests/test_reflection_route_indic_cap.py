"""The post-reflection route must honour the per-request rewrite budget.

2026-09-26 retry benchmark: a Hindi question ran rewrite #1 and #2 (each with a
full regeneration) and hit the 180 s client timeout, because
_route_after_reflection read settings.rag_max_rewrites directly and ignored
the Indic cap in max_rewrites_for_state().
"""

from app.config import settings
from rag.graph_strategies import _route_after_reflection


def test_indic_request_stops_after_its_single_rewrite(monkeypatch):
    monkeypatch.setattr(settings, "rag_max_rewrites", 2)
    monkeypatch.setattr(settings, "rag_indic_max_rewrites", 1)
    state = {"needs_correction": True, "rewrite_count": 1, "detected_language": "hi"}
    assert _route_after_reflection(state) == "fallback"


def test_english_request_keeps_the_global_budget(monkeypatch):
    monkeypatch.setattr(settings, "rag_max_rewrites", 2)
    monkeypatch.setattr(settings, "rag_indic_max_rewrites", 1)
    state = {"needs_correction": True, "rewrite_count": 1, "detected_language": "en"}
    assert _route_after_reflection(state) != "fallback"
