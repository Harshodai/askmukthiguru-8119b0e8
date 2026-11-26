"""Editorial store port, Supabase adapter, and author/approver separation (audit finding 7)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.api import editorial as editorial_api
from app.config import settings
from domain.evidence_contract import EvidenceCandidate
from services.editorial.editorial_service import (
    EditorialApprovalError,
    EditorialIntelligenceService,
    ScriptBlock,
)
from services.editorial.editorial_store import (
    EditorialStoreError,
    InMemoryEditorialStore,
    SupabaseEditorialStore,
)


class FakeClient:
    """Minimal supabase-py lookalike: table().upsert/insert/select/eq/limit/execute."""

    def __init__(self, fail: bool = False) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.fail = fail
        self._t = ""
        self._op: tuple[str, Any] = ("select", None)
        self._eq: tuple[str, Any] | None = None

    def table(self, name: str) -> FakeClient:
        self._t, self._op, self._eq = name, ("select", None), None
        return self

    def upsert(self, row: dict[str, Any]) -> FakeClient:
        self._op = ("upsert", row)
        return self

    def insert(self, row: dict[str, Any]) -> FakeClient:
        self._op = ("insert", row)
        return self

    def select(self, _cols: str) -> FakeClient:
        return self

    def eq(self, col: str, val: Any) -> FakeClient:
        self._eq = (col, val)
        return self

    def limit(self, _n: int) -> FakeClient:
        return self

    def execute(self) -> SimpleNamespace:
        if self.fail:
            raise ConnectionError("supabase down")
        rows = self.tables.setdefault(self._t, [])
        kind, row = self._op
        if kind == "upsert":
            rows[:] = [r for r in rows if r["id"] != row["id"]] + [row]
        elif kind == "insert":
            rows.append(row)
        elif self._eq:
            return SimpleNamespace(data=[r for r in rows if r[self._eq[0]] == self._eq[1]])
        return SimpleNamespace(data=list(rows))


def _ev() -> EvidenceCandidate:
    return EvidenceCandidate(
        evidence_id="ev-1",
        source_id="src-1",
        source_title="T",
        source_url="https://www.youtube.com/watch?v=xyz98765432",
        source_type="video",
        teacher_id="preethaji",
        speaker_verified=True,
        text="Suffering is born from division within oneself.",
        start_time=30.0,
        end_time=45.0,
        retrieval_source="qdrant",
        rights_status="licensed",
        concepts=["Suffering State"],
    )


def _svc(store: Any = None) -> EditorialIntelligenceService:
    return EditorialIntelligenceService(search_fn=lambda t, s, n: [_ev()], store=store)


def _good_script(svc: EditorialIntelligenceService) -> Any:
    return svc.build_verified_script(
        title="D",
        topic="S",
        blocks=[
            ScriptBlock(
                block_id="b1",
                block_type="exact_quote",
                text="Suffering is born from division within oneself.",
                teacher_attributed="preethaji",
                evidence_ids=["ev-1"],
            )
        ],
        trusted_evidence=[_ev()],
    )


def test_flag_default_off_uses_in_memory_store() -> None:
    assert settings.editorial_persistence_enabled is False
    assert isinstance(_svc()._store, InMemoryEditorialStore)


def test_flag_on_selects_supabase_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(editorial_api, "_EDITORIAL_SINGLETON", None)
    monkeypatch.setattr(settings, "editorial_persistence_enabled", True)
    client = FakeClient()
    container = SimpleNamespace(telemetry_sink=SimpleNamespace(client=client))
    svc = editorial_api.get_editorial_service(container)  # type: ignore[arg-type]
    assert isinstance(svc._store, SupabaseEditorialStore)
    monkeypatch.setattr(editorial_api, "_EDITORIAL_SINGLETON", None)


def test_supabase_round_trip_and_audit_rows() -> None:
    client = FakeClient()
    svc = _svc(SupabaseEditorialStore(client))
    proj = svc.create_project(title="Title", topic="S", author_id="alice")
    svc.attach_script(proj.project_id, _good_script(svc), actor_id="alice")

    loaded = svc.get_project(proj.project_id)
    assert loaded is not None and loaded.status == "review" and loaded.author_id == "alice"
    assert loaded.script is not None and loaded.script.verification.passed
    assert len(svc.list_projects()) == 1
    audit = client.tables["editorial_audit_log"]
    assert [(a["event"], a["from_state"], a["to_state"]) for a in audit] == [
        ("project_created", None, "idea"),
        ("script_attached", "idea", "review"),
    ]
    assert audit[1]["actor_id"] == "alice"


def test_adapter_error_is_raised_not_swallowed() -> None:
    svc = _svc(SupabaseEditorialStore(FakeClient(fail=True)))
    with pytest.raises(ConnectionError):
        svc.create_project(title="Title", topic="S", author_id="alice")


def test_adapter_without_client_raises() -> None:
    svc = _svc(SupabaseEditorialStore(None))
    with pytest.raises(EditorialStoreError):
        svc.create_project(title="Title", topic="S")


@pytest.mark.parametrize("store_kind", ["memory", "supabase"])
def test_author_cannot_approve_and_approver_is_recorded(store_kind: str) -> None:
    client = FakeClient()
    svc = _svc(SupabaseEditorialStore(client) if store_kind == "supabase" else None)
    proj = svc.create_project(title="Title", topic="S", author_id="Alice")
    svc.attach_script(proj.project_id, _good_script(svc), actor_id="Alice")

    for variant in (" alice ", "ALICE", "Alice"):
        with pytest.raises(EditorialApprovalError, match="must differ"):
            svc.approve_project(proj.project_id, reviewer_id=variant)
    assert svc.get_project(proj.project_id).status == "review"  # type: ignore[union-attr]

    approved = svc.approve_project(proj.project_id, reviewer_id="bob", notes="ok")
    assert approved.status == "approved" and approved.approved_by == "bob"
    last = approved.audit_log[-1]
    assert (last["event"], last["actor_id"], last["from_state"], last["to_state"]) == (
        "human_approved",
        "bob",
        "review",
        "approved",
    )
    published = svc.publish_project(proj.project_id, publisher_id="bob")
    assert published.audit_log[-1]["to_state"] == "published"
    if store_kind == "supabase":
        assert [a["event"] for a in client.tables["editorial_audit_log"]][-2:] == [
            "human_approved",
            "published",
        ]


def test_approval_still_requires_verified_claims() -> None:
    svc = _svc()
    proj = svc.create_project(title="Title", topic="S", author_id="alice")
    bad = svc.build_verified_script(
        title="D",
        topic="S",
        blocks=[
            ScriptBlock(
                block_id="b1",
                block_type="exact_quote",
                text="Suffering is born from division within oneself.",
                teacher_attributed="krishnaji",
                evidence_ids=["ev-1"],
            )
        ],
        trusted_evidence=[_ev()],
    )
    svc.attach_script(proj.project_id, bad)
    with pytest.raises(EditorialApprovalError):
        svc.approve_project(proj.project_id, reviewer_id="bob")


def test_script_attacher_cannot_approve_but_third_party_can() -> None:
    svc = _svc()
    proj = svc.create_project(title="Title", topic="S", author_id="A")
    svc.attach_script(proj.project_id, _good_script(svc), actor_id=" b ")
    with pytest.raises(EditorialApprovalError, match="must differ"):
        svc.approve_project(proj.project_id, reviewer_id="B")
    assert svc.approve_project(proj.project_id, reviewer_id="C").approved_by == "C"


@pytest.mark.parametrize("author", [None, "", "   "])
def test_unset_author_fails_closed(author: str | None) -> None:
    svc = _svc()
    proj = svc.create_project(title="Title", topic="S", author_id=author)
    svc.attach_script(proj.project_id, _good_script(svc), actor_id="b")
    with pytest.raises(EditorialApprovalError, match="no recorded author"):
        svc.approve_project(proj.project_id, reviewer_id="c")


def test_store_error_is_503_on_non_approve_route(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.admin import _require_admin
    from app.dependencies import get_container_async

    monkeypatch.setattr(
        editorial_api,
        "_EDITORIAL_SINGLETON",
        _svc(SupabaseEditorialStore(None)),
    )
    app = FastAPI()
    app.include_router(editorial_api.router)
    app.dependency_overrides[_require_admin] = lambda: {"id": "admin-1"}
    app.dependency_overrides[get_container_async] = lambda: SimpleNamespace()
    r = TestClient(app, raise_server_exceptions=False).post(
        "/api/editorial/projects", json={"title": "Title", "topic": "Topic"}
    )
    assert r.status_code == 503


def test_migration_revokes_all_privileges_from_public_roles() -> None:
    """RLS does not stop TRUNCATE, and Supabase grants it to anon/authenticated by default.

    Verified against a scratch Supabase Postgres on 2026-11-26: with only UPDATE/DELETE revoked,
    both roles could TRUNCATE the audit log, which cascades into dossiers, scripts and approvals.
    """
    import re
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20261126120000_editorial_persistence.sql"
    ).read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", sql)
    assert "REVOKE ALL ON public.editorial_audit_log FROM PUBLIC, anon, authenticated" in flat
    assert "REVOKE ALL ON SEQUENCE public.editorial_audit_log_id_seq" in flat
    assert (
        "REVOKE ALL ON public.editorial_projects, public.editorial_dossiers, "
        "public.editorial_scripts, public.editorial_approvals FROM PUBLIC, anon, authenticated"
    ) in flat
