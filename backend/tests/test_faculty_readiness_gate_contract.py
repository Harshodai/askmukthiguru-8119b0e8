from scripts.ops.faculty_readiness_gate import validate_first_person_response


def _citation(text="A verified teaching."):
    return {
        "verbatim_text": text,
        "is_verbatim": True,
        "speaker_verified": True,
        "domain_rights_status": "licensed",
        "boundary_status": "verified",
    }


def test_gate_accepts_exact_source_reconstruction():
    ok, detail = validate_first_person_response(
        {
            "status": "success",
            "answer_text": "Opening. Answer.",
            "citations": [_citation("Opening."), _citation("Answer.")],
        }
    )
    assert ok is True
    assert "2 licensed" in detail


def test_gate_accepts_fail_closed_abstention_without_evidence():
    ok, detail = validate_first_person_response(
        {
            "status": "abstained",
            "answer_text": "No verified first-person discourse found.",
            "citations": [],
        }
    )
    assert ok is True
    assert "fail-closed" in detail


def test_gate_rejects_generated_body_and_generated_gloss():
    citation = _citation()
    citation["translated_text"] = "Generated translation"
    ok, detail = validate_first_person_response(
        {"status": "success", "answer_text": "LLM connective prose", "citations": [citation]}
    )
    assert ok is False
    assert "translation gloss" in detail or "reconstruction" in detail


def test_gate_rejects_unlicensed_or_unverified_citation():
    citation = _citation()
    citation["domain_rights_status"] = "unknown"
    ok, detail = validate_first_person_response(
        {"status": "success", "answer_text": citation["verbatim_text"], "citations": [citation]}
    )
    assert ok is False
    assert "domain_rights_status" in detail
