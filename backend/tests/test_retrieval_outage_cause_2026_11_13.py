"""A retrieval outage abstain is system_unavailable, not no_evidence."""

from __future__ import annotations

import pytest

from app.answer_contract import abstain_cause, abstain_copy_key


def test_outage_error_is_system_unavailable():
    cause = abstain_cause(
        "abstained", "no_verified_clips", None, "context_retrieval_error:RuntimeError"
    )
    assert cause == "system_unavailable"
    assert abstain_copy_key(cause) == "abstain.system_unavailable"


def test_ordinary_empty_retrieval_is_no_evidence():
    assert abstain_cause("abstained", "no_verified_clips", None) == "no_evidence"
    assert abstain_cause("abstained", "no_verified_clips", None, None) == "no_evidence"
    assert abstain_cause("abstained", "no_verified_clips", None, "") == "no_evidence"


def test_unrelated_error_text_does_not_flip_cause():
    assert abstain_cause("abstained", "no_verified_clips", None, "other") == "no_evidence"


@pytest.mark.asyncio
async def test_bridge_abstain_reports_outage_and_does_not_pass():
    from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
    from tests.test_fp_audit_fixes_2026_11_13 import _bridge_ctx

    ctx = _bridge_ctx("What is suffering?", [])
    result = await FirstPersonBridgeStage()._abstain(
        ctx,
        "abstained",
        reason="no_verified_clips",
        error="context_retrieval_error:RuntimeError",
    )
    assert result.verification["abstain_cause"] == "system_unavailable"
    assert result.verification["passed"] is False
    assert result.route_metadata["abstain_copy_key"] == "abstain.system_unavailable"
    assert not result.citations
