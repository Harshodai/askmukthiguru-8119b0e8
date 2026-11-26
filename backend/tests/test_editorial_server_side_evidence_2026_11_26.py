"""Editorial fact-check verifies against server-fetched evidence, never client-supplied text."""

from __future__ import annotations

from domain.evidence_contract import ClaimVerificationReport, EvidenceCandidate
from services.editorial.editorial_service import EditorialIntelligenceService, ScriptBlock
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
