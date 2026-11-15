"""inspect-source must be able to reach the live Qdrant facade (2026-11-13 audit).

``GET /api/search/inspect-source`` reads ``container.qdrant.get_client()`` and
``container.qdrant.collection_name``. The facade declared neither, so every live
request raised ``AttributeError`` inside its try-block, was logged at WARNING and
silently served the local-transcript fallback instead of the corpus:

    "Failed to scroll Qdrant for source ... 'QdrantService' object has no
     attribute 'get_client'"

The route's own unit test could not catch it because it passes a stand-in
container whose qdrant object has ``get_client``. This pins the real surface.
"""

from __future__ import annotations

from services.qdrant_service import QdrantService


def _facade(client: object, collection: str) -> QdrantService:
    """A facade with no client manager, so no connection is opened."""
    service = object.__new__(QdrantService)
    service._client = client  # type: ignore[attr-defined]
    service._collection = collection  # type: ignore[attr-defined]
    return service


def test_facade_exposes_the_client_and_collection_name_the_route_reads() -> None:
    client = object()
    service = _facade(client, "first_person_v10")

    assert service.get_client() is client
    assert service.collection_name == "first_person_v10"


def test_the_route_reads_only_the_pinned_names() -> None:
    """A rename in either place is what broke this endpoint; pin both names."""
    import inspect

    from app.api import search_routes

    source = inspect.getsource(search_routes)
    assert "container.qdrant.get_client()" in source
    assert "container.qdrant.collection_name" in source
