"""Guards for the 2026-10-30 branch-review fixes.

Each test fails on the code as it was before the fix:
 1. release filter ran twice and the second pass dropped every searcher doc in enforce
 2. retrieval-feedback service was rebuilt on every request
 3. admin provenance only looked in the chat collection
 4. RAPTOR summary ids collided across multi-source clusters
"""

from __future__ import annotations

import asyncio
import pathlib
import types
import uuid

import pytest

from ingest.raptor import _raptor_summary_point_id
from rag.nodes.retrieval import _needs_release_filter
from services import retrieval_feedback
from services.qdrant.source_policy import filter_by_release

_BACKEND = pathlib.Path(__file__).resolve().parents[1]


class _Registry:
    def get_active_version(self, corpus_id, source_identity, fallback_version=1, strict=False):
        return 1


def _searcher_shaped_doc(**extra):
    # What QdrantSearcher builds: flattened, carries chunk_id and rights, source_url.
    doc = {
        "text": "t",
        "source_url": "https://youtu.be/abc",
        "chunk_id": "p1",
        "domain_rights_status": "cleared",
        "source_release_version": 1,
        "release_screened": True,
    }
    doc.update(extra)
    return doc


def test_screened_searcher_doc_is_not_filtered_a_second_time():
    assert _needs_release_filter(_searcher_shaped_doc()) is False


def test_unscreened_qdrant_point_still_gets_filtered():
    assert _needs_release_filter({"chunk_id": "p1", "source_url": "u"}) is True


def test_okf_and_web_docs_have_no_release_concept():
    assert _needs_release_filter({"text": "okf", "source": "okf"}) is False


def test_enforce_fails_closed_on_a_flattened_doc_without_the_stamp():
    """Why the flag exists: the old second pass saw docs without a stamp and dropped all."""
    doc = _searcher_shaped_doc()
    doc.pop("source_release_version")
    doc.pop("release_screened")
    kept, dropped = filter_by_release([doc], filter_mode="enforce", registry=_Registry())
    assert kept == [] and dropped == 1


def test_searcher_docs_carry_stamp_and_screen_flag():
    src = (_BACKEND / "services/qdrant/searcher.py").read_text()
    assert '"release_screened": True' in src
    assert '"source_release_version": hit.payload.get("source_release_version")' in src


def test_feedback_service_is_shared(monkeypatch):
    monkeypatch.setattr(retrieval_feedback, "_SHARED_SERVICE", None)
    created = []

    class _Svc:
        def __init__(self):
            created.append(self)

    monkeypatch.setattr(retrieval_feedback, "RetrievalFeedbackService", _Svc)
    a = retrieval_feedback.get_retrieval_feedback_service()
    b = retrieval_feedback.get_retrieval_feedback_service()
    assert a is b and len(created) == 1


def test_call_sites_use_the_shared_getter():
    for rel in ("rag/nodes/retrieval.py", "services/qdrant/searcher.py"):
        text = (_BACKEND / rel).read_text()
        assert "RetrievalFeedbackService()" not in text, rel
        assert "get_retrieval_feedback_service()" in text, rel


def test_raptor_single_source_id_is_unchanged():
    url = "https://youtu.be/a"
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}:raptor_1:3"))
    assert _raptor_summary_point_id(url, 3, [url]) == expected


def test_raptor_multi_source_clusters_sharing_a_first_url_do_not_collide():
    first = "https://youtu.be/a"
    one = _raptor_summary_point_id(first, 0, [first, "https://youtu.be/b"])
    two = _raptor_summary_point_id(first, 0, [first, "https://youtu.be/c"])
    assert one != two
    assert one == _raptor_summary_point_id(first, 0, [first, "https://youtu.be/b"])


class _Point:
    def __init__(self, payload):
        self.id = "pt-1"
        self.payload = payload


class _Qdrant:
    """Holds the point only in the first-person collection."""

    def __init__(self):
        self.asked = []

    def retrieve(self, collection_name, ids, with_payload):
        self.asked.append(collection_name)
        if collection_name == "first_person_v10":
            return [_Point({"source_url": "u", "source_release_version": 2})]
        return []


def test_admin_provenance_finds_first_person_points(monkeypatch):
    from app.api import admin

    monkeypatch.setattr(admin.settings, "qdrant_collection", "chat_corpus", raising=False)
    monkeypatch.setattr(
        admin.settings, "first_person_context_collection", "first_person_v10", raising=False
    )
    client = _Qdrant()
    container = types.SimpleNamespace(qdrant_client=client)
    out = asyncio.run(admin.get_corpus_provenance("pt-1", user={"id": "a"}, container=container))
    assert out["source_release_version"] == 2
    assert client.asked[0] == "chat_corpus" and "first_person_v10" in client.asked


def test_admin_provenance_still_404s_when_nowhere():
    from fastapi import HTTPException

    from app.api import admin

    class _Empty:
        def retrieve(self, **_kw):
            return []

    container = types.SimpleNamespace(qdrant_client=_Empty())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(admin.get_corpus_provenance("zz", user={"id": "a"}, container=container))
    assert exc.value.status_code == 404
