"""Admin video-approval API: auth, CSRF, validation, filters, and the audit trail."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_container, get_container_async
from app.main import app, get_current_user_from_supabase
from services import first_person_video_decisions as fvd

client = TestClient(app)
BASE = "/api/admin/fp-videos"
VID = "abcdefghijk"
OTHER = "lmnopqrstuv"

ADMIN = {"id": "admin-1", "email": "a@example.com", "is_superuser": True, "aal": "aal2"}
NON_ADMIN = {"id": "user-1", "email": "u@example.com", "is_superuser": False, "aal": "aal2"}
AAL1_ADMIN = {"id": "admin-2", "email": "b@example.com", "is_superuser": True, "aal": "aal1"}

INVENTORY_CSV = (
    "video_id,title,channel,in_v10,child_spans,speaker_verified_spans,"
    "spans_with_voice_method,guru_ids,status_note\n"
    f"{VID},Calm Mind,Sri Preethaji & Sri Krishnaji,yes,4,4,4,krishnaji,\n"
    f"{OTHER},Half Checked,Sri Preethaji & Sri Krishnaji,yes,4,1,1,preethaji,\n"
    "zzzzzzzzzzz,Not Ingested,Times Now,no,,,,,has transcript+audio\n"
)


def _as(user):
    async def fixed():
        return user

    app.dependency_overrides[get_current_user_from_supabase] = fixed


class _FakeClient:
    """Qdrant stand-in whose scroll returns v10 child payloads."""

    def __init__(self, payloads):
        self._payloads = payloads
        self.writes = 0

    def scroll(self, **kwargs):
        return [SimpleNamespace(payload=p) for p in self._payloads], None

    def upsert(self, *a, **k):  # pragma: no cover - must never be called
        self.writes += 1

    set_payload = delete = upsert


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    inv = tmp_path / "inventory.csv"
    inv.write_text(INVENTORY_CSV, encoding="utf-8")
    monkeypatch.setattr(settings, "first_person_video_inventory_path", str(inv))
    monkeypatch.setattr(settings, "first_person_video_decisions_dir", str(tmp_path / "dec"))
    monkeypatch.setattr(settings, "first_person_context_collection", "first_person_v10")
    monkeypatch.setattr(settings, "csrf_secret", "test-csrf-secret-0123456789abcdef")
    fvd._CACHE.clear()
    # The shared admin limiter (default 5/minute) would 429 a multi-request test; it is
    # covered by its own tests, so give this module a roomy one.
    from app.security_utils import TTLRateLimiter

    monkeypatch.setattr(
        "app.main._ADMIN_RATE_LIMITER", TTLRateLimiter(ttl=60.0, max_requests=10_000)
    )
    from app.api import admin_video_review as mod

    mod._LIVE_CACHE.update(at=0.0, collection="", data=None)
    qdrant = _FakeClient(
        [
            {
                "video_id": VID,
                "speaker_verified": True,
                "voice_verification_method": "ecapa",
                "min_window_cosine": 0.71,
                "guru_id": "krishnaji",
            },
            {
                "video_id": VID,
                "speaker_verified": True,
                "voice_verification_method": "ecapa",
                "min_window_cosine": 0.64,
                "guru_id": "krishnaji",
            },
            {"video_id": OTHER, "speaker_verified": False, "guru_id": "preethaji"},
        ]
    )
    container = SimpleNamespace(qdrant_client=qdrant)
    app.dependency_overrides[get_container] = lambda: container
    app.dependency_overrides[get_container_async] = lambda: container
    _as(ADMIN)
    yield SimpleNamespace(qdrant=qdrant, mod=mod)
    app.dependency_overrides.pop(get_current_user_from_supabase, None)
    app.dependency_overrides.pop(get_container, None)
    app.dependency_overrides.pop(get_container_async, None)
    fvd._CACHE.clear()


def _csrf(user_headers=None) -> dict:
    res = client.get(f"{BASE}/csrf")
    assert res.status_code == 200, res.text
    return {"X-CSRF-Token": res.json()["token"]}


def _put(video_id=VID, body=None, headers="auto"):
    h = _csrf() if headers == "auto" else headers
    return client.put(f"{BASE}/{video_id}", json=body or {}, headers=h)


# ------------------------------------------------------------------- auth
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", BASE),
        ("get", f"{BASE}/csrf"),
        ("get", f"{BASE}/{VID}"),
        ("put", f"{BASE}/{VID}"),
    ],
)
def test_every_route_requires_an_authenticated_admin(method, path):
    async def no_user():
        raise HTTPException(status_code=401, detail="Authentication required")

    app.dependency_overrides[get_current_user_from_supabase] = no_user
    assert getattr(client, method)(path).status_code == 401
    _as(NON_ADMIN)
    assert getattr(client, method)(path).status_code == 403
    _as(AAL1_ADMIN)
    assert getattr(client, method)(path).status_code == 403  # AAL2 step-up required


def test_non_admin_cannot_write_even_with_a_valid_looking_token():
    token = _csrf()
    _as(NON_ADMIN)
    res = client.put(f"{BASE}/{VID}", json={"grade": "A"}, headers=token)
    assert res.status_code == 403
    assert fvd.blocked_video_ids() == frozenset()


# ------------------------------------------------------------------- CSRF
def test_write_without_csrf_token_is_refused():
    res = _put(body={"admin_approved": False, "reason": "bad audio"}, headers={})
    assert res.status_code == 403
    assert fvd.video_is_blocked(VID) is False


def test_write_with_garbage_or_foreign_user_token_is_refused():
    assert _put(body={"grade": "A"}, headers={"X-CSRF-Token": "a.b.c.d"}).status_code == 403
    token = _csrf()  # minted for admin-1
    other_admin = {**ADMIN, "id": "admin-9"}
    _as(other_admin)
    res = client.put(f"{BASE}/{VID}", json={"grade": "A"}, headers=token)
    assert res.status_code == 403


def test_expired_csrf_token_is_refused(monkeypatch):
    token = _csrf()
    import time as _time

    real = _time.time
    monkeypatch.setattr("app.security_utils.time.time", lambda: real() + 7200)
    res = client.put(f"{BASE}/{VID}", json={"grade": "A"}, headers=token)
    assert res.status_code == 403


def test_csrf_unavailable_without_a_signing_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "csrf_secret", None)
    monkeypatch.setattr(settings, "jwt_secret", None)
    assert client.get(f"{BASE}/csrf").status_code == 503
    assert _put(body={"grade": "A"}, headers={"X-CSRF-Token": "x"}).status_code == 503


# ------------------------------------------------------------ validation
@pytest.mark.parametrize(
    "body",
    [
        {"grade": "S"},
        {"admin_approved": "yes"},
        {"admin_approved": 1},
        {"human_speaker_check": "maybe"},
        {"notes": "x" * 2001},
        {"reason": "x" * 501},
        {"speaker_verified": True},  # machine field: not accepted
        {"unknown": 1},
    ],
)
def test_invalid_body_is_rejected(body):
    assert _put(body=body).status_code == 422


@pytest.mark.parametrize("bad_id", ["short", "has space 1", "a" * 12, "bad;id;;;;;"])
def test_invalid_video_id_is_rejected(bad_id):
    res = client.put(f"{BASE}/{bad_id}", json={"grade": "A"}, headers=_csrf())
    assert res.status_code in (404, 422)
    assert not (fvd.decisions_dir() / "decisions.json").exists()


def test_changing_approval_needs_a_reason():
    res = _put(body={"admin_approved": False})
    assert res.status_code == 422
    assert "reason" in res.json()["detail"]


# --------------------------------------------------------------- behaviour
def test_reject_then_list_get_and_audit():
    res = _put(
        body={
            "admin_approved": False,
            "grade": "D",
            "notes": "host voice",
            "reason": "wrong speaker",
        }
    )
    assert res.status_code == 200, res.text
    assert res.json()["blocks_serving"] is True
    assert fvd.video_is_blocked(VID) is True

    detail = client.get(f"{BASE}/{VID}").json()
    assert detail["video"]["serving"] == "blocked_by_admin"
    assert detail["video"]["decision"]["updated_by"] == "admin-1"
    assert detail["audit"][0]["reason"] == "wrong speaker"
    assert detail["audit"][0]["actor"] == "admin-1"


def test_machine_speaker_evidence_is_shown_and_never_overwritten(env):
    _put(body={"admin_approved": True, "human_speaker_check": "confirmed", "reason": "listened"})
    video = client.get(f"{BASE}/{VID}").json()["video"]
    assert video["machine"]["speaker_verified_spans"] == 2
    assert video["machine"]["spans_with_voice_method"] == 2
    assert video["machine"]["min_window_cosine"] == 0.64
    assert video["machine"]["speaker_status"] == "full"
    assert video["decision"]["human_speaker_check"] == "confirmed"
    # the half-checked video stays machine-"partial" whatever a human says about another video
    other = client.get(f"{BASE}/{OTHER}").json()["video"]
    assert other["machine"]["speaker_status"] == "none"
    assert env.qdrant.writes == 0  # the page never writes Qdrant


def test_approval_does_not_unblock_a_machine_unverified_video():
    """admin_approved=True records intent only; machine gates still apply downstream."""
    _put(OTHER, {"admin_approved": True, "reason": "I listened"})
    row = client.get(f"{BASE}/{OTHER}").json()["video"]
    assert row["serving"] == "gates_apply"
    assert row["machine"]["speaker_status"] == "none"
    assert fvd.video_is_blocked(OTHER) is False


def test_list_filters():
    _put(VID, {"admin_approved": False, "reason": "not the teacher"})
    _put(OTHER, {"admin_approved": True, "reason": "listened, fine"})

    def ids(**params):
        res = client.get(BASE, params=params)
        assert res.status_code == 200, res.text
        return {r["video_id"] for r in res.json()["rows"]}

    assert ids() == {VID, OTHER, "zzzzzzzzzzz"}
    assert ids(approved="rejected") == {VID}
    assert ids(approved="approved") == {OTHER}
    assert ids(approved="undecided") == {"zzzzzzzzzzz"}
    assert ids(verified="full") == {VID}
    assert ids(verified="none") == {OTHER}
    assert ids(in_v10="false") == {"zzzzzzzzzzz"}
    assert ids(in_v10="true") == {VID, OTHER}
    assert ids(channel="Times Now") == {"zzzzzzzzzzz"}
    assert ids(q="calm") == {VID}
    assert ids(channel="Times Now", in_v10="true") == set()

    body = client.get(BASE).json()
    assert body["summary"]["rejected"] == 1 and body["summary"]["missing_in_v10"] == 1
    assert body["live"] is True and body["collection"] == "first_person_v10"
    assert set(body["channels"]) == {"Sri Preethaji & Sri Krishnaji", "Times Now"}


def test_invalid_filter_values_and_paging_are_rejected():
    assert client.get(BASE, params={"verified": "sort-of"}).status_code == 422
    assert client.get(BASE, params={"approved": "maybe"}).status_code == 422
    assert client.get(BASE, params={"limit": 0}).status_code == 422
    assert client.get(BASE, params={"limit": 10_000}).status_code == 422
    assert client.get(BASE, params={"offset": -1}).status_code == 422


def test_paging():
    res = client.get(BASE, params={"limit": 1, "offset": 1}).json()
    assert res["total"] == 3 and len(res["rows"]) == 1


def test_page_falls_back_to_inventory_when_qdrant_is_down(env):
    def boom(**kwargs):
        raise RuntimeError("qdrant down")

    env.qdrant.scroll = boom
    body = client.get(BASE, params={"refresh": "true"}).json()
    assert body["live"] is False
    row = next(r for r in body["rows"] if r["video_id"] == VID)
    assert row["machine"]["source"] == "inventory"
    assert row["machine"]["min_window_cosine"] is None


def test_unknown_video_is_404():
    assert client.get(f"{BASE}/qqqqqqqqqqq").status_code == 404


def test_corrupt_decisions_file_makes_the_page_report_503_not_an_empty_list():
    _put(body={"admin_approved": False, "reason": "bad"})
    (fvd.decisions_dir() / "decisions.json").write_text("{broken", encoding="utf-8")
    fvd._CACHE.clear()
    assert client.get(BASE).status_code == 503


def test_clearing_a_decision_restores_default_behaviour():
    _put(body={"admin_approved": False, "reason": "bad"})
    res = _put(body={"reason": "reverting my mistake"})
    assert res.status_code == 200 and res.json()["decision"] is None
    assert fvd.video_is_blocked(VID) is False
    assert client.get(f"{BASE}/{VID}").json()["video"]["approval_state"] == "undecided"
