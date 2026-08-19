"""Focused regressions for governed source-release controls."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.corpus_release_registry import CorpusReleaseRegistry, CorpusReleaseTransitionError
from ingest.pipeline import IngestionPipeline


class Response:
    def __init__(self, data):
        self.data = data


class RpcCall:
    def __init__(self, store, name, payload):
        self.store = store
        self.name = name
        self.payload = payload

    def execute(self):
        if self.name == "register_source_release":
            return Response(self.store.register(self.payload))
        if self.name == "approve_source_release":
            return Response(self.store.approve(self.payload))
        if self.name == "activate_source_release":
            return Response(self.store.activate(self.payload))
        raise AssertionError(self.name)


class Table:
    def __init__(self, store):
        self.store = store
        self.filters = {}
        self.max_rows = None

    def select(self, _fields):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, _field, desc=False):
        return self

    def limit(self, value):
        self.max_rows = value
        return self

    def execute(self):
        rows = []
        for row in self.store.rows:
            if all(row.get(k) == v for k, v in self.filters.items()):
                rows.append(row.copy())
        if self.max_rows is not None:
            rows = rows[: self.max_rows]
        return Response(rows)


class Store:
    def __init__(self):
        self.rows = []

    def rpc(self, name, payload):
        return RpcCall(self, name, payload)

    def table(self, _name):
        return Table(self)

    def row(self, release_id):
        for item in self.rows:
            if item["id"] == release_id:
                return item
        raise RuntimeError("release does not exist")

    def register(self, payload):
        corpus = payload["p_corpus_id"]
        identity = payload["p_source_identity"]
        checksum = payload["p_content_checksum"]
        for item in self.rows:
            if item["corpus_id"] != corpus:
                continue
            if item["source_identity"] != identity:
                continue
            if item["content_checksum"] == checksum:
                return item.copy()
        version = 1
        for item in self.rows:
            if item["corpus_id"] == corpus:
                if item["source_identity"] == identity:
                    version = max(version, item["release_version"] + 1)
        item = {
            "id": str(uuid4()),
            "corpus_id": corpus,
            "source_url": payload["p_source_url"],
            "source_identity": identity,
            "release_version": version,
            "content_checksum": checksum,
            "status": "pending",
            "approved_by": None,
            "approved_at": None,
            "activated_at": None,
            "notes": payload.get("p_notes"),
            "created_at": "2026-08-13T00:00:00Z",
        }
        self.rows.append(item)
        return item.copy()

    def approve(self, payload):
        item = self.row(payload["p_release_id"])
        if item["status"] not in {"pending", "superseded"}:
            raise RuntimeError("release is not pending")
        item["status"] = "approved"
        item["approved_by"] = payload["p_approved_by"]
        item["approved_at"] = "2026-08-13T01:00:00Z"
        return item.copy()

    def activate(self, payload):
        item = self.row(payload["p_release_id"])
        if item["status"] != "approved":
            raise RuntimeError("only approved releases may be activated")
        for peer in self.rows:
            same_corpus = peer["corpus_id"] == item["corpus_id"]
            same_source = peer["source_identity"] == item["source_identity"]
            if same_corpus and same_source and peer["status"] == "active":
                peer["status"] = "superseded"
        item["status"] = "active"
        item["activated_at"] = "2026-08-13T02:00:00Z"
        return item.copy()


def registry(client=None, enabled=True):
    return CorpusReleaseRegistry(
        enabled=enabled,
        client=client,
        fallback_version=1,
    )


def candidate(reg, checksum):
    return reg.register_source(
        corpus_id="askmukthiguru",
        source_url="https://example.org/talk",
        source_identity="https://example.org/talk",
        content_checksum=checksum,
        notes="review candidate",
    )


def test_disabled_registry_uses_version_one_checkpoint_fallback():
    reg = registry(enabled=False)
    assert (
        reg.get_active_version(
            corpus_id="askmukthiguru",
            source_identity="https://example.org/talk",
        )
        == 1
    )
    pipeline = object.__new__(IngestionPipeline)
    pipeline._corpus_id = "askmukthiguru"
    pipeline._release_registry = reg
    assert pipeline._checkpoint_key("source", 1) == "askmukthiguru:v1:source"


def test_unavailable_registry_falls_back_gracefully():
    reg = registry(client=None, enabled=True)
    assert (
        reg.get_active_version(
            corpus_id="askmukthiguru",
            source_identity="https://example.org/talk",
        )
        == 1
    )


def test_candidate_registration_is_idempotent_and_safe_for_admins():
    reg = registry(Store())
    first = candidate(reg, "a" * 64)
    duplicate = candidate(reg, "a" * 64)
    assert duplicate.id == first.id
    assert duplicate.release_version == 1
    assert "content_checksum" not in duplicate.admin_dict()


def test_pending_release_cannot_activate_without_approval():
    reg = registry(Store())
    pending = candidate(reg, "a" * 64)
    with pytest.raises(CorpusReleaseTransitionError, match="only approved"):
        reg.activate_release(pending.id)


def test_activation_supersedes_previous_active_release():
    reg = registry(Store())
    first = candidate(reg, "a" * 64)
    reg.approve_release(first.id, approved_by="admin-a")
    reg.activate_release(first.id)
    second = candidate(reg, "b" * 64)
    reg.approve_release(second.id, approved_by="admin-b")
    active = reg.activate_release(second.id)
    statuses = {item.status for item in reg.list_releases(corpus_id="askmukthiguru")}
    assert active.release_version == 2
    assert statuses == {"active", "superseded"}


def test_active_version_is_isolated_by_corpus():
    store = Store()
    reg = registry(store)
    first = candidate(reg, "a" * 64)
    reg.approve_release(first.id, approved_by="admin-a")
    reg.activate_release(first.id)
    other = reg.register_source(
        corpus_id="teacher-b",
        source_url="https://example.org/talk",
        source_identity="https://example.org/talk",
        content_checksum="c" * 64,
    )
    reg.approve_release(other.id, approved_by="admin-b")
    reg.activate_release(other.id)
    assert (
        reg.get_active_version(
            corpus_id="askmukthiguru",
            source_identity="https://example.org/talk",
        )
        == 1
    )
    assert (
        reg.get_active_version(
            corpus_id="teacher-b",
            source_identity="https://example.org/talk",
        )
        == 1
    )


def test_active_release_version_overrides_legacy_checkpoint_version():
    class ActiveRegistry:
        def get_active_version(self, **_kwargs):
            return 7

    pipeline = object.__new__(IngestionPipeline)
    pipeline._corpus_id = "askmukthiguru"
    pipeline._release_registry = ActiveRegistry()
    assert pipeline._checkpoint_key("source", 1) == "askmukthiguru:v7:source"


def test_explicit_reactivation_restores_a_superseded_release_without_cross_scope_change():
    reg = registry(Store())
    first = candidate(reg, "a" * 64)
    reg.approve_release(first.id, approved_by="admin-a")
    reg.activate_release(first.id)
    second = candidate(reg, "b" * 64)
    reg.approve_release(second.id, approved_by="admin-b")
    reg.activate_release(second.id)

    restored = reg.reactivate_release(first.id, approved_by="rollback-reviewer")

    assert restored.id == first.id
    assert restored.status == "active"
    assert restored.approved_by == "rollback-reviewer"
    releases = reg.list_releases(corpus_id="askmukthiguru")
    assert {release.status for release in releases} == {"active", "superseded"}
    assert (
        reg.get_active_version(
            corpus_id="askmukthiguru", source_identity="https://example.org/talk"
        )
        == 1
    )
