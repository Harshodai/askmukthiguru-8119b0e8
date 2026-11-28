"""Enrichment-window scrolls run side by side, not N x timeout (latency fix 2026-11-28)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import Mock

from app.config import settings
from services.first_person_pipeline import FirstPersonPipeline

DELAY_S = 0.2
N = 6


class _SlowStore:
    def enrich_to_parent_window(self, ctx):
        time.sleep(DELAY_S)  # stands in for one blocking Qdrant scroll
        return SimpleNamespace(parent=ctx.parent, spans=ctx.spans + ("wide",))


def test_enrichment_widen_is_concurrent_and_ordered(monkeypatch) -> None:
    monkeypatch.setattr(settings, "first_person_enrichment_window_enabled", True, raising=False)
    monkeypatch.setattr(settings, "first_person_enrichment_window_timeout_s", 1.5, raising=False)
    for flag in (
        "first_person_graph_expansion_enabled",
        "first_person_okf_expansion_enabled",
        "first_person_teaching_unit_graph_enabled",
    ):
        monkeypatch.setattr(settings, flag, False, raising=False)
    ctxs = [
        SimpleNamespace(parent=SimpleNamespace(parent_unit_id=f"p{i}"), spans=(f"s{i}",))
        for i in range(N)
    ]
    pipe = FirstPersonPipeline(store=Mock(), serene_mind_engine=Mock(), llm_service=Mock())
    t0 = time.monotonic()
    out = pipe._expand_context_candidates(
        ctxs,
        ctx_store=_SlowStore(),
        query_dense_vector=[0.0],
        query_sparse_vector=None,
        retrieval_query="q",
        teacher_id="t",
        max_clips=N,
        max_spans=4,
    )
    wall = time.monotonic() - t0
    assert [c.parent.parent_unit_id for c in out] == [f"p{i}" for i in range(N)]
    assert all(c.spans[-1] == "wide" for c in out)
    # serial would be N * DELAY_S = 1.2 s; concurrent is ~DELAY_S
    assert wall < DELAY_S * 3, wall
