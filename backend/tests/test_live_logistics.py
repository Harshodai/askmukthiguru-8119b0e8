from __future__ import annotations

import pytest

from app.config import settings
from rag.graph_strategies import route_after_intent
from rag.nodes.intent import (
    _is_app_boundary_query,
    _is_logistics_query,
    _is_playful_edge_query,
    handle_casual,
)
from rag.nodes.generation import generate_answer
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


@pytest.mark.asyncio
async def test_app_memory_boundary_returns_direct_privacy_answer():
    result = await handle_casual(
        {
            "question": "What is the difference between conversation memory and my private Second Brain vault?",
            "intent": "CAPABILITY",
            "chat_history": [],
        }
    )
    assert result["intent"] == "CAPABILITY"
    assert result["grounding_state"] == "capability_answer"
    assert "anonymous" in result["final_answer"]
    assert "invent" in result["final_answer"]


@pytest.mark.asyncio
async def test_playful_hypothetical_returns_bounded_capability_answer():
    result = await handle_casual(
        {
            "question": "Can I manifest a unicorn using the third sacred secret?",
            "intent": "CAPABILITY",
            "chat_history": [],
        }
    )
    assert result["grounding_state"] == "bounded_hypothetical"
    assert "playful hypothetical" in result["final_answer"]
    assert "guarantee enlightenment" in result["final_answer"]


def test_app_memory_boundary_queries_use_fast_capability_route():
    assert _is_app_boundary_query("What is the difference between conversation memory and my private Second Brain vault?")
    assert _is_app_boundary_query("What do you remember about my spiritual practice?")
    assert not _is_app_boundary_query("What is the Beautiful State?")
    assert _is_playful_edge_query("Can I manifest a unicorn using the third sacred secret?")


def test_manifest_date_and_booking_queries_are_live_logistics():
    assert _is_logistics_query("When is the next Manifest event?")
    assert _is_logistics_query("How do I book Guru Darshan at Ekam?")
    assert _is_logistics_query("What is the latest official Ekam program or event information right now?")
    assert _is_logistics_query("What is the current schedule on the official Oneness Movement website?")
    assert not _is_logistics_query("What is the teaching of manifestation?")
    assert route_after_intent({"intent": "LIVE_LOGISTICS"}) == "temporal"


@pytest.mark.asyncio
async def test_live_logistics_generation_uses_official_results_directly():
    result = await generate_answer(
        {
            "question": "What is the latest official Ekam program information?",
            "intent": "LIVE_LOGISTICS",
            "relevant_docs": [],
            "web_search_results": [
                {
                    "title": "Ekam Events",
                    "text": "Official current event information.",
                    "official_source_url": "https://www.ekam.org/events",
                }
            ],
            "detected_language": "en",
            "chat_history": [],
        }
    )
    assert result["verification"]["method"] == "official_live_web_results"
    assert result["citations"] == ["https://www.ekam.org/events"]
    assert "Ekam Events" in result["answer"]


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
