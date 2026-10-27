"""Tests for release lifecycle governance: register -> stamp -> filter -> enforce (DE-0.1, DE-0.2, DE-0.3, DE-0.4)."""

from __future__ import annotations

import hashlib
import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from app.corpus_release_registry import CorpusReleaseRegistry, SourceReleaseRegistry
from services.first_person_serving_contract import CollectionContract, fingerprint_components
from services.qdrant.indexer import QdrantIndexer
from services.qdrant.source_policy import filter_by_release
from services.qdrant.utils import QdrantUtils


class FakeReleaseStore:
    """In-memory simulation of the Supabase source_releases table and RPCs."""

    def __init__(self):
        self.rows = []

    def rpc(self, name, payload):
        class RpcCall:
            def __init__(self, store, name, payload):
                self.store = store
                self.name = name
                self.payload = payload

            def execute(self):
                class Response:
                    def __init__(self, data):
                        self.data = data

                if self.name == "register_source_release":
                    return Response(self.store.register(self.payload))
                raise AssertionError(f"Unknown RPC {self.name}")

        return RpcCall(self, name, payload)

    def table(self, _name):
        class Table:
            def __init__(self, store):
                self.store = store
                self.filters = {}

            def select(self, _fields):
                return self

            def eq(self, key, value):
                self.filters[key] = value
                return self

            def limit(self, _value):
                return self

            def execute(self):
                class Response:
                    def __init__(self, data):
                        self.data = data

                matching = [
                    row.copy()
                    for row in self.store.rows
                    if all(row.get(k) == v for k, v in self.filters.items())
                ]
                return Response(matching)

        return Table(self)

    def register(self, payload):
        corpus = payload["p_corpus_id"]
        identity = payload["p_source_identity"]
        checksum = payload["p_content_checksum"]
        for item in self.rows:
            if item["corpus_id"] == corpus and item["source_identity"] == identity:
                if item["content_checksum"] == checksum:
                    return item.copy()

        version = 1
        for item in self.rows:
            if item["corpus_id"] == corpus and item["source_identity"] == identity:
                version = max(version, item["release_version"] + 1)

        item = {
            "id": str(uuid4()),
            "corpus_id": corpus,
            "source_url": payload["p_source_url"],
            "source_identity": identity,
            "release_version": version,
            "content_checksum": checksum,
            "status": "active",
            "approved_by": "test",
            "approved_at": "2026-10-27T00:00:00Z",
            "activated_at": "2026-10-27T00:00:00Z",
            "notes": payload.get("p_notes"),
            "created_at": "2026-10-27T00:00:00Z",
        }
        self.rows.append(item)
        return item.copy()


def test_one_release_per_ingest():
    """DE-0.1: Ingestion registers a source release and stamps it on indexed points."""
    store = FakeReleaseStore()
    registry = SourceReleaseRegistry(enabled=True, client=store, fallback_version=1)

    text = "The supreme truth is that reality is undivided oneness and consciousness."
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    url = "https://example.org/talk-1"

    release = registry.register_source(
        corpus_id="askmukthiguru",
        source_url=url,
        source_identity=url,
        content_checksum=checksum,
    )
    assert release.release_version == 1
    assert release.content_checksum == checksum
    assert release.source_url == url

    # Now verify QdrantIndexer stamps source_release_version and content_checksum
    client = MagicMock()
    indexer = QdrantIndexer.__new__(QdrantIndexer)
    indexer._client = client
    indexer._collection = "test_corpus"
    indexer._utils = QdrantUtils()

    metadata = {
        "source_url": url,
        "chunk_index": 0,
        "source_release_version": release.release_version,
        "content_checksum": checksum,
    }
    indexer.upsert_chunks([text], [[0.1] * 8], [metadata])

    upsert_calls = client.upsert.call_args_list
    assert len(upsert_calls) == 1
    points = upsert_calls[0].kwargs["points"]
    assert len(points) == 1
    payload = points[0].payload
    assert payload["source_release_version"] == 1
    assert isinstance(payload["source_release_version"], int)
    assert payload["content_checksum"] == checksum
    assert isinstance(payload["content_checksum"], str)


def test_unchanged_checksum_is_noop():
    """DE-0.1: Ingesting unchanged content checksum is a no-op that returns the existing release."""
    store = FakeReleaseStore()
    registry = SourceReleaseRegistry(enabled=True, client=store, fallback_version=1)

    text = "Stillness is the key to deep spiritual awakening."
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    url = "https://example.org/talk-unchanged"

    rel1 = registry.register_source(
        corpus_id="askmukthiguru",
        source_url=url,
        source_identity=url,
        content_checksum=checksum,
    )
    assert rel1.release_version == 1

    # Re-registering with identical checksum
    rel2 = registry.register_source(
        corpus_id="askmukthiguru",
        source_url=url,
        source_identity=url,
        content_checksum=checksum,
    )
    assert rel2.id == rel1.id
    assert rel2.release_version == 1
    assert len(store.rows) == 1


