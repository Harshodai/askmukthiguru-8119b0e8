from __future__ import annotations

import pytest

from app.config import settings
from rag.graph_strategies import route_after_intent
from rag.nodes.intent import _is_logistics_query
from rag.nodes.web_search import web_search_node


class OfficialSearch:
    async def search(self, query, *, user_id=None):
        return [
            {
                "title": "Guru Darshan registration",
                "source_url": "https://www.ekam.org/guru-darshan",
                "text": "Official registration information",
                "source_trust": "official_domain",
            }
        ]


def test_manifest_date_and_booking_queries_are_live_logistics():
    assert _is_logistics_query("When is the next Manifest event?")
    assert _is_logistics_query("How do I book Guru Darshan at Ekam?")
    assert not _is_logistics_query("What is the teaching of manifestation?")
    assert route_after_intent({"intent": "LIVE_LOGISTICS"}) == "temporal"


@pytest.mark.asyncio
async def test_live_logistics_only_uses_official_typed_results(monkeypatch):
    import rag.nodes as nodes

    monkeypatch.setattr(settings, "live_logistics_enabled", True)
    monkeypatch.setattr(nodes._services, "_web_search", OfficialSearch())
    result = await web_search_node(
        {"intent": "LIVE_LOGISTICS", "question": "When is Guru Darshan?", "user_id": "u1"}
    )

    event = result["web_search_results"][0]["live_event"]
    assert event["official_source_url"] == "https://www.ekam.org/guru-darshan"
    assert event["booking_url"] == event["official_source_url"]
    assert event["verified_at"] < event["expires_at"]


@pytest.mark.asyncio
async def test_non_logistics_intent_never_invokes_live_search(monkeypatch):
    import rag.nodes as nodes

    monkeypatch.setattr(settings, "live_logistics_enabled", True)
    monkeypatch.setattr(nodes._services, "_web_search", OfficialSearch())
    result = await web_search_node({"intent": "FACTUAL", "question": "What is Soul Sync?"})
    assert result == {"web_search_results": []}
