"""Registry-derived teacher handling must match the old hardcoded literals."""

from __future__ import annotations

import pytest

from services.canonical_evidence_registry import founder_ids
from services.evidence_adapters.claim_verifier import _canon_teacher, _teachers_compatible
from services.guru_registry import neutral_voice_id, shared_scope_slug
from services.semantic_understanding import SemanticUnderstandingEngine as S

# Old literals, spelled only here (tests are outside the guard scope).
P, K, BOTH = "preethaji", "krishnaji", "preethaji_krishnaji"


@pytest.mark.parametrize(
    ("raw", "canon"),
    [
        ("Preethaji", P),
        ("Sri Preethaji", P),
        ("sri_preethaji", P),
        ("sri-preethaji", P),
        ("preetha", P),
        ("Krishnaji", K),
        ("sri krishnaji", K),
        ("sri-krishnaji", K),
        ("krishna", K),
        (BOTH, BOTH),
        ("sri preethaji & sri krishnaji", BOTH),
        ("Sri Preethaji and Sri Krishnaji", BOTH),
        ("both", BOTH),
        ("shared", BOTH),
        ("Someone  Else", "someone else"),
        ("sri-preethaji-and-sri-krishnaji", "sri-preethaji-and-sri-krishnaji"),
        (None, None),
    ],
)
def test_canon_teacher_matches_old_aliases(raw, canon):
    assert _canon_teacher(raw) == canon


@pytest.mark.parametrize(
    ("a", "b", "ok"),
    [
        (P, P, True),
        (P, K, False),
        (P, BOTH, True),
        (BOTH, K, True),
        (BOTH, BOTH, True),
        ("unknown", BOTH, False),
        ("unknown", "unknown", True),
        (None, None, True),
        (P, None, False),
    ],
)
def test_teachers_compatible_matches_old_rules(a, b, ok):
    assert _teachers_compatible(a, b) is ok


def test_scope_helpers_match_old_literals():
    assert founder_ids() == {P, K}
    assert neutral_voice_id() == BOTH
    assert shared_scope_slug() == "sri-preethaji-and-sri-krishnaji"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What does Sri Preethaji say about fear?", (P, False)),
        ("ask preetha", (P, False)),
        ("Krishnaji on love", (K, False)),
        ("what would krishna ji say", (K, False)),
        ("Preethaji and Krishnaji differ?", ("both", True)),
        ("what is the capital of France", (None, False)),
        ("Lord Krishna in the Gita", (None, False)),
    ],
)
def test_detect_teacher_scope_matches_old_hints(text, expected):
    assert S._detect_teacher_scope(text) == expected


def test_non_teacher_role_still_rejected_when_registry_is_unavailable(monkeypatch):
    """Fail closed: host speech must not become canonical evidence if gurus.yaml cannot load."""
    import services.canonical_evidence_registry as cer
    from domain.evidence_contract import SourceType

    monkeypatch.setattr(cer, "founder_ids", lambda: frozenset())
    reg = cer.CanonicalEvidenceRegistry()
    _, report = reg.register_and_ingest(
        canonical_uri="https://www.youtube.com/watch?v=abc12345678",
        source_type=SourceType.VIDEO,
        title="Host segment",
        teacher_id="krishnaji",
        rights_status="licensed",
        source_version="1",
        segments=[
            {
                "original_text": "Welcome everyone, please settle in and find a comfortable seat today.",
                "start_time_ms": 1000,
                "end_time_ms": 9000,
                "speaker_role": "host",
                "teacher_id": "krishnaji",
                "speaker_verified": True,
            }
        ],
    )
    assert not reg._records
    assert any(r.reason_code == "speaker_role_attribution_conflict" for r in report.rejections)
