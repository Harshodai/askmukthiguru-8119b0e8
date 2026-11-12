"""T2-05: behaviour tests against a real Qdrant and a real Redis.

These are the store-level contracts the first-person lane relies on and that a
mocked client cannot prove: the payload filter that decides which clips may be
served, and the exact-cache entry that decides whether a served answer replays.

They run against service containers in CI (`fixture-stores.yml`) and against the
local compose stack during development. Locally they skip when a store is
unreachable, so an ordinary `pytest` run on a machine without docker still passes.
In the CI job `FIXTURE_STORES_REQUIRED=1` turns that skip into a failure, because
there an unreachable store means the job proved nothing.

Nothing here writes to a serving collection: the Qdrant collection is created
with a throwaway name and dropped in teardown, and the Redis keys carry a
throwaway prefix and are deleted in teardown. No flush of any kind is used.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest

pytestmark = pytest.mark.fixture_store

FIXTURE_COLLECTION_PREFIX = "t2_05_fixture_"
FIXTURE_KEY_PREFIX = "t2_05_fixture:"
DENSE_DIMENSION = 8


def _unavailable(message: str) -> None:
    """Skip locally; fail in the CI job, where a missing store is a broken job."""
    if os.environ.get("FIXTURE_STORES_REQUIRED") == "1":
        pytest.fail(message)
    pytest.skip(message)


def _qdrant_client():
    qdrant_client = pytest.importorskip("qdrant_client")
    url = os.environ.get("FIXTURE_QDRANT_URL", "http://localhost:6333")
    client = qdrant_client.QdrantClient(url=url, timeout=10, prefer_grpc=False)
    try:
        client.get_collections()
    except Exception as exc:  # noqa: BLE001 - any transport failure means "no fixture"
        _unavailable(f"Qdrant unreachable at {url}: {exc}")
    return client


def _fixture_redis_url() -> str:
    """CI injects `FIXTURE_REDIS_URL`; locally reuse the app's own (authenticated) URL.

    The local compose Redis requires a password, so a hard-coded
    `redis://localhost:6379/15` cannot connect. `force_test_database` is the same
    helper the suite's conftest uses to keep tests off the serving database.
    """
    override = os.environ.get("FIXTURE_REDIS_URL")
    if override:
        return override
    from app.config import settings
    from tests.redis_url_safety import force_test_database

    return force_test_database(str(settings.redis_url))


def _redis_client():
    redis = pytest.importorskip("redis")
    url = _fixture_redis_url()
    client = redis.Redis.from_url(url, decode_responses=False, socket_connect_timeout=3)
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 - any transport failure means "no fixture"
        _unavailable(f"Redis unreachable at {url}: {exc}")
    return client


def _unit_vector(seed: float) -> list[float]:
    vector = [0.0] * DENSE_DIMENSION
    vector[0] = seed
    vector[1] = 1.0
    return vector


def _clip_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "video_id": "vid_fixture",
        "start_ms": 1000,
        "end_ms": 2000,
        "teacher_id": "preethaji",
        "speaker": "Sri Preethaji",
        "verbatim_text": "A fixture span used only by the fixture-store contract test.",
        "first_person_eligible": True,
        "rights_cleared": True,
        "is_verbatim": True,
        "domain_rights_status": "licensed",
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def qdrant_store():
    """A throwaway multi-vector collection shaped exactly like production."""
    from qdrant_client.models import PointStruct

    from services.first_person_store import FirstPersonStore

    client = _qdrant_client()
    collection = f"{FIXTURE_COLLECTION_PREFIX}{uuid.uuid4().hex[:10]}"
    store = FirstPersonStore(collection=collection, client=client, dimension=DENSE_DIMENSION)
    store.init_collection()
    try:
        yield store, PointStruct
    finally:
        client.delete_collection(collection_name=collection)
        client.close()


def _seed(store, point_struct, payloads: list[dict[str, Any]]) -> None:
    store.client.upsert(
        collection_name=store.collection,
        points=[
            point_struct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, payload["video_id"])),
                vector={"passage_dense": _unit_vector(1.0)},
                payload=payload,
            )
            for payload in payloads
        ],
        wait=True,
    )


def _register_says_licensed(monkeypatch) -> None:
    """Isolate the store read from the rights-register join, with no network.

    `FirstPersonStore` resolves the rights status from the curated register on
    every read, so a synthetic clip with no register entry is correctly
    unlicensed and would be dropped for the wrong reason. These tests are about
    the store's own filtering and freshness, so the register is stubbed to
    mirror the payload; the join itself is asserted separately below.
    """
    monkeypatch.setattr(
        "services.first_person_store.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )


def _offline_serve_gates(monkeypatch) -> None:
    """Licence stubs for the pipeline path, plus no YouTube availability probe.

    The integrity re-check probes YouTube (FI-16). A unit test must not make that
    call, and the golden characterization matrix patches it for the same reason.
    """
    for target in (
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        "services.first_person_store.source_is_authoritatively_licensed",
    ):
        monkeypatch.setattr(
            target, lambda **kwargs: kwargs.get("domain_rights_status") == "licensed"
        )
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _vid: True
    )


def test_search_hybrid_serves_only_licensed_verbatim_eligible_clips(qdrant_store, monkeypatch):
    """The retrieval filter is the rights gate, not a post-filter the caller may skip.

    Five points sit at the same distance from the query. Only the one that is
    licensed, rights-cleared, verbatim and eligible may come back.
    """
    _register_says_licensed(monkeypatch)
    store, point_struct = qdrant_store
    _seed(
        store,
        point_struct,
        [
            _clip_payload(video_id="vid_good"),
            _clip_payload(video_id="vid_unlicensed", domain_rights_status="unlicensed"),
            _clip_payload(video_id="vid_rights_unclear", rights_cleared=False),
            _clip_payload(video_id="vid_not_verbatim", is_verbatim=False),
            _clip_payload(video_id="vid_not_eligible", first_person_eligible=False),
        ],
    )

    hits = store.search_hybrid(query_dense_vector=_unit_vector(1.0), limit=10, dedup_limit=10)

    served = sorted(hit.get("video_id") or hit.get("payload", {}).get("video_id") for hit in hits)
    assert served == ["vid_good"], f"only the licensed servable clip may be returned, got {served}"


def test_search_hybrid_refuses_a_clip_the_rights_register_does_not_vouch_for(qdrant_store):
    """A payload that says "licensed" is not a licence.

    Rights status is owned by the curated register (invariant X40). A point whose
    payload claims `licensed` but whose source is absent from the register must
    not be served, which is what stops a mis-stamped payload from publishing
    unlicensed teaching.
    """
    store, point_struct = qdrant_store
    _seed(store, point_struct, [_clip_payload(video_id="vid_payload_claims_licensed")])

    hits = store.search_hybrid(query_dense_vector=_unit_vector(1.0), limit=10, dedup_limit=10)

    assert hits == [], f"an unregistered source must never be served, got {hits}"


def test_points_servable_reads_the_store_every_time(qdrant_store, monkeypatch):
    """A revocation has to be visible to the serve-time check, not only to search.

    The pipeline re-checks the exact points it is about to serve. If that check
    reads a cached verdict instead of the store, a revoked clip keeps being
    served until the cache expires.
    """
    _register_says_licensed(monkeypatch)
    store, point_struct = qdrant_store
    _seed(store, point_struct, [_clip_payload(video_id="vid_revocable")])
    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "vid_revocable"))

    assert store.points_servable([point_id]) is True

    store.client.set_payload(
        collection_name=store.collection,
        payload={"rights_cleared": False},
        points=[point_id],
        wait=True,
    )

    assert store.points_servable([point_id]) is False
    assert store.points_servable([str(uuid.uuid4())]) is False, "a deleted point is not servable"


def _pipeline_with_real_cache(redis_client, *, servable: bool = True):
    from services.first_person_pipeline import FirstPersonPipeline

    class _StubStore:
        """Retrieval must never run; the serve-time re-check must.

        Replaying a cached answer still asks the store whether those exact points
        may be served, so the stub records that call instead of faking it away.
        """

        collection = "first_person_v1"

        def __init__(self) -> None:
            self.servable_checks: list[list[str]] = []

        def search_hybrid(self, *args, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("the exact-cache path must never retrieve")

        def points_servable(self, point_ids: list[str]) -> bool:
            self.servable_checks.append(list(point_ids))
            return servable

    store = _StubStore()
    return FirstPersonPipeline(store=store, redis_client=redis_client), store


def _served_answer(text: str) -> dict[str, Any]:
    """A minimal served answer whose citation passes the replay integrity re-check."""
    import hashlib

    body = "A fixture span used only by the fixture-store contract test."
    return {
        "answer_text": text,
        "citations": [
            {
                "point_id": "8f14e45f-ea3a-5f4f-9f1f-000000000001",
                "video_id": "vid_fixture",
                "start_ms": 1000,
                "end_ms": 2000,
                "verbatim_text": body,
                "transcript_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "speaker": "Sri Preethaji",
                "source_url": "https://www.youtube.com/watch?v=vid_fixture",
                "first_person_eligible": True,
                "rights_cleared": True,
                "is_verbatim": True,
                "domain_rights_status": "licensed",
            }
        ],
        "status": "served",
        "confidence": 0.71,
        "is_direct_answer": True,
    }


def test_exact_cache_round_trip_on_real_redis(monkeypatch):
    """A served answer survives a real serialise/deserialise cycle unchanged."""
    _offline_serve_gates(monkeypatch)
    redis_client = _redis_client()
    pipeline, store = _pipeline_with_real_cache(redis_client)
    question = f"{FIXTURE_KEY_PREFIX}{uuid.uuid4().hex}"
    answer = _served_answer("A fixture answer body.")
    cache_key = pipeline._get_exact_cache_key(question, None, language="en")
    try:
        pipeline.set_exact_cache(question, answer, language="en")
        assert redis_client.exists(cache_key) == 1, "the answer must actually be written"

        replayed = pipeline.check_exact_cache(question, language="en")

        assert replayed is not None, "a written entry must replay"
        assert replayed["citations"][0]["verbatim_text"] == answer["citations"][0]["verbatim_text"]
        assert replayed["status"] == answer["status"]
        assert store.servable_checks, "replay must re-check the points at the store"
    finally:
        redis_client.delete(cache_key)
        redis_client.close()


def test_cached_entry_whose_citation_no_longer_verifies_is_a_miss(monkeypatch):
    """Replay re-runs the integrity gate; a tampered entry is never served.

    The cache stores the quote and its hash. If the stored text and the stored
    hash disagree, the entry cannot be source-verified and must not replay — the
    whole point of not trusting a cache entry as evidence.
    """
    _offline_serve_gates(monkeypatch)
    redis_client = _redis_client()
    pipeline, _store = _pipeline_with_real_cache(redis_client)
    question = f"{FIXTURE_KEY_PREFIX}{uuid.uuid4().hex}"
    cache_key = pipeline._get_exact_cache_key(question, None, language="en")
    answer = _served_answer("A fixture answer body.")
    answer["citations"][0]["verbatim_text"] = "A different span that does not match the hash."
    try:
        pipeline.set_exact_cache(question, answer, language="en")

        assert pipeline.check_exact_cache(question, language="en") is None
    finally:
        redis_client.delete(cache_key)
        redis_client.close()


def test_cached_entry_is_not_replayed_once_the_store_says_it_is_not_servable(monkeypatch):
    """A cache hit is not a licence to serve; the store still decides.

    The exact cache is keyed on the question, but rights can be revoked and an
    admin can block a video between the write and the replay. Replay must ask the
    store again, and a "no" turns the hit into a miss.
    """
    _offline_serve_gates(monkeypatch)
    redis_client = _redis_client()
    question = f"{FIXTURE_KEY_PREFIX}{uuid.uuid4().hex}"
    answer = _served_answer("A fixture answer body.")

    writer, _ = _pipeline_with_real_cache(redis_client, servable=True)
    cache_key = writer._get_exact_cache_key(question, None, language="en")
    try:
        writer.set_exact_cache(question, answer, language="en")
        assert writer.check_exact_cache(question, language="en") is not None

        revoked, revoked_store = _pipeline_with_real_cache(redis_client, servable=False)

        assert revoked.check_exact_cache(question, language="en") is None
        assert revoked_store.servable_checks, "the replay must ask the store"
    finally:
        redis_client.delete(cache_key)
        redis_client.close()


def test_malformed_cache_entry_is_a_miss_and_is_removed():
    """A cache entry missing the contract keys is never served, and is cleaned up.

    Serving a half-written entry is how a seeker would see a blank or
    unattributed teaching; treating it as a miss costs one retrieval instead.
    """
    redis_client = _redis_client()
    pipeline, _store = _pipeline_with_real_cache(redis_client)
    question = f"{FIXTURE_KEY_PREFIX}{uuid.uuid4().hex}"
    cache_key = pipeline._get_exact_cache_key(question, None, language="en")
    try:
        redis_client.set(cache_key, json.dumps({"answer_text": "half an entry"}))

        assert pipeline.check_exact_cache(question, language="en") is None
        assert redis_client.exists(cache_key) == 0, "the malformed entry must be deleted"
    finally:
        redis_client.delete(cache_key)
        redis_client.close()