def test_changed_content_bumps_version():
    """DE-0.1: Changed content checksum bumps release version to N+1."""
    store = FakeReleaseStore()
    registry = SourceReleaseRegistry(enabled=True, client=store, fallback_version=1)

    text_v1 = "Initial draft transcript text."
    checksum_v1 = hashlib.sha256(text_v1.encode("utf-8")).hexdigest()
    url = "https://example.org/talk-versioning"

    rel1 = registry.register_source(
        corpus_id="askmukthiguru",
        source_url=url,
        source_identity=url,
        content_checksum=checksum_v1,
    )
    assert rel1.release_version == 1

    text_v2 = "Corrected transcript text with edited teacher words."
    checksum_v2 = hashlib.sha256(text_v2.encode("utf-8")).hexdigest()

    rel2 = registry.register_source(
        corpus_id="askmukthiguru",
        source_url=url,
        source_identity=url,
        content_checksum=checksum_v2,
    )
    assert rel2.release_version == 2
    assert rel2.content_checksum == checksum_v2
    assert len(store.rows) == 2


def test_release_filter_shadow_and_enforce(caplog):
    """DE-0.3: Read-time release filter in off, shadow, and enforce modes."""
    from app.metrics import RETRIEVAL_RELEASE_SHADOW_EXCLUSIONS_TOTAL

    store = FakeReleaseStore()
    registry = SourceReleaseRegistry(enabled=True, client=store, fallback_version=1)

    # Register source A at version 2 (active)
    store.rows.append(
        {
            "id": str(uuid4()),
            "corpus_id": "askmukthiguru",
            "source_url": "https://example.org/src-A",
            "source_identity": "https://example.org/src-A",
            "release_version": 2,
            "content_checksum": "checksum-v2",
            "status": "active",
        }
    )
    # Register source B at version 1 (active)
    store.rows.append(
        {
            "id": str(uuid4()),
            "corpus_id": "askmukthiguru",
            "source_url": "https://example.org/src-B",
            "source_identity": "https://example.org/src-B",
            "release_version": 1,
            "content_checksum": "checksum-b",
            "status": "active",
        }
    )

    docs = [
        {
            "id": "doc1",
            "source_url": "https://example.org/src-A",
            "source_release_version": 2,
            "text": "Source A active version",
        },
        {
            "id": "doc2",
            "source_url": "https://example.org/src-A",
            "source_release_version": 1,  # Inactive / superseded
            "text": "Source A stale version",
        },
        {
            "id": "doc3",
            "source_url": "https://example.org/src-B",
            "source_release_version": 1,
            "text": "Source B active version",
        },
    ]

    # Mode 1: 'off' -> all 3 docs returned, no metrics incremented
    allowed, dropped = filter_by_release(docs, filter_mode="off", registry=registry, corpus_id="askmukthiguru")
    assert len(allowed) == 3
    assert dropped == 0

    # Mode 2: 'shadow' -> all 3 docs returned, but stale hit triggers metric and log
    initial_metric = RETRIEVAL_RELEASE_SHADOW_EXCLUSIONS_TOTAL._value.get()
    with caplog.at_level(logging.INFO):
        allowed_shadow, dropped_shadow = filter_by_release(
            docs, filter_mode="shadow", registry=registry, corpus_id="askmukthiguru"
        )
    assert len(allowed_shadow) == 3
    assert dropped_shadow == 0
    assert RETRIEVAL_RELEASE_SHADOW_EXCLUSIONS_TOTAL._value.get() == initial_metric + 1
    assert "would_filter_inactive_release" in caplog.text

    # Mode 3: 'enforce' -> doc2 dropped, only doc1 and doc3 kept
    allowed_enforce, dropped_enforce = filter_by_release(
        docs, filter_mode="enforce", registry=registry, corpus_id="askmukthiguru"
    )
    assert len(allowed_enforce) == 2
    assert dropped_enforce == 1
    assert [d["id"] for d in allowed_enforce] == ["doc1", "doc3"]


def test_cache_fingerprint_carries_release_version():
    """DE-0.3: Exact cache fingerprint and components incorporate release_version."""
    entry = CollectionContract(
        name="first_person_v10",
        schema="first-person-legacy-clip-v1",
        role="legacy",
        corpus_version="legacy-clip-store",
        required_payload_fields=("first_person_eligible",),
        evidence_policy="payload_rights_claim_unverified",
    )

    # fingerprint_components without explicit release version defaults cleanly
    comp1 = fingerprint_components(entry)
    assert "release_version" in comp1

    # fingerprint_components with explicit release version
    comp2 = fingerprint_components(entry, release_version=3)
    assert comp2["release_version"] == "3"
    assert comp2["collection"] == "first_person_v10"

    # Pipeline exact cache fingerprint components incorporate release_version
    from services.first_person_pipeline import FirstPersonPipeline

    pipeline = FirstPersonPipeline.__new__(FirstPersonPipeline)
    pipeline._store = type("S", (), {"collection": "first_person_v10"})()
    pipeline._collection_contract_cache = None
    pipeline._boundary_guard_enabled = False
    pipeline._content_quality_gate_enabled = False
    pipeline._corpus_manifest_digest = lambda: "digest123"

    with patch.object(settings, "corpus_release_fallback_version", 5):
        components = pipeline._serving_policy_components("allow", "block")
        assert "release_version" in components
        assert components["release_version"] == "5"
