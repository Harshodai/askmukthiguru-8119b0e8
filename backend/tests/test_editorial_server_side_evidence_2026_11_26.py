"""Editorial fact-check verifies against server-fetched evidence, never client-supplied text."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

import app.api.editorial as editorial_api
import services.evidence_adapters.qdrant_adapter as qa
from domain.evidence_contract import ClaimVerificationReport, EvidenceCandidate
from services.editorial.editorial_service import EditorialIntelligenceService, ScriptBlock
from services.evidence_adapters.qdrant_adapter import QdrantEvidenceAdapter
from services.guru_registry import get_gurus

TEXT = "Be still and know."
T1 = get_gurus()[0].id
T2 = get_gurus()[1].id


def _ev(
    eid: str = "e1", text: str = TEXT, teacher: str = T1, verified: bool = True
) -> EvidenceCandidate:
    return EvidenceCandidate(
        evidence_id=eid,
        source_id="s1",
        text=text,
        teacher_id=teacher,
        speaker_verified=verified,
        retrieval_source="qdrant",
    )


def _svc(store: dict[str, EvidenceCandidate]) -> EditorialIntelligenceService:
    return EditorialIntelligenceService(
        search_fn=lambda *_: [],
        evidence_resolver=lambda ids: {i: store[i] for i in ids if i in store},
    )


def _quote(ids: list[str], teacher: str | None = T1, text: str = TEXT) -> ScriptBlock:
    return ScriptBlock(
        block_id="b1",
        block_type="exact_quote",
        text=text,
        teacher_attributed=teacher,
        evidence_ids=ids,
    )


def _status(report: ClaimVerificationReport) -> str:
    return report.mappings[0].verification_status


def test_matching_server_id_verifies() -> None:
    assert _status(_svc({"e1": _ev()}).fact_check_blocks([_quote(["e1"])])) == "verified"


def test_fabricated_client_evidence_is_not_verified() -> None:
    fake = _ev("fake", text="Invented words.")
    r = _svc({}).fact_check_blocks([_quote(["fake"], text="Invented words.")], [fake])
    assert _status(r) == "unverifiable"
    assert not r.passed


def test_unknown_id_is_unverifiable() -> None:
    r = _svc({"e1": _ev()}).fact_check_blocks([_quote(["nope"])])
    assert _status(r) == "unverifiable"


def test_client_text_conflicting_with_server_record_is_rejected() -> None:
    forged = _ev("e1", text="Something the teacher never said.")
    r = _svc({"e1": _ev()}).fact_check_blocks(
        [_quote(["e1"], text="Something the teacher never said.")], [forged]
    )
    assert _status(r) == "unverifiable"
    assert "does not match the server record" in r.mappings[0].notes


def test_client_cannot_assert_speaker_verified() -> None:
    claimed = _ev("e1", verified=True)
    r = _svc({"e1": _ev(verified=False)}).fact_check_blocks([_quote(["e1"])], [claimed])
    assert _status(r) == "quote_mismatch"


def test_exact_quote_without_teacher_not_verified() -> None:
    svc = _svc({"e1": _ev()})
    for teacher in (None, ""):
        r = svc.fact_check_blocks([_quote(["e1"], teacher=teacher)])
        assert _status(r) != "verified"
        assert "attributed teacher" in r.mappings[0].notes
        assert not r.passed


def test_misattribution_still_caught() -> None:
    r = _svc({"e1": _ev(teacher=T1)}).fact_check_blocks([_quote(["e1"], teacher=T2)])
    assert _status(r) == "misattributed"


# --- resolver, adapter and API-level checks ---

SPAN_UUID = "11111111-1111-1111-1111-111111111111"


def _pt(pid: str, payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(id=pid, payload=payload, score=0.0)


def _payload(**kw: Any) -> dict[str, Any]:
    base = {
        "verbatim_text": TEXT,
        "source_url": "https://example.test/v",
        "video_id": "vid",
        "domain_rights_status": "licensed",
        "guru_id": T1,
        "speaker_verified": True,
    }
    return {**base, **kw}


class _FakeQdrant:
    def __init__(self, by_key: dict[str, list[SimpleNamespace]], by_id: list[SimpleNamespace]):
        self.by_key, self.by_id = by_key, by_id

    def scroll(self, *, scroll_filter: Any, **_: Any) -> tuple[list[SimpleNamespace], None]:
        return self.by_key.get(scroll_filter.must[0].key, []), None

    def retrieve(self, *, ids: list[str], **_: Any) -> list[SimpleNamespace]:
        return [p for p in self.by_id if p.id in ids]


def test_fetch_by_ids_maps_ids_and_enforces_licensing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        qa, "source_is_authoritatively_licensed", lambda **kw: kw["source_id"] != "bad"
    )
    client = _FakeQdrant(
        {
            "source_span_id": [_pt("p1", _payload(source_span_id="span-1"))],
            "evidence_id": [_pt("p2", _payload(evidence_id="ev-2"))],
        },
        [
            _pt(SPAN_UUID, _payload()),
            _pt("p9", _payload(source_asset_id="bad", source_span_id="span-bad")),
        ],
    )
    out = QdrantEvidenceAdapter(client, "col").fetch_by_ids(
        ["span-1", "ev-2", SPAN_UUID, "span-bad"]
    )
    assert {"span-1", "ev-2", SPAN_UUID} <= set(out)
    assert "span-bad" not in out
    assert out["span-1"].speaker_verified is True and out["span-1"].text == TEXT


def _container(client: Any) -> Any:
    return SimpleNamespace(embedding=None, memgraph_driver=None, qdrant_client=client)


@pytest.fixture
def _fresh_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(editorial_api, "_EDITORIAL_SINGLETON", None)


def test_no_qdrant_client_gives_503(_fresh_singleton: None) -> None:
    req = editorial_api.FactCheckRequest(blocks=[_quote(["e1"])])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(editorial_api.fact_check_script(req, _admin={}, container=_container(None)))
    assert exc.value.status_code == 503


def test_api_client_pool_with_altered_text_cannot_verify(
    _fresh_singleton: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(qa, "source_is_authoritatively_licensed", lambda **_: True)
    client = _FakeQdrant({"source_span_id": [_pt("p1", _payload(source_span_id="e1"))]}, [])
    altered = "Altered words the teacher never said."
    req = editorial_api.FactCheckRequest(
        blocks=[_quote(["e1"], text=altered)], evidence_pool=[_ev("e1", text=altered)]
    )
    out = asyncio.run(editorial_api.fact_check_script(req, _admin={}, container=_container(client)))
    assert out["passed"] is False
    assert out["mappings"][0]["verification_status"] == "unverifiable"
    assert out["evidence_pool_trust"] == "server"
